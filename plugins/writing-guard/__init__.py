"""writing-guard: style check for the final answer of every Hermes turn (German and English).

What it does
------------
* Dashes: finds em and en dashes (and their rarer siblings) outside code, URLs and quotes.
  ``mode: fix`` replaces them by rule (ranges become hyphens, list bullets become "- ",
  dashes between words become a comma or a spaced hyphen).
* AI phrases: reports stock phrases in German and English ("Es ist wichtig zu beachten",
  "I hope this helps", "delve"). Reported only, never rewritten.
* du / Sie: in German text, reports both forms in the same paragraph, a switch against the
  previous answer of the same chat, or the wrong form when one is configured. Reported only.

How it works
------------
The ``transform_llm_output`` hook runs once per turn, before Hermes stores the answer. In the
default ``report`` mode the answer stays as it is and one italic line is appended when there is
a finding (an append is shown as a plain suffix after streaming). With ``footer: false`` the text
is never changed and the last report is only available through ``/writing-guard``.

No model calls, no network. Standard library only. Every error ends silently (answer unchanged),
never in an aborted turn.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

from . import guard

try:
    import fcntl  # Linux/macOS only; without it the store runs unlocked
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

logger = logging.getLogger("hermes.plugins.writing_guard")

PLUGIN_ID = "writing-guard"
DEFAULTS: dict[str, Any] = {
    "mode": "report",
    "footer": True,
    "language": "auto",
    "dash_style": "comma",
    "address": "auto",
    "check_dashes": True,
    "check_phrases": True,
    "check_address": True,
    "track_switches": True,
    "skip_quotes": True,
    "extra_phrases": [],
    "ignore_phrases": [],
    "disabled_platforms": ["cron", "subagent", "kanban", "batch", "webhook"],
}
RETENTION_DAYS = 30
MAX_SESSIONS = 2000

_SKILL = Path(__file__).resolve().parent / "skills" / "check-draft" / "SKILL.md"
_SKILL_DESCRIPTION = ("Writing a mail, post or page for the user? Before you deliver it, run "
                      "writing_guard_check (find it with tool_search) and fix what it reports.")

_ctx: Any = None
_last: dict[str, Any] = {}
_last_lock = threading.Lock()

# --------------------------------------------------------------------------- settings


def _setting(key: str) -> Any:
    value = None
    if _ctx is not None:
        try:
            value = _ctx.get_config(key, None)
        except Exception:  # noqa: BLE001
            value = None
    return DEFAULTS[key] if value is None else value


def _bool(key: str) -> bool:
    v = _setting(key)
    if isinstance(v, str):
        return v.strip().lower() not in ("0", "false", "no", "off", "")
    return bool(v)


def _choice(key: str, allowed: tuple[str, ...]) -> str:
    v = str(_setting(key) or "").strip().lower()
    return v if v in allowed else DEFAULTS[key]


def _list(key: str) -> list[str]:
    v = _setting(key)
    if isinstance(v, str):
        v = [x.strip() for x in v.split(",")]
    if not isinstance(v, (list, tuple)):
        return list(DEFAULTS[key])
    return [str(x).strip() for x in v if str(x).strip()]


def _check_kwargs(fix: bool, address: Optional[str] = None) -> dict[str, Any]:
    addr = (address or "").strip().lower() or _choice("address", ("auto", "du", "sie"))
    return {
        "fix": fix,
        "dash_style": _choice("dash_style", ("comma", "hyphen")),
        "check_dashes": _bool("check_dashes"),
        "check_phrases": _bool("check_phrases"),
        "check_address": _bool("check_address"),
        "address": addr if addr in ("auto", "du", "sie") else "auto",
        "extra_phrases": _list("extra_phrases"),
        "ignore_phrases": _list("ignore_phrases"),
        "skip_quotes": _bool("skip_quotes"),
        "track_switches": _bool("track_switches"),
    }

# --------------------------------------------------------------------------- store


def _hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home  # public helper
        return Path(get_hermes_home())
    except Exception:  # noqa: BLE001
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def _store_dir() -> Path:
    d = _hermes_home() / "plugin-data" / PLUGIN_ID
    d.mkdir(parents=True, exist_ok=True)
    return d


class _Locked:
    """Exclusive file lock across processes (gateway, desktop, CLI may run in parallel)."""

    def __init__(self, path: Path):
        self.fh = open(path, "a+")

    def __enter__(self):
        if fcntl is not None:
            fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        try:
            if fcntl is not None:
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        finally:
            self.fh.close()


def _sessions(data: dict) -> dict:
    raw = data.get("sessions")
    return raw if isinstance(raw, dict) else {}


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _remember_form(session_id: str, form: Optional[str]) -> Optional[str]:
    """Return the form of address stored for this chat and store the new one (du or sie)."""
    if not session_id:
        return None
    d = _store_dir()
    path = d / "sessions.json"
    with _Locked(d / ".lock"):
        data = _read(path)
        sessions = _sessions(data)
        entry = sessions.get(session_id)
        prev = entry.get("form") if isinstance(entry, dict) else None
        if form in ("du", "sie"):
            now = time.time()
            sessions[session_id] = {"form": form, "ts": int(now)}
            cutoff = now - RETENTION_DAYS * 86400
            sessions = {k: v for k, v in sessions.items()
                        if isinstance(v, dict) and v.get("ts", 0) >= cutoff}
            if len(sessions) > MAX_SESSIONS:
                keep = sorted(sessions.items(), key=lambda kv: kv[1].get("ts", 0))[-MAX_SESSIONS // 2:]
                sessions = dict(keep)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"version": 1, "sessions": sessions}), encoding="utf-8")
            os.replace(tmp, path)
        return prev if prev in ("du", "sie") else None


def _peek_form(session_id: str) -> Optional[str]:
    if not session_id:
        return None
    data = _read(_store_dir() / "sessions.json")
    entry = _sessions(data).get(session_id)
    prev = entry.get("form") if isinstance(entry, dict) else None
    return prev if prev in ("du", "sie") else None

# --------------------------------------------------------------------------- hook


def _footer_language(rep: guard.Report) -> str:
    lang = _choice("language", ("auto", "en", "de"))
    return rep.language if lang == "auto" else lang


def on_llm_output(response_text: Any = None, session_id: str = "", model: str = "",
                  platform: str = "", turn_id: Any = None, **_: Any) -> Optional[str]:
    """transform_llm_output: return a replacement string, or None to leave the answer alone."""
    try:
        mode = _choice("mode", ("report", "fix", "off"))
        if mode == "off" or not isinstance(response_text, str) or not response_text.strip():
            return None
        if (platform or "").strip().lower() in {p.lower() for p in _list("disabled_platforms")}:
            return None
        kwargs = _check_kwargs(fix=(mode == "fix"))
        previous = _peek_form(session_id) if kwargs["check_address"] else None
        rep = guard.check(response_text, previous_form=previous, **kwargs)
        if kwargs["check_address"] and rep.form in ("du", "sie"):
            _remember_form(session_id, rep.form)
        lang = _footer_language(rep)
        line = guard.footer(rep, lang)
        with _last_lock:
            _last.clear()
            _last.update({"ts": int(time.time()), "platform": platform or "", "mode": mode,
                          "report": rep.as_dict(), "summary": line})
        text = rep.text if (mode == "fix" and rep.text) else response_text
        if line and _bool("footer"):
            text = text + ("\n\n" if not text.endswith("\n") else "\n") + line
        return text if text != response_text else None
    except Exception:  # noqa: BLE001
        logger.debug("writing-guard hook failed", exc_info=True)
        return None

# --------------------------------------------------------------------------- tool

TOOL_SCHEMA = {
    "name": "writing_guard_check",
    "description": (
        "Style check for a draft: dashes, AI phrases, du/Sie. "
        "Checks a text you are about to deliver (mail, social post, web page, document) for em and "
        "en dashes, stock AI phrases in German and English, and mixed or wrong forms of address "
        "(du/Sie) in German. With fix=true it returns the text with all dashes replaced by rule. "
        "AI phrases and the form of address are only reported: rewrite those parts yourself, "
        "then deliver the result. Code blocks, inline code, URLs and quotes are skipped."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "The full draft text."},
            "fix": {"type": "boolean", "description": "Return the text with dashes replaced. Default false."},
            "address": {"type": "string", "enum": ["auto", "du", "sie"],
                        "description": "Expected German form of address. auto = only report mixing."},
        },
        "required": ["text"],
    },
}


def tool_handler(args: Any, **_: Any) -> str:
    try:
        args = args if isinstance(args, dict) else {}
        text = args.get("text")
        if not isinstance(text, str) or not text.strip():
            return json.dumps({"ok": False, "error": "text is empty", "error_type": "invalid_argument",
                               "next_step": "Pass the full draft as text."})
        if len(text) > guard.MAX_CHARS:
            return json.dumps({"ok": False, "error": f"text longer than {guard.MAX_CHARS} characters",
                               "error_type": "too_long", "next_step": "Check the draft in parts."})
        fix = bool(args.get("fix"))
        kwargs = _check_kwargs(fix=fix, address=args.get("address"))
        kwargs["track_switches"] = False
        rep = guard.check(text, **kwargs)
        out: dict[str, Any] = {"ok": True, "clean": not rep.has_findings or
                               (fix and not (rep.phrases or rep.mixed or rep.wrong_form)),
                               "report": rep.as_dict(), "summary": guard.footer(rep, rep.language)}
        if fix:
            out["fixed_text"] = rep.text if rep.text is not None else text
        if rep.phrases or rep.mixed or rep.wrong_form:
            out["next_step"] = ("Rewrite the reported phrases in plain words and use one form of "
                                "address, then deliver the text.")
        return json.dumps(out, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        logger.debug("writing_guard_check failed", exc_info=True)
        return json.dumps({"ok": False, "error": str(exc)[:200], "error_type": "internal"})

# --------------------------------------------------------------------------- slash command


def command_handler(raw_args: str = "") -> str:
    try:
        raw = (raw_args or "").strip()
        verb, _, rest = raw.partition(" ")
        if verb.lower() == "check":
            if not rest.strip():
                return "Usage: /writing-guard check <text>"
            rep = guard.check(rest, **_check_kwargs(fix=False))
            return guard.footer(rep, rep.language).strip("*") or "writing-guard: no findings."
        if verb.lower() in ("help", "?"):
            return ("/writing-guard: settings and the last report.\n"
                    "/writing-guard check <text>: check a text.")
        lines = [
            f"writing-guard: mode {_choice('mode', ('report', 'fix', 'off'))}, "
            f"footer {'on' if _bool('footer') else 'off'}, "
            f"address {_choice('address', ('auto', 'du', 'sie'))}, "
            f"dash style {_choice('dash_style', ('comma', 'hyphen'))}.",
            "Off on: " + (", ".join(_list("disabled_platforms")) or "none") + ".",
        ]
        with _last_lock:
            last = dict(_last)
        if last:
            when = time.strftime("%H:%M:%S", time.localtime(last["ts"]))
            lines.append(f"Last answer ({when}, {last.get('platform') or 'unknown'}): "
                         + (last.get("summary", "").strip("*") or "no findings."))
        else:
            lines.append("No answer checked in this process yet.")
        return "\n".join(lines)
    except Exception:  # noqa: BLE001
        logger.debug("/writing-guard failed", exc_info=True)
        return "writing-guard: status not available."

# --------------------------------------------------------------------------- register


def register(ctx: Any) -> None:
    global _ctx
    _ctx = ctx
    ctx.register_hook("transform_llm_output", on_llm_output)
    ctx.register_tool(name="writing_guard_check", toolset="writing_guard", schema=TOOL_SCHEMA,
                      handler=tool_handler, emoji="✍️")
    try:
        ctx.register_command("writing-guard", command_handler,
                             description="writing-guard: settings, last report, check a text",
                             args_hint="[check <text>]")
    except Exception:  # noqa: BLE001
        logger.warning("writing-guard command was not registered", exc_info=True)
    try:
        ctx.register_skill("check-draft", _SKILL, description=_SKILL_DESCRIPTION)
    except Exception:  # noqa: BLE001
        logger.warning("writing-guard skill was not registered", exc_info=True)
