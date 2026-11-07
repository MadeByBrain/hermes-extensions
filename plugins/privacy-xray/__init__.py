"""privacy-xray: where does your data actually go?

A privacy X-ray for Hermes Agent.

* Flow ledger: every outgoing model request, the main loop (``pre_api_request``) and side tasks
  such as titles, compression or vision (``pre_auxiliary_call``), is recorded as METADATA only:
  destination host, vendor, vendor headquarters, size, counts of detected personal data types and
  canary hits. Never content.
* Canary trace: ``/xray canary`` invents a fictitious person; ``/xray trace`` shows every request
  and every local store that carried it.
* Config audit: ``/xray check`` lists the paths Hermes itself configures on which content leaves the
  machine, each with a severity and an exact ``hermes config set`` fix; ``/xray fix <id> --yes``
  applies one (never a fix that deletes data: those are shown as advice only).
* Subject finder: ``/xray find "<name>"`` searches the local stores read-only, with an optional
  Markdown/JSON access report.
* Leak map: ``/xray map`` in chat, ``/xray report`` as a self-contained HTML file.
* Optional guard (off by default): ``llm_request`` middleware masks canary values and watch terms
  in the human-readable text of MAIN requests (never tool names, ids, JSON, thinking blocks or
  anything signed). Side requests cannot be changed by any plugin.
* ``fix --yes`` and ``find`` run only on local surfaces unless ``allow_sensitive_on_gateways``.

Standard library only. Hooks catch every error and return None: privacy-xray never breaks a turn.
"""
from __future__ import annotations

import json
import logging
import os
import shlex
import threading
import time
from pathlib import Path
from typing import Any, Optional

from . import audit, detect, report, scan, store, vendors, views

logger = logging.getLogger("hermes.plugins.privacy_xray")

PLUGIN_ID = store.PLUGIN_ID
DEFAULTS: dict[str, Any] = {
    "language": "auto",
    "record": True,
    "detectors": list(detect.DETECTORS),
    "watch_terms": [],
    "home_region": "",
    "guard": False,
    "ledger_max_mb": 5,
    "map_turns": 20,
    "scan_seconds": 30,
    "allow_sensitive_on_gateways": False,
    "wrap_width": 0,
}
# Surfaces on this machine (hermes_cli/plugin_command_dispatch.py passes ``platform``): the classic
# CLI, the TUI, the desktop app, the web dashboard, and "local" (CLI/desktop sessions the gateway
# owns). Everything else, including an empty or unknown value and api_server (the plugin cannot see
# whether the caller is on localhost), counts as remote: fail closed.
LOCAL_SURFACES = frozenset({"cli", "tui", "desktop", "dashboard", "local"})
# Surfaces that print command output into a terminal (v0.23 reports the classic CLI as "local").
# Terminals break long lines at any character; there privacy-xray wraps its own text at word boundaries.
TERMINAL_SURFACES = frozenset({"cli", "tui", "local"})

_ctx: Any = None
SCANNER = detect.Scanner()
_needles_lock = threading.Lock()
_needles_cache: dict[str, Any] = {"key": None, "needles": detect.Needles()}
_masked: dict[str, int] = {}
_masked_lock = threading.Lock()
_masker_cache: dict[str, Any] = {"gen": None, "rx": None}

_SKILL = Path(__file__).resolve().parent / "skills" / "privacy-xray" / "SKILL.md"
_SKILL_DESCRIPTION = ("Questions about privacy, GDPR or where chat data goes? Use tool_search for "
                      "privacy_xray before answering from memory.")

# --------------------------------------------------------------------------- settings


def _setting(key: str) -> Any:
    value = None
    if _ctx is not None:
        try:
            value = _ctx.get_config(key, None)
        except Exception:  # noqa: BLE001
            value = None
    else:
        # Loaded without a plugin context (dashboard backend): read the saved plugin settings.
        try:
            entry = ((audit.load_config().get("plugins") or {}).get("entries") or {}).get(PLUGIN_ID) or {}
            value = (entry.get("settings") or {}).get(key)
        except Exception:  # noqa: BLE001
            value = None
    return DEFAULTS[key] if value is None else value


