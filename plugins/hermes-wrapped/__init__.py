"""hermes-wrapped: your year with your agent, as shareable story cards.

What it does
------------
* ``hermes wrapped`` reads this profile's ``state.db`` (read only), prints a short summary and
  writes story cards (1080 x 1920) as self-contained HTML, plus PNG when a headless Chrome or
  Chromium is installed. ``index.html`` shows all cards side by side.
* ``/wrapped`` (every surface) prints the same summary and writes the HTML cards.

Privacy
-------
Everything is counted locally. No model calls, no network, no telemetry. Session titles are
hidden on the cards unless you pass ``--show-titles``. Machine sessions (cron, subagents, ...)
are not counted as your messages. Costs are not shown: the cost columns in state.db are
estimates that do not add up reliably.

Standard library only. Every error ends quietly with a short message.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

from . import cards as _cards
from . import render as _render
from . import stats as _stats
from . import words as _words

logger = logging.getLogger("hermes.plugins.hermes_wrapped")

PLUGIN_ID = "hermes-wrapped"
DEFAULTS: dict[str, Any] = {
    "language": "auto",
    "timezone": "",
    "show_titles": False,
    "exclude_words": [],
    "rename_words": [],
    "excluded_sources": list(_stats.DEFAULT_EXCLUDED_SOURCES),
    "browser_path": "",
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
    if isinstance(default, list):
        return [str(x) for x in val] if isinstance(val, (list, tuple)) else default
    return str(val)


def _tz(name: str = ""):
    """(tzinfo or None for system local time, display name)."""
    name = (name or _cfg("timezone") or "").strip()
    if name:
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(name), name
        except Exception:
            logger.warning("hermes-wrapped: unknown timezone %r, using local time", name)
    local = _dt.datetime.now().astimezone().tzinfo
    return local, str(local or "local")


def _lang(st: Optional[_stats.Stats] = None, forced: str = "") -> str:
    lang = forced or _cfg("language")
    if lang in ("en", "de"):
        return lang
    if st is not None and (st.de_votes or st.en_votes):
        return st.guess_language()
    env = (os.environ.get("LANG") or "").lower()
    return "de" if env.startswith("de") else "en"


def build_stats(*, year: Optional[int] = None, days: Optional[int] = None, all_time: bool = False,
                tz_name: str = "", show_titles: bool = False, renames: Optional[list] = None) -> _stats.Stats:
    tz, tzn = _tz(tz_name)
    if all_time:
        window = _stats.all_window()
    elif days:
        window = _stats.days_window(days)
    else:
        window = _stats.year_window(year or _dt.datetime.now(tz).year, tz)
    return _stats.collect(_home(), window, tz=tz, tz_name=tzn, excluded=tuple(_cfg("excluded_sources")),
                          exclude_words=_cfg("exclude_words"), with_titles=show_titles,
                          rename_words=_words.parse_renames(list(_cfg("rename_words")) + list(renames or [])))


def out_dir(st: _stats.Stats) -> Path:
    w = st.window
    slug = str(w.year) if w.year else (f"last-{w.days}-days" if w.days else "all-time")
    return _home() / "plugin-data" / PLUGIN_ID / slug


def write_cards(st: _stats.Stats, *, lang: str, show_titles: bool = False, out: Optional[Path] = None,
                png: bool = True) -> dict:
    target = Path(out) if out else out_dir(st)
    target.mkdir(parents=True, exist_ok=True)
    rendered = _cards.render_all(st, lang=lang, show_titles=show_titles)
    files = []
    for i, (slug, doc) in enumerate(rendered, 1):
        path = target / f"{i:02d}-{slug}.html"
        tmp = path.with_suffix(".html.tmp")
        tmp.write_text(doc, encoding="utf-8")
        os.replace(tmp, path)
        files.append(path)
    if out is None:  # only in our own plugin-data folder: drop cards of an earlier run that no longer apply
        keep = {p.name for p in files} | ({p.with_suffix(".png").name for p in files} if png else set())
        for old in target.glob("[0-9][0-9]-*.*"):
            if old.name not in keep and old.suffix in (".html", ".png"):
                old.unlink()
    title = f"Hermes Wrapped {_cards.period_label(st, lang)}"
    (target / "index.html").write_text(_cards.gallery([p.name for p in files], title), encoding="utf-8")
    pngs: list[Path] = []
    browser = None
    if png and files:
        # The first card decides which browser works (a snap Chromium may start but cannot read ~/.hermes).
        for cand in _render.find_browsers(_cfg("browser_path")):
            first = files[0].with_suffix(".png")
            if _render.screenshot(cand, files[0], first):
                browser = cand
                pngs.append(first)
                break
        if browser:
            for p in files[1:]:
                out_png = p.with_suffix(".png")
                if _render.screenshot(browser, p, out_png):
                    pngs.append(out_png)
    return {"dir": target, "html": files, "png": pngs, "browser": browser}


# ---------------------------------------------------------------------------------------
# Text summary
# ---------------------------------------------------------------------------------------

SUMMARY = {
    "en": {"head": "Hermes Wrapped {p}", "none": "No conversations in this period yet.",
           "type": "Your type: {n} ({c})", "vol": "{s} {chats}, {m} {msgs} from you, {d} {days}",
           "tool": "Top tool: {t} ({n}x)", "skill": "Top skill: {t} ({n}x)", "model": "Main model: {t} ({n} chats)",
           "word": "Word of the year: {w} ({n} messages)", "polite": "Manners: {n}x polite, swear jar {j}",
           "late": "Latest message: {c} on {d}", "cron": "Jobs that ran without you: {n}",
           "proj": "Projects started: {s}, archived: {c}", "folders": "Folders worked in: {s}, quiet for 30 days: {c}",
           "cards": "Cards ({n}): {d}", "png": "PNG ({n}) rendered with {b}", "nopng": "No headless Chrome or "
           "Chromium found, HTML only. Open index.html in a browser, or set browser_path.",
           "titles": "Session titles are hidden. Use --show-titles to show them.",
           "local": "Counted locally from state.db. Nothing left your machine."},
    "de": {"head": "Hermes Wrapped {p}", "none": "In diesem Zeitraum gibt es noch keine Gespräche.",
           "type": "Dein Typ: {n} ({c})", "vol": "{s} {chats}, {m} {msgs} von dir, {d} {days}",
           "tool": "Top-Tool: {t} ({n}x)", "skill": "Top-Skill: {t} ({n}x)", "model": "Hauptmodell: {t} ({n} Chats)",
           "word": "Wort des Jahres: {w} ({n} Nachrichten)", "polite": "Manieren: {n}x höflich, Schimpfglas {j}",
           "late": "Späteste Nachricht: {c} am {d}", "cron": "Jobs, die ohne dich liefen: {n}",
           "proj": "Projekte angefangen: {s}, archiviert: {c}",
           "folders": "Ordner mit Arbeit: {s}, seit 30 Tagen still: {c}",
           "cards": "Karten ({n}): {d}", "png": "PNG ({n}) erzeugt mit {b}", "nopng": "Kein Headless-Chrome oder "
           "Chromium gefunden, nur HTML. index.html im Browser öffnen oder browser_path setzen.",
           "titles": "Session-Titel sind ausgeblendet. Mit --show-titles einblenden.",
           "local": "Lokal aus state.db gezählt. Nichts hat deinen Rechner verlassen."},
}


def summary_text(st: _stats.Stats, lang: str) -> str:
    s = SUMMARY[lang]
    f = lambda n: _cards.fmt_int(n, lang)  # noqa: E731
    lines = [s["head"].format(p=_cards.period_label(st, lang))]
    if not st.user_messages:
        lines.append(s["none"])
        return "\n".join(lines)
    u = _cards.unit
    lines.append(s["vol"].format(s=f(st.sessions), m=f(st.user_messages), d=f(st.active_days),
                                 chats=u(lang, "chat", st.sessions), msgs=u(lang, "msg", st.user_messages),
                                 days=u(lang, "day", st.active_days)))
    if st.persona:
        lines.append(s["type"].format(n=_cards.persona_name(st.persona["code"], lang),
                                      c="·".join(_cards.AXIS_CODES[c] for c in st.persona["code"])))
    if st.tools:
        t, n = st.tools.most_common(1)[0]
        lines.append(s["tool"].format(t=t, n=f(n)))
    if st.skills:
        t, n = st.skills.most_common(1)[0]
        lines.append(s["skill"].format(t=t, n=f(n)))
    if st.models:
        t, n = st.models.most_common(1)[0]
        lines.append(s["model"].format(t=t, n=f(n)))
    if st.words:
        lines.append(s["word"].format(w=st.words[0][0], n=f(st.words[0][1])))
    lines.append(s["polite"].format(n=f(st.polite_total), j=f(st.swear_total)))
    if st.latest_clock:
        lines.append(s["late"].format(c=st.latest_clock, d=_cards.fmt_date(st.latest_date, lang)))
    if st.cron_runs:
        lines.append(s["cron"].format(n=f(st.cron_runs)))
    if st.projects_source == "projects":
        lines.append(s["proj"].format(s=f(st.projects_started), c=f(st.projects_closed)))
    elif st.projects_source == "folders":
        lines.append(s["folders"].format(s=f(st.projects_started), c=f(st.projects_closed)))
    return "\n".join(lines)


def _result_lines(res: dict, lang: str, show_titles: bool) -> list[str]:
    s = SUMMARY[lang]
    out = ["", s["cards"].format(n=len(res["html"]), d=res["dir"]), str(res["dir"] / "index.html")]
    if res["png"]:
        out.append(s["png"].format(n=len(res["png"]), b=os.path.basename(res["browser"] or "")))
    elif res.get("png_wanted"):
        out.append(s["nopng"])
    if not show_titles:
        out.append(s["titles"])
    out.append(s["local"])
    return out


# ---------------------------------------------------------------------------------------
# hermes wrapped
# ---------------------------------------------------------------------------------------

def _cli_setup(parser) -> None:
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--year", type=int, default=None, help="calendar year (default: this year)")
    g.add_argument("--days", type=int, default=None, help="only the last N days")
    g.add_argument("--all", action="store_true", help="the whole history")
    parser.add_argument("--lang", choices=["en", "de"], default=None, help="card language (default: setting, then auto)")
    parser.add_argument("--tz", default="", help="IANA timezone for hours and days, e.g. Europe/Berlin")
    parser.add_argument("--show-titles", action="store_true", help="show the session title on the marathon card")
    parser.add_argument("--rename", action="append", default=[], metavar="OLD=NEW",
                        help="show a word under another name, e.g. a client name as a code name (repeatable)")
    parser.add_argument("--out", default=None, metavar="DIR", help="write the cards here instead of plugin-data")
    parser.add_argument("--no-png", action="store_true", help="HTML only, do not start a headless browser")
    parser.add_argument("--json", action="store_true", help="print the raw numbers as JSON, write no cards")


def _cli_handler(args) -> int:
    try:
        show = bool(args.show_titles or _cfg("show_titles"))
        st = build_stats(year=args.year, days=args.days if args.days and args.days > 0 else None,
                         all_time=args.all, tz_name=args.tz, show_titles=show,
                         renames=getattr(args, "rename", None) or [])
        if args.json:
            print(_stats.dumps(st))
            return 0
        lang = _lang(st, args.lang or "")
        print(summary_text(st, lang))
        res = write_cards(st, lang=lang, show_titles=show, out=Path(args.out) if args.out else None,
                          png=not args.no_png)
        res["png_wanted"] = not args.no_png
        print("\n".join(_result_lines(res, lang, show)))
        return 0
    except Exception as exc:
        logger.warning("hermes-wrapped failed: %s", exc)
        print(f"hermes-wrapped: could not build your wrapped ({type(exc).__name__}: {exc}).")
        return 1


# ---------------------------------------------------------------------------------------
# /wrapped
# ---------------------------------------------------------------------------------------

USAGE = ("/wrapped            this year: summary and HTML cards\n"
         "/wrapped 2025       a calendar year\n"
         "/wrapped 30         the last 30 days\n"
         "/wrapped all        the whole history\n"
         "/wrapped json       raw numbers\n"
         "PNG cards: run 'hermes wrapped' in a terminal.")


def slash_wrapped(raw_args: str = "", **_kw) -> str:
    try:
        toks = (raw_args or "").lower().split()
        if any(t in ("help", "-h", "--help", "?") for t in toks):
            return USAGE
        year = days = None
        for t in toks:
            if re.fullmatch(r"(19|20)\d\d", t):
                year = int(t)
            elif re.fullmatch(r"\d{1,4}d?", t) and int(t.rstrip("d")) > 0:
                days = int(t.rstrip("d"))
        show = bool(_cfg("show_titles"))
        st = build_stats(year=year, days=None if year else days, all_time="all" in toks, show_titles=show)
        if "json" in toks:
            return _stats.dumps(st)
        lang = _lang(st)
        text = summary_text(st, lang)
        if st.user_messages:
            res = write_cards(st, lang=lang, show_titles=show, png=False)
            text += "\n" + "\n".join(_result_lines(res, lang, show))
        return text
    except Exception as exc:  # never break the chat
        logger.warning("hermes-wrapped: /wrapped failed: %s", exc)
        return f"hermes-wrapped: could not read the history ({type(exc).__name__})."


def register(ctx) -> None:
    global _ctx
    _ctx = ctx
    ctx.register_command("wrapped", slash_wrapped,
                         description="Your year with your agent: summary and story cards from your own history",
                         args_hint="[2026|30|all|json]")
    ctx.register_cli_command("wrapped", "Your year with your agent as shareable story cards",
                             _cli_setup, _cli_handler,
                             description="Reads state.db locally (read only) and writes story cards, 1080x1920, "
                                         "as HTML plus PNG when a headless Chrome is installed.")
