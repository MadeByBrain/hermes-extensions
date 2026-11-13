"""manners-meter: how polite are you to your agent, and what is in the swear jar?

What it does
------------
* ``/manners`` (every surface) and ``hermes manners`` (terminal) count "please", "thank you",
  "bitte", "danke" and friends in the messages you typed, estimate how many tokens your
  politeness cost, and count the swear words you aimed at your agent (the swear jar).
* ``/manners card`` and ``hermes manners --card`` write a share card (HTML, 1080 x 1920).
* Optional swear jar reaction: when a message of yours contains a swear word, a short note
  (``context`` of the ``pre_llm_call`` hook, added to your message, never to the system prompt)
  tells the agent the new jar count, so it may answer with one dry line.

How it counts
-------------
Read only, from this profile's ``state.db``. Only text you typed: code blocks, quoted lines and
injected system blocks are skipped, and machine sources (cron, subagent, kanban, batch, webhook)
are excluded. Token figures are estimates (about 4 characters per token), not provider numbers.

No model calls, no network. Standard library only. Every error ends quietly.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

from . import card as _card
from . import meter

logger = logging.getLogger("hermes.plugins.manners_meter")

PLUGIN_ID = "manners-meter"
DEFAULTS: dict[str, Any] = {
    "language": "auto",
    "jar_reactions": True,
    "jar_price": 1.0,
    "currency": "",
    "price_per_mtok": 3.0,
    "extra_polite": [],
    "extra_swear": [],
    "excluded_sources": list(meter.DEFAULT_EXCLUDED_SOURCES),
}

_ctx: Any = None


def _home() -> Path:
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home())
    except Exception:
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def _cfg(key: str) -> Any:
    default = DEFAULTS[key]
    try:
        val = _ctx.get_config(key) if _ctx is not None else None
    except Exception:
        val = None
    if val is None:
        return default
    if isinstance(default, bool):
        return val if isinstance(val, bool) else str(val).lower() in ("1", "true", "yes", "on")
    if isinstance(default, float):
        try:
            return max(0.0, float(val))
        except (TypeError, ValueError):
            return default
    if isinstance(default, list):
        return [str(x) for x in val] if isinstance(val, (list, tuple)) else default
    return str(val)


def _lang(rep: Optional[meter.Report] = None) -> str:
    lang = _cfg("language")
    if lang in ("en", "de"):
        return lang
    if rep is not None and (rep.de_votes or rep.en_votes):
        return rep.guess_language()
    env = (os.environ.get("LANG") or "").lower()
    return "de" if env.startswith("de") else "en"


def build_report(days: Optional[int] = None, session_id: Optional[str] = None) -> meter.Report:
    rows = meter.read_rows(_home() / "state.db", days=days, session_id=session_id,
                           excluded_sources=tuple(_cfg("excluded_sources")))
    return meter.analyze_rows(rows, extra_polite=_cfg("extra_polite"), extra_swear=_cfg("extra_swear"), days=days)


def _text(rep: meter.Report, scope: str = "all") -> str:
    return meter.render_text(rep, lang=_lang(rep), scope=scope, jar_price=_cfg("jar_price"),
                             currency=_cfg("currency"), price_per_mtok=_cfg("price_per_mtok"))


def write_card(rep: meter.Report, path: Optional[Path] = None) -> Path:
    out = Path(path) if path else _home() / "plugin-data" / PLUGIN_ID / "manners-card.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = _card.render_card(rep, lang=_lang(rep), jar_price=_cfg("jar_price"), currency=_cfg("currency"))
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(doc, encoding="utf-8")
    os.replace(tmp, out)
    return out


# ---------------------------------------------------------------------------------------
# /manners
# ---------------------------------------------------------------------------------------

USAGE = ("/manners           all time\n"
         "/manners 30        last 30 days\n"
         "/manners chat      this chat only\n"
         "/manners card      write a share card (HTML, 1080x1920) and show its path\n"
         "/manners json      raw numbers")


def _parse_days(tok: str) -> Optional[int]:
    m = re.fullmatch(r"(\d{1,4})d?", tok)
    return int(m.group(1)) if m and int(m.group(1)) > 0 else None


def slash_manners(raw_args: str = "", session_id: str = "", **_kw) -> str:
    try:
        toks = (raw_args or "").lower().split()
        if any(t in ("help", "-h", "--help", "?") for t in toks):
            return USAGE
        days = next((d for d in (_parse_days(t) for t in toks) if d), None)
        chat = any(t in ("chat", "session", "here") for t in toks)
        rep = build_report(days=days, session_id=(session_id or None) if chat else None)
        if "json" in toks:
            return json.dumps(rep.to_dict(), ensure_ascii=False, indent=2)
        text = _text(rep, scope="session" if chat else "all")
        if "card" in toks:
            path = write_card(rep)
            text += ("\n\nKarte: " if _lang(rep) == "de" else "\n\nCard: ") + str(path)
        return text
    except Exception as exc:  # never break the chat
        logger.warning("manners-meter: /manners failed: %s", exc)
        return f"manners-meter: could not read the history ({type(exc).__name__})."


# ---------------------------------------------------------------------------------------
# hermes manners
# ---------------------------------------------------------------------------------------

def _cli_setup(parser) -> None:
    parser.add_argument("--days", type=int, default=None, help="only the last N days")
    parser.add_argument("--json", action="store_true", help="print the raw numbers as JSON")
    parser.add_argument("--card", nargs="?", const="", default=None, metavar="PATH",
                        help="write the share card (HTML, 1080x1920); default path under plugin-data")


def _cli_handler(args) -> int:
    days = args.days if args.days and args.days > 0 else None
    rep = build_report(days=days)
    if args.json:
        print(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(_text(rep))
    if args.card is not None:
        path = write_card(rep, Path(args.card) if args.card else None)
        print(("\nKarte: " if _lang(rep) == "de" else "\nCard: ") + str(path))
    return 0


# ---------------------------------------------------------------------------------------
# Swear jar reaction (pre_llm_call)
# ---------------------------------------------------------------------------------------

_JAR_NOTE = {
    "en": ("[manners-meter] The user's message contains a swear word ({w}). Swear jar now holds "
           "{n} coins. You may acknowledge it with one short, dry, friendly line (for example that "
           "a coin went into the jar), then answer normally. Do not lecture."),
    "de": ("[manners-meter] Die Nachricht des Nutzers enthält ein Schimpfwort ({w}). Im Schimpfglas "
           "liegen jetzt {n} Münzen. Du darfst das mit einer kurzen, trockenen, freundlichen Zeile "
           "erwähnen (etwa, dass eine Münze ins Glas gewandert ist), dann normal antworten. Keine Belehrung."),
}


_JAR_CACHE: dict = {}


def on_pre_llm_call(**kw) -> Optional[dict]:
    try:
        if not _cfg("jar_reactions"):
            return None
        if (kw.get("platform") or "") in _cfg("excluded_sources"):
            return None
        msg = kw.get("user_message")
        if not isinstance(msg, str):
            return None
        text = meter.clean_user_text(msg)
        hits = meter.swear_hits(text, _cfg("extra_swear"))
        if not hits:
            return None
        now_n = sum(n for _r, _l, n in hits)
        cached = _JAR_CACHE.get("total")
        if cached is not None and time.time() - _JAR_CACHE.get("at", 0) < 3600:
            total = cached + now_n  # cheap path: no rescan for an hour
        else:
            before = build_report()
            # The current message may already be stored; count it once.
            total = before.swear_total if _already_stored(msg, kw.get("session_id")) else before.swear_total + now_n
            _JAR_CACHE["at"] = time.time()
            _JAR_CACHE["lang"] = _lang(before)
        _JAR_CACHE["total"] = total
        lang = "de" if any(r.startswith("de.") for r, _l, _n in hits) else _JAR_CACHE.get("lang") or _lang()
        return {"context": _JAR_NOTE[lang].format(w=hits[0][1], n=total)}
    except Exception as exc:
        logger.debug("manners-meter: jar hook failed: %s", exc)
        return None


def _already_stored(msg: str, session_id: Optional[str]) -> bool:
    if not session_id:
        return False
    try:
        import sqlite3
        db = _home() / "state.db"
        if not db.is_file():
            return False
        con = sqlite3.connect("file:" + str(db) + "?mode=ro", uri=True, timeout=2)
        try:
            row = con.execute("SELECT 1 FROM messages WHERE session_id=? AND role='user' AND content=? "
                              "AND timestamp >= ? LIMIT 1", (session_id, msg, time.time() - 600)).fetchone()
            return row is not None
        finally:
            con.close()
    except Exception:
        return False


def register(ctx) -> None:
    global _ctx
    _ctx = ctx
    ctx.register_command("manners", slash_manners,
                         description="Politeness count, token cost and swear jar from your own history",
                         args_hint="[30|chat|card|json]")
    ctx.register_cli_command("manners", "Politeness count and swear jar from your Hermes history",
                             _cli_setup, _cli_handler,
                             description="Counts please/thank you and swear words in the messages you typed. Read only.")
    ctx.register_hook("pre_llm_call", on_pre_llm_call)