def _bool(key: str) -> bool:
    v = _setting(key)
    if isinstance(v, str):
        return v.strip().lower() not in ("0", "false", "no", "off", "")
    return bool(v)


def _int(key: str, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(_setting(key))))
    except Exception:  # noqa: BLE001
        return int(DEFAULTS[key])


def _list(key: str) -> list[str]:
    v = _setting(key)
    if isinstance(v, str):
        v = [x.strip() for x in v.split(",")]
    if not isinstance(v, (list, tuple)):
        return list(DEFAULTS[key])
    return [str(x).strip() for x in v if str(x).strip()]


def _detectors() -> tuple[str, ...]:
    chosen = [d for d in _list("detectors") if d in detect.DETECTORS]
    return tuple(chosen)


def _lang() -> str:
    v = str(_setting("language") or "auto").strip().lower()
    if v in ("en", "de"):
        return v
    try:
        disp = str((audit.load_config().get("display") or {}).get("language") or "").lower()
        if disp.startswith("de"):
            return "de"
    except Exception:  # noqa: BLE001
        pass
    return "en"


def _region() -> str:
    return str(_setting("home_region") or "").strip()


def _needles() -> detect.Needles:
    path = store.data_dir() / "canaries.json"
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        mtime = 0
    terms = _list("watch_terms")
    key = f"{mtime}|{'|'.join(terms)}"
    with _needles_lock:
        if _needles_cache["key"] == key:
            return _needles_cache["needles"]
    n = detect.Needles(store.load_canaries(), terms)
    with _needles_lock:
        _needles_cache.update(key=key, needles=n)
    return n

# --------------------------------------------------------------------------- ledger hooks


def _record(kind: str, kw: dict) -> None:
    if not _bool("record"):
        return
    provider = str(kw.get("provider") or "")
    base_url = str(kw.get("base_url") or "")
    host = vendors.host_of(base_url) or vendors.PROVIDER_HOSTS.get(provider.lower().split(":", 1)[0], "")
    model = str(kw.get("model") or "")
    info = vendors.with_model(vendors.classify(host, provider), model)
    summary = SCANNER.scan_request(kw.get("request_messages"), kw.get("system_prompt"), _needles(), _detectors())
    rid = str(kw.get("api_request_id") or "")
    masked = 0
    if kind == "main" and rid:
        with _masked_lock:
            masked = _masked.pop(rid, 0)
    try:
        retry = int(kw.get("retry_count") or 0)
    except (TypeError, ValueError):
        retry = 0
    rec = {
        "v": 1, "ts": round(time.time(), 3), "kind": kind,
        "sid": str(kw.get("session_id") or ""), "turn": str(kw.get("turn_id") or ""),
        "aux_task": str(kw.get("aux_task") or "") if kind == "aux" else "",
        "platform": str(kw.get("platform") or ""), "provider": provider, "model": model,
        "api_mode": str(kw.get("api_mode") or ""), "host": info["host"], "vendor": info["vendor"],
        "hq": info["hq"], "vkind": info["kind"], "local": info["local"],
        "chars": summary["chars"], "types": summary["types"], "canary": summary["canary"],
        "watch": summary["watch_fields"], "retry": retry,
    }
    if info.get("mvendor") or info["kind"] == "router":
        rec["mvendor"], rec["mhq"] = info.get("mvendor") or "", info.get("mhq") or ""
    if summary.get("truncated"):
        rec["incomplete"] = True
    if kw.get("plugin_id"):
        rec["plugin_id"] = str(kw.get("plugin_id"))
    if masked:
        rec["masked"] = masked
    store.append_ledger(rec, _int("ledger_max_mb", 1, 500) * 1_048_576)


def on_pre_api_request(**kwargs: Any) -> None:
    try:
        _record("main", kwargs)
    except Exception:  # noqa: BLE001
        logger.debug("privacy-xray pre_api_request failed", exc_info=True)
    return None


def on_pre_auxiliary_call(**kwargs: Any) -> None:
    try:
        _record("aux", kwargs)
    except Exception:  # noqa: BLE001
        logger.debug("privacy-xray pre_auxiliary_call failed", exc_info=True)
    return None

# --------------------------------------------------------------------------- guard middleware

MASK = "[masked by privacy-xray]"
# Content blocks whose text is human-readable and may be masked. Everything else is passed through
# untouched: tool_use / function_call (names, ids, JSON arguments), thinking / redacted_thinking /
# reasoning, any block with a signature or encrypted content, images, audio, files.
_TEXT_BLOCKS = {"text", "input_text", "output_text"}
_TOOL_RESULT_BLOCKS = {"tool_result"}
_OUTPUT_ITEMS = {"function_call_output", "custom_tool_call_output"}
_TEXT_ROLES = {"system", "developer", "user", "assistant", "tool", "function"}


def _mask_str(text: str, rx: Any) -> tuple[str, int]:
    new, n = rx.subn(MASK, text)
    return (new, n) if n else (text, 0)


def _signed(block: dict) -> bool:
    return any(k in block for k in ("signature", "encrypted_content", "redacted_thinking"))


def _mask_block(block: Any, rx: Any, depth: int) -> tuple[Any, int]:
    if isinstance(block, str):
        return _mask_str(block, rx)
    if not isinstance(block, dict) or depth > 6 or _signed(block):
        return block, 0
    btype = str(block.get("type") or "")
    if btype in _TEXT_BLOCKS and isinstance(block.get("text"), str):
        new, n = _mask_str(block["text"], rx)
        return ({**block, "text": new}, n) if n else (block, 0)
    if btype in _TOOL_RESULT_BLOCKS and "content" in block:
        new, n = _mask_content(block["content"], rx, depth + 1)
        return ({**block, "content": new}, n) if n else (block, 0)
    return block, 0


def _mask_content(content: Any, rx: Any, depth: int = 0) -> tuple[Any, int]:
    """A message ``content``: a string, or a list of content blocks."""
    if isinstance(content, str):
        return _mask_str(content, rx)
    if isinstance(content, list) and depth <= 6:
        total, changed = 0, None
        for i, block in enumerate(content):
            nb, n = _mask_block(block, rx, depth + 1)
            if n:
                if changed is None:
                    changed = list(content)
                changed[i] = nb
                total += n
        return (changed, total) if changed is not None else (content, 0)
    return content, 0


def _mask_message(msg: Any, rx: Any) -> tuple[Any, int]:
    """One chat-completions / Anthropic message or Responses input item. Only text is touched."""
    if not isinstance(msg, dict) or _signed(msg):
        return msg, 0
    mtype = str(msg.get("type") or "")
    if mtype in _OUTPUT_ITEMS and "output" in msg:
        new, n = _mask_content(msg["output"], rx)
        return ({**msg, "output": new}, n) if n else (msg, 0)
    if mtype and mtype != "message":
        return msg, 0  # function_call, reasoning, item_reference, ...
    if str(msg.get("role") or "") not in _TEXT_ROLES or "content" not in msg:
        return msg, 0
    new, n = _mask_content(msg["content"], rx)
    return ({**msg, "content": new}, n) if n else (msg, 0)


def _mask_messages(items: Any, rx: Any) -> tuple[Any, int]:
    if isinstance(items, str):
        return _mask_str(items, rx)
    if not isinstance(items, list):
        return items, 0
    total, changed = 0, None
    for i, m in enumerate(items):
        nm, n = _mask_message(m, rx)
        if n:
            if changed is None:
                changed = list(items)
            changed[i] = nm
            total += n
    return (changed, total) if changed is not None else (items, 0)


def mask_request(request: dict, rx: Any) -> tuple[dict, int]:
    """A copy of ``request`` with canary values and watch terms masked in its human-readable text:
    ``messages`` (chat completions, Anthropic), ``system`` (string or text blocks), Responses
    ``input`` and ``instructions``. The original is never mutated."""
    new, total = dict(request), 0
    for key, fn in (("messages", _mask_messages), ("input", _mask_messages),
                    ("system", lambda v, r: _mask_content(v, r)), ("instructions", lambda v, r: _mask_content(v, r))):
        if key in new:
            nv, n = fn(new[key], rx)
            if n:
                new[key] = nv
                total += n
    return new, total


def on_llm_request(request: Any = None, api_request_id: Any = "", **_: Any) -> Optional[dict]:
    """llm_request middleware: mask canary values and watch terms in the main request (guard on)."""
    try:
        if not _bool("guard") or not isinstance(request, dict):
            return None
        needles = _needles()
        if _masker_cache["gen"] != needles.generation:
            _masker_cache.update(gen=needles.generation, rx=detect.compile_masker(needles.all_values()))
        rx = _masker_cache["rx"]
        if rx is None:
            return None
        new, total = mask_request(request, rx)
        if not total:
            return None
        rid = str(api_request_id or "")
        if rid:
            with _masked_lock:
                _masked[rid] = total
                while len(_masked) > 256:
                    _masked.pop(next(iter(_masked)))
        return {"request": new, "source": PLUGIN_ID, "reason": f"masked {total} canary/watch value(s)"}
    except Exception:  # noqa: BLE001
        logger.debug("privacy-xray guard failed", exc_info=True)
        return None

# --------------------------------------------------------------------------- actions


def do_check(lang: str) -> tuple[str, dict]:
    res = audit.check(region=_region())
    store.save_last("check", res)
    return views.render_check(res, lang), res


def do_map(lang: str, session_id: str = "", turns: int = 0, hours: float = 0) -> tuple[str, dict]:
    records = store.read_ledger()
    if session_id:
        scope = views.t("scope_session", lang)
    elif hours:
        scope = views.t("scope_hours", lang, n=f"{hours:g}")
    else:
        turns = turns or _int("map_turns", 1, 10000)
        scope = views.t("scope_turns", lang, n=turns)
    sel = views.select_records(records, session_id=session_id, turns=turns, hours=hours)
    main = audit.main_route(audit.load_config())
    agg = views.aggregate(sel, main, _region())
    return views.render_map(agg, lang, scope), {"scope": scope, **agg}


def do_trace(lang: str, cid: str = "", deep: bool = False) -> tuple[str, dict]:
    canary = store.canary_by_id(cid) if cid else store.latest_canary()
    if not canary:
        known = [c.get("id") for c in store.load_canaries()]
        if cid and known:
            return views.t("trace_unknown", lang, id=cid, ids=", ".join(known)), {"canary": None, "known": known}
        return views.t("trace_none", lang), {"canary": None}
    records = store.read_ledger(since=float(canary.get("created") or 0) - 1)
    rest = scan.search_all(store.hermes_home(), list(canary.get("match") or []), store.data_dir(),
                           seconds=_int("scan_seconds", 3, 600), deep=deep)
    places = views.trace_places(canary, records, rest)
    store.save_last("trace", {"canary_id": canary["id"], "ts": int(time.time()), "places": places})
    main = audit.main_route(audit.load_config())
    public = {k: canary[k] for k in ("id", "name", "email", "iban", "phone", "created")}
    return views.render_trace(canary, places, lang, main), {"canary": public, **places}


def do_find(lang: str, query: str, export: bool = False, deep: bool = False) -> tuple[str, dict]:
    q = (query or "").strip().strip("\"'").strip()
    if len(q) < 3:
        return views.t("find_usage", lang), {"error": "query too short"}
    # An access report should be complete: --export always includes the deep pass.
    res = scan.search_all(store.hermes_home(), [q], store.data_dir(), seconds=_int("scan_seconds", 3, 600),
                          snippet_term=q, snippets=5, deep=deep or export)
    text = views.render_find(q, res, lang)
    data: dict[str, Any] = {"query_masked": detect.mask_value(q), **res}
    if export:
        md, js = _export_access_report(q, res, lang)
        text += "\n" + views.t("find_export", lang, md=md, js=js)
        data["export"] = {"markdown": str(md), "json": str(js)}
    else:
        text += "\n" + views.t("find_hint", lang)
    return text, data


def _export_access_report(q: str, res: dict, lang: str) -> tuple[Path, Path]:
    d = store.reports_dir()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    slug = "".join(ch if ch.isalnum() else "-" for ch in detect.mask_value(q).lower())[:40].strip("-") or "subject"
    md_path, js_path = d / f"access-{slug}-{stamp}.md", d / f"access-{slug}-{stamp}.json"
    places = res.get("places", [])
    reasons = []
    if res.get("partial"):
        reasons.append(views.partial_text(res, "en").removeprefix("Search incomplete: ").rstrip("."))
    if "tool_tail" in (res.get("coverage") or []):
        reasons.append("tool outputs longer than 8 KB were searched in their first 8 KB only")
    complete = "no (" + "; ".join(reasons) + ")" if reasons else "yes"
    lines = ["# Access report (GDPR Art. 15 style)", "",
             f"- Subject: {detect.mask_value(q)} (search term masked)",
             f"- Generated: {time.strftime('%Y-%m-%d %H:%M %Z')}",
             f"- Hermes home: {store.hermes_home()}",
             "- Scope: local Hermes stores only (state.db, session files, memories, logs, cron output, plugin data).",
             f"- Search complete: {complete}", "",
             "| Store | Place | Hits |", "|---|---|---|"]
    for p in places:
        lines.append(f"| {p['store']} | {p['place']} | {p['count']} |")
    if not places:
        lines.append("| - | no hits | 0 |")
    snips = [s for s in res.get("state_db", {}).get("snippets", [])] + \
            [{"place": p["place"], "text": p["snippet"]} for p in places if p.get("snippet")]
    if snips:
        lines += ["", "## Masked excerpts", ""]
        for s in snips[:20]:
            lines.append(f"- {s.get('place')}: {s['text']}")
    lines += ["", "## Not covered", "",
              "- Data held by the model vendors and other recipients listed by `/xray check` (ask them directly).",
              "- Backups, other Hermes profiles, external memory providers, messaging platforms.", "",
              "Generated by privacy-xray. Not legal advice. Review before handing it out."]
    with store.Locked():
        store.write_text_private(md_path, "\n".join(lines) + "\n")
        store.write_json(js_path, {"subject_masked": detect.mask_value(q), "generated": int(time.time()),
                                   "complete": not reasons, "incomplete_reasons": reasons,
                                   "partial_files": res.get("partial_files") or [], "places": places,
                                   "snippets": snips[:20]})
    return md_path, js_path


def build_report_page(lang: str, session_id: str = "") -> str:
    """The HTML leak map for the current ledger (used by /xray report and the dashboard tab)."""
    _, agg = do_map(lang, session_id=session_id)
    check = store.load_last("check")
    if not isinstance(check, dict) or time.time() - float(check.get("ts") or 0) > 600:
        _, check = do_check(lang)
    trace = store.load_last("trace")
    canary = store.canary_by_id(trace.get("canary_id")) if isinstance(trace, dict) else None
    places = trace.get("places") if (isinstance(trace, dict) and canary) else None
    main = audit.main_route(audit.load_config())
    compare = report.compare_data(store.load_canaries(), store.read_ledger())
    flow_agg, flow_scope = None, ""
    since = None if session_id else report.canary_flow_since(canary if places is not None else None, compare)
    if since:
        # everything sent since the latest canary was created ("created" is whole seconds, rounded down,
        # so no margin: a margin would pull in the end of the earlier test)
        flow_agg = views.aggregate(store.read_ledger(since=since), main, _region())
        flow_scope = views.t("scope_since", lang, t=views.when(since, lang))
    return report.build_html(lang=lang, agg=agg, scope=agg.get("scope", ""), check=check, trace=places,
                             canary=canary, compare=compare, main=main, region=_region(),
                             flow_agg=flow_agg, flow_scope=flow_scope)


def do_report(lang: str, session_id: str = "") -> tuple[str, dict]:
    page = build_report_page(lang, session_id)
    path = store.reports_dir() / f"leak-map-{time.strftime('%Y%m%d-%H%M%S')}.html"
    store.write_text_private(path, page)
    return views.t("report_done", lang, path=path), {"path": str(path)}


def do_fix(lang: str, fid: str, apply: bool) -> str:
    res = audit.check(region=_region())
    f = next((x for x in res["findings"] if x["id"] == fid), None)
    if f is None:
        return views.t("fix_unknown", lang, id=fid)
    sets = f["fix"].get("sets") or []
    if f["severity"] == "green":
        return views.t("fix_green", lang, id=fid)
    if not sets:
        # Advice only (also with --yes): privacy-xray never applies it, for example the retention
        # setting that would make Hermes delete old chats.
        manual = f["fix"].get("manual") or {}
        text = views.t("fix_none", lang, id=fid, manual=manual.get(lang) or manual.get("en") or "")
        warning = f["fix"].get("warning") or {}
        if warning:
            text += "\n⚠️ " + (warning.get(lang) or warning.get("en") or "")
        return text
    cmds = "\n".join("  " + c for c in audit.fix_commands(f))
    if not apply:
        cons = f["fix"].get("consequence") or {}
        note = views.t("fix_note", lang, x=cons.get(lang) or cons.get("en")) if cons else ""
        return views.t("fix_show", lang, id=fid, sev=views.SEV_WORD[lang][f["severity"]],
                       why=f["why"].get(lang) or f["why"]["en"], cmds=cmds, note=note)
    ok, log = audit.apply_sets(sets)
    if not ok:
        return views.t("fix_failed", lang, err=log)
    after = audit.check(region=_region())
    store.save_last("check", after)
    g = next((x for x in after["findings"] if x["id"] == fid), None)
    sev = views.SEV_WORD[lang][g["severity"]] if g else views.SEV_WORD[lang]["green"]
    return views.t("fix_done", lang, cmds=cmds, id=fid, sev=sev)


def do_status(lang: str) -> str:
    records = store.read_ledger()
    day = time.time() - 86400
    hosts = {r.get("host") for r in records}
    lines = [views.t("status_head", lang, t=views.t("title", lang), n=len(records),
                     today=sum(1 for r in records if float(r.get("ts") or 0) >= day), d=len(hosts),
                     kb=round(store.ledger_size() / 1024))]
    c = store.latest_canary()
    lines.append(views.t("status_canary", lang, name=c["name"], cid=c["id"]) if c else views.t("status_nocanary", lang))
    last = store.load_last("check")
    if isinstance(last, dict) and last.get("summary"):
        s = last["summary"]
        lines.append(views.t("status_check", lang, r=s["red"], a=s["amber"], g=s["green"],
                             when=views.when(last.get("ts"), lang)))
    else:
        lines.append(views.t("status_nocheck", lang))
    lines.append(views.t("status_guard", lang, state=views.t("on" if _bool("guard") else "off", lang)))
    lines.append("/xray help")
    return "\n".join(lines)

# --------------------------------------------------------------------------- slash command


def _split(raw: str) -> list[str]:
    try:
        return shlex.split(raw)
    except ValueError:
        return raw.split()


class UsageError(Exception):
    """A friendly message for a malformed command; never a Python error text."""


def _num_option(rest: list[str], name: str, key: str, lang: str, lo: float, hi: float, whole: bool) -> float:
    i = rest.index(name)
    raw = rest[i + 1] if i + 1 < len(rest) else ""
    try:
        val = int(raw) if whole else float(raw)
    except ValueError:
        raise UsageError(views.t(key, lang)) from None
    if not (lo <= val <= hi) or val != val:
        raise UsageError(views.t(key, lang))
    return val


def _check_options(rest: list[str], allowed: set, lang: str, hint_key: str = "help") -> None:
    for a in rest:
        if a.startswith("--") and a not in allowed:
            raise UsageError(views.t("usage_option", lang, o=a, hint=views.t(hint_key, lang)
                                     if hint_key != "help" else "/xray help"))


def surface_allowed(platform: Any) -> bool:
    """fix --yes and find: allowed on local surfaces, refused on chat gateways and when unknown."""
    if _bool("allow_sensitive_on_gateways"):
        return True
    return str(platform or "").strip().lower() in LOCAL_SURFACES


def _refusal(verb: str, platform: Any, lang: str) -> str:
    p = str(platform or "").strip() or views.t("unknown_surface", lang)
    return views.t("gateway_refused", lang, v=verb, p=p, why=views.t("why_fix" if verb.startswith("fix") else "why_find", lang))


def _wrap_width() -> int:
    """Setting wrap_width, or with 0 the width of this terminal (when the command runs inside it), else 100."""
    width = _int("wrap_width", 0, 400)
    if width:
        return max(40, width)
    try:
        import shutil
        import sys
        if sys.stdout.isatty():
            cols = shutil.get_terminal_size((0, 0)).columns
            if cols >= 40:
                return cols - 1
    except Exception:  # noqa: BLE001
        pass
    return 100


def command_handler(raw_args: str = "", session_id: str = "", platform: Any = None, **kw: Any) -> str:
    out = _command(raw_args, session_id, platform, **kw)
    if str(platform or "").strip().lower() in TERMINAL_SURFACES:
        try:
            return views.wrap_text(out, _wrap_width())
        except Exception:  # noqa: BLE001
            logger.debug("wrap failed", exc_info=True)
    return out


def _command(raw_args: str = "", session_id: str = "", platform: Any = None, **_: Any) -> str:
    lang = "en"
    try:
        lang = _lang()
        args = _split((raw_args or "").strip())
        verb = args[0].lower() if args else "status"
        rest = args[1:]
        if verb in ("help", "?", "-h", "--help"):
            return views.t("help", lang)
        if verb == "status":
            return do_status(lang)
        if verb == "check":
            _check_options(rest, {"--all"}, lang)
            return do_check(lang)[0] if "--all" not in rest else views.render_check(audit.check(region=_region()), lang, True)
        if verb == "canary":
            return views.render_canary(store.add_canary(), lang)
        if verb == "trace":
            _check_options(rest, {"--deep"}, lang)
            ids = [a for a in rest if not a.startswith("--")]
            return do_trace(lang, ids[0] if ids else "", deep="--deep" in rest)[0]
        if verb == "map":
            _check_options(rest, {"--session", "--turns", "--hours"}, lang)
            turns, hours, sid = 0, 0.0, ""
            given = [o for o in ("--session", "--turns", "--hours") if o in rest]
            if len(given) > 1:
                raise UsageError(views.t("usage_map", lang))
            if "--turns" in rest:
                turns = int(_num_option(rest, "--turns", "usage_turns", lang, 1, 10000, True))
            if "--hours" in rest:
                hours = _num_option(rest, "--hours", "usage_hours", lang, 1e-6, 8760, False)
            if "--session" in rest:
                sid = session_id or ""
                if not sid:
                    return views.t("map_empty", lang)
            return do_map(lang, session_id=sid, turns=turns, hours=hours)[0]
        if verb == "report":
            _check_options(rest, {"--session"}, lang)
            return do_report(lang, session_id=session_id if "--session" in rest else "")[0]
        if verb == "find":
            _check_options(rest, {"--export", "--deep"}, lang)
            if not surface_allowed(platform):
                return _refusal("find", platform, lang)
            export = "--export" in rest
            query = " ".join(a for a in rest if a not in ("--export", "--deep"))
            return do_find(lang, query, export, deep="--deep" in rest)[0]
        if verb == "fix":
            _check_options(rest, {"--yes"}, lang)
            ids = [a for a in rest if not a.startswith("-")]
            if not ids:
                return views.t("check_fix_hint", lang)
            apply = "--yes" in rest or "-y" in rest
            if apply and not surface_allowed(platform):
                return _refusal("fix --yes", platform, lang)
            return do_fix(lang, ids[0], apply=apply)
        return views.t("unknown_cmd", lang, v=verb) + "\n" + views.t("help", lang)
    except UsageError as exc:
        return str(exc)
    except Exception as exc:  # noqa: BLE001
        logger.debug("/xray failed", exc_info=True)
        return views.t("error", lang, e=f"{type(exc).__name__}: {exc}"[:200])

# --------------------------------------------------------------------------- tool

TOOL_SCHEMA = {
    "name": "privacy_xray",
    "description": (
        "Privacy audit: where chat data goes and where it is stored. "
        "Answers questions like 'which companies see my chats?', 'is my data sent to the US?', "
        "'where is this person mentioned?'. Actions: map = outgoing model requests recorded by the plugin "
        "(destinations, vendor HQ country, side tasks such as titles or compression, detected personal data "
        "types; metadata only); check = audit of the Hermes config with a severity and the exact fix command "
        "per path; trace = where the canary person went (requests and local stores); find = read-only search "
        "of local Hermes stores for a name or e-mail with masked snippets. The tool never changes settings: "
        "tell the user to run /xray fix <id> --yes. Country = vendor headquarters, not processing location; "
        "this is not legal advice."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["map", "check", "trace", "find"]},
            "query": {"type": "string", "description": "find: the name or e-mail to search (3+ characters)."},
            "scope": {"type": "string", "enum": ["session", "recent"],
                      "description": "map: this chat only, or the recent turns across chats (default)."},
            "export": {"type": "boolean", "description": "find: also write a Markdown/JSON access report."},
        },
        "required": ["action"],
    },
}


def tool_handler(args: Any, **kw: Any) -> str:
    try:
        args = args if isinstance(args, dict) else {}
        action = str(args.get("action") or "").lower()
        lang = _lang()
        if action == "map":
            sid = str(kw.get("session_id") or "") if args.get("scope") == "session" else ""
            text, data = do_map(lang, session_id=sid)
        elif action == "check":
            text, data = do_check(lang)
            data = {"summary": data["summary"], "findings": [
                {"id": f["id"], "severity": f["severity"], "why": f["why"]["en"],
                 "fix_commands": audit.fix_commands(f)} for f in data["findings"]]}
            data["note"] = views.t("fix_tool", "en")
        elif action == "trace":
            text, data = do_trace(lang)
        elif action == "find":
            surface = ""
            try:
                surface = _ctx.session_surface() if _ctx is not None and hasattr(_ctx, "session_surface") else ""
            except Exception:  # noqa: BLE001
                surface = ""
            if not surface_allowed(surface):
                return json.dumps({"ok": False, "error": "find is only available on this machine, not over a chat gateway",
                                   "error_type": "not_allowed_here",
                                   "next_step": "Tell the user to run /xray find in the Hermes CLI, TUI, desktop app "
                                                "or dashboard on this machine. Do not retry."})
            query = str(args.get("query") or "")
            if len(query.strip()) < 3:
                return json.dumps({"ok": False, "error": "query must have at least 3 characters",
                                   "error_type": "invalid_argument",
                                   "next_step": "Ask the user for the full name or e-mail address."})
            text, data = do_find(lang, query, bool(args.get("export")))
        else:
            return json.dumps({"ok": False, "error": f"unknown action {action!r}", "error_type": "invalid_argument",
                               "next_step": "Use one of: map, check, trace, find."})
        return json.dumps({"ok": True, "action": action, "text": text, "data": data}, ensure_ascii=False,
                          default=lambda o: sorted(o) if isinstance(o, set) else str(o))
    except Exception as exc:  # noqa: BLE001
        logger.debug("privacy_xray tool failed", exc_info=True)
        return json.dumps({"ok": False, "error": str(exc)[:200], "error_type": "internal"})

# --------------------------------------------------------------------------- register


def register(ctx: Any) -> None:
    global _ctx
    _ctx = ctx
    ctx.register_hook("pre_api_request", on_pre_api_request)
    ctx.register_hook("pre_auxiliary_call", on_pre_auxiliary_call)
    ctx.register_middleware("llm_request", on_llm_request)
    ctx.register_tool(name="privacy_xray", toolset="privacy_xray", schema=TOOL_SCHEMA, handler=tool_handler,
                      emoji="🩻")
    try:
        ctx.register_command("xray", command_handler,
                             description="Privacy X-ray: where your data goes (check, canary, trace, map, report, find, fix)",
                             args_hint="[check|canary|trace|map|report|find|fix|help]")
    except Exception:  # noqa: BLE001
        logger.warning("privacy-xray command was not registered", exc_info=True)
    try:
        ctx.register_skill("privacy-xray", _SKILL, description=_SKILL_DESCRIPTION)
    except Exception:  # noqa: BLE001
        logger.warning("privacy-xray skill was not registered", exc_info=True)
