"""Story cards for hermes-wrapped: self-contained HTML, 1080 x 1920 each.

No external fonts, scripts or images: every file works offline and leaks nothing.
Top 150 px and bottom 170 px hold no key content (story app overlays).
Every number on a card comes from the user's own history (see stats.py).
"""
from __future__ import annotations

import datetime as _dt
import html
from typing import Callable, Optional

from . import manners as _m
from .stats import Stats

REPO_HINT = "github.com/MadeByBrain/hermes-extensions"
HP_TOKENS = 1_410_000      # Harry Potter 1 to 7: about 1.08 M words, about 1.3 tokens per word
HOBBIT_TOKENS = 124_000    # The Hobbit: about 95,000 words
PAGE_TOKENS = 400          # one novel page: about 300 words

MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"],
    "de": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
           "November", "Dezember"],
}

# ------------------------------------------------------------------------------------------
# Persona types: N/D night or day, B/A build or ask, T/C terminal or chat, L/M loyal or multi
# ------------------------------------------------------------------------------------------

PERSONAS = {
    "NBTM": ("🌙", "The 3 AM Architect", "Der 3-Uhr-Architekt",
             "You build systems while others sleep. Terminal first, and every model gets a shift.",
             "Du baust Systeme, während andere schlafen. Terminal zuerst, und jedes Modell bekommt eine Schicht."),
    "NBTL": ("🔧", "The Midnight Mechanic", "Der Mitternachtsmechaniker",
             "Night shift, one terminal, one model. You fix things nobody asked about until morning.",
             "Nachtschicht, ein Terminal, ein Modell. Du reparierst bis zum Morgen Dinge, nach denen keiner gefragt hat."),
    "NBCM": ("🏗️", "The Insomniac Foreman", "Der schlaflose Polier",
             "You run the building site from a chat window at night and hire whichever model is awake.",
             "Du leitest die Baustelle nachts aus dem Chatfenster und heuerst an, welches Modell gerade wach ist."),
    "NBCL": ("🌕", "The Moonlight Builder", "Der Mondschein-Baumeister",
             "Late hours, one trusted model, and a chat that keeps turning into working code.",
             "Späte Stunden, ein Modell deines Vertrauens und ein Chat, aus dem ständig funktionierender Code wird."),
    "NATM": ("🔦", "The Nocturnal Interrogator", "Der nächtliche Verhörer",
             "You question every model you can reach, in a terminal, long after midnight.",
             "Du verhörst jedes Modell, das du erreichen kannst. Im Terminal, lange nach Mitternacht."),
    "NATL": ("🦉", "The Terminal Owl", "Die Terminal-Eule",
             "Quiet terminal, dark room, one model you trust. You ask, it answers, nobody else is awake.",
             "Stilles Terminal, dunkles Zimmer, ein Modell deines Vertrauens. Du fragst, es antwortet, sonst ist niemand wach."),
    "NACM": ("🍷", "The 2 AM Philosopher", "Der 2-Uhr-Philosoph",
             "Big questions after dark, asked to as many models as possible.",
             "Große Fragen nach Einbruch der Dunkelheit, gestellt an so viele Modelle wie möglich."),
    "NACL": ("🕯️", "The Late Night Confidant", "Der Mitternachts-Vertraute",
             "Your agent hears your best ideas at night. Always the same model, always in chat.",
             "Deine besten Ideen hört dein Agent nachts. Immer dasselbe Modell, immer im Chat."),
    "DBTM": ("🤹", "The Model Juggler", "Der Modell-Jongleur",
             "Office hours, terminal open, a different model for every job.",
             "Bürozeiten, Terminal offen, für jeden Job ein anderes Modell."),
    "DBTL": ("⏱️", "The Clockwork Builder", "Der Uhrwerk-Baumeister",
             "Reliable as a clock: daytime, terminal, one model, things get built.",
             "Zuverlässig wie ein Uhrwerk: tagsüber, Terminal, ein Modell, und es wird gebaut."),
    "DBCM": ("🦺", "The Chatty Contractor", "Der gesprächige Bauleiter",
             "You run your building site from a chat window and switch models like subcontractors.",
             "Du leitest deine Baustelle aus dem Chatfenster und wechselst Modelle wie Subunternehmer."),
    "DBCL": ("🧱", "The Steady Foreman", "Der verlässliche Vorarbeiter",
             "Daylight, one chat, one model. You keep the site running without drama.",
             "Tageslicht, ein Chat, ein Modell. Bei dir läuft die Baustelle ohne Drama."),
    "DATM": ("🧳", "The Benchmark Tourist", "Der Benchmark-Tourist",
             "You ask five models the same question just to compare. In a terminal. During office hours.",
             "Du stellst fünf Modellen dieselbe Frage, nur zum Vergleich. Im Terminal. Zu Bürozeiten."),
    "DATL": ("🧘", "The Command Line Monk", "Der Kommandozeilen-Mönch",
             "Calm, focused, one model, plain commands. Enlightenment by daylight.",
             "Ruhig, konzentriert, ein Modell, schlichte Befehle. Erleuchtung bei Tageslicht."),
    "DACM": ("🍇", "The Model Sommelier", "Der Modell-Sommelier",
             "You taste every model and know exactly which vintage answers best.",
             "Du verkostest jedes Modell und weißt genau, welcher Jahrgang am besten antwortet."),
    "DACL": ("💌", "The Loyal Pen Pal", "Der treue Brieffreund",
             "Steady correspondence with one model. Daytime, chat, always a good question.",
             "Stetiger Briefwechsel mit einem Modell. Tagsüber, im Chat, immer mit einer guten Frage."),
}
AXIS_CODES = {"N": "NGT", "D": "DAY", "B": "BLD", "A": "ASK", "T": "TRM", "C": "CHT", "L": "ONE", "M": "MLT"}


def persona_name(code: str, lang: str) -> str:
    p = PERSONAS.get(code)
    return "" if not p else (p[2] if lang == "de" else p[1])


# ------------------------------------------------------------------------------------------
# Text
# ------------------------------------------------------------------------------------------

T = {
    "en": {
        "wrapped": "Hermes Wrapped", "all": "all time", "days": "last {d} days",
        "cover_big": "{conv} with your agent.",
        "cover_sub": "{d} {days}. {m} {msgs} typed by you.",
        "cover_hook": "Let's see what that says about you.",
        "your_type": "Your type", "type_of": "1 of 16 types",
        "ax_night": "{p}% of your messages after 10 PM", "ax_day": "Only {p}% of your messages after 10 PM",
        "ax_build": "{p}% of your chats ran commands or wrote files",
        "ax_ask": "{p}% of your chats ran commands or wrote files",
        "ax_term": "{p}% typed in a terminal", "ax_chat": "{p}% typed in a terminal, the rest in chat apps",
        "ax_loyal": "{p}% of your chats with {m}", "ax_multi": "Only {p}% of your chats with {m}, your favourite",
        "tools_k": "Your top {n} tools", "tools_k1": "Your top tool",
        "tools_terminal": "You don't chat.<br>You run commands.",
        "tools_read": "You read more<br>than you write.",
        "tools_web": "Curiosity,<br>automated.",
        "tools_write": "Words in,<br>files out.",
        "tools_other": "Your agent's<br>favourite toys.",
        "skill_k": "Most used skill", "skill_line": "loaded {n}× by your agent.",
        "skill_more": "{k} different skills in total. Your agent reads the manual. Do you?",
        "manners_k": "Manners", "said": "you said", "manners_tok": "Your politeness cost about <b>{t} tokens</b>. Less than a cent. Keep going.",
        "jar_k": "Swear jar", "jar": "{n} {coins}. Top word: {w}", "jar_empty": "Empty. Suspiciously clean.",
        "rank": "Rank",
        "night_k": "Night shift", "night_line": "Your latest message.",
        "night_awake": "{date}. Your agent was awake. Were you?",
        "night_early": "{date}. In bed before 2 AM. Respect.",
        "night_deep": "{n} messages between 2 and 5 AM.",
        "night_late": "{n} messages after 10 PM.",
        "night_none": "Not a single message after 10 PM. Who are you?",
        "mara_k": "Longest conversation", "mara_line": "messages in one session.",
        "mara_date": "Started {date}.", "mara_avg": "Your average chat: {a} messages.", "mara_x": "{x}× longer.", "mara_hidden": "Title hidden. You choose what to show.",
        "tok_k": "Tokens processed", "tok_line": "tokens. That is roughly",
        "tok_hp": "the complete Harry Potter series.", "tok_hobbit": "The Hobbit.", "tok_pages": "{p} of a novel.", "tok_lt_page": "less than one page of a novel.",
        "tok_cache": "Plus {c} read from cache. Your agent has a very good memory.",
        "tok_note": "1 token ≈ 0.75 words. Harry Potter 1 to 7 ≈ 1.08 M words.",
        "crew_k": "Your night crew", "crew_line": "jobs ran without you.",
        "crew_sub": "Plus {n} subagents you sent off to work.",
        "crew_punch": "You are not a user.<br>You are a manager.",
        "model_k": "Your main model", "model_line": "{n} {chats} together.",
        "model_cheat": "But you cheated. {n} times with {m}.",
        "status": "Relationship status:", "st_excl": "Exclusive.", "st_compl": "It's complicated.",
        "st_open": "Open relationship.",
        "proj_k": "Projects", "proj_started": "projects started.", "proj_closed": "{n} archived.",
        "proj_folders": "folders you worked in.", "proj_quiet": "{n} quiet for 30 days or more.",
        "proj_lo": "Starting is your superpower.", "proj_mid": "A healthy mix of starting and finishing.",
        "proj_hi": "Rare species: a finisher.",
        "word_k": "Word of the year", "word_line": "in {n} of your messages.", "word_runners": "Runners-up",
        "sum_sessions": "chats", "sum_msgs": "messages", "sum_tools": "tool calls", "sum_polite": "× \"{w}\"",
        "sum_tokens": "tokens", "sum_latest": "latest message", "sum_cron": "cron jobs", "sum_hp": "Harry Potter",
        "sum_top_tool": "Top tool", "sum_top_model": "Top model", "sum_busiest": "Busiest day",
        "sum_word": "Word of the year", "sum_msgs_day": "{n} {msgs}",
        "foot_local": "Counted locally. Nothing uploaded.",
    },
    "de": {
        "wrapped": "Hermes Wrapped", "all": "gesamt", "days": "letzte {d} Tage",
        "cover_big": "{conv} mit deinem Agenten.",
        "cover_sub": "{d} {days}. {m} {msgs} von dir getippt.",
        "cover_hook": "Mal sehen, was das über dich verrät.",
        "your_type": "Dein Typ", "type_of": "1 von 16 Typen",
        "ax_night": "{p} % deiner Nachrichten nach 22 Uhr", "ax_day": "Nur {p} % deiner Nachrichten nach 22 Uhr",
        "ax_build": "{p} % deiner Chats mit Befehlen oder geschriebenen Dateien",
        "ax_ask": "{p} % deiner Chats mit Befehlen oder geschriebenen Dateien",
        "ax_term": "{p} % im Terminal getippt", "ax_chat": "{p} % im Terminal getippt, der Rest in Chat-Apps",
        "ax_loyal": "{p} % deiner Chats mit {m}", "ax_multi": "Nur {p} % deiner Chats mit {m}, deinem Favoriten",
        "tools_k": "Deine Top {n} Tools", "tools_k1": "Dein Top-Tool",
        "tools_terminal": "Du chattest nicht.<br>Du gibst Befehle.",
        "tools_read": "Du liest mehr,<br>als du schreibst.",
        "tools_web": "Neugier,<br>automatisiert.",
        "tools_write": "Worte rein,<br>Dateien raus.",
        "tools_other": "Das Lieblings&shy;spielzeug deines Agenten.",
        "skill_k": "Meistgenutzter Skill", "skill_line": "{n}× von deinem Agenten geladen.",
        "skill_more": "{k} verschiedene Skills insgesamt. Dein Agent liest die Anleitung. Du auch?",
        "manners_k": "Manieren", "said": "hast du gesagt",
        "manners_tok": "Deine Höflichkeit hat etwa <b>{t} Tokens</b> gekostet. Weniger als ein Cent. Weiter so.",
        "jar_k": "Schimpfglas", "jar": "{n} {coins}. Lieblingswort: {w}", "jar_empty": "Leer. Verdächtig sauber.",
        "rank": "Rang",
        "night_k": "Nachtschicht", "night_line": "Deine späteste Nachricht.",
        "night_awake": "{date}. Dein Agent war wach. Und du?",
        "night_early": "{date}. Vor 2 Uhr im Bett. Respekt.",
        "night_deep": "{n} Nachrichten zwischen 2 und 5 Uhr.",
        "night_late": "{n} Nachrichten nach 22 Uhr.",
        "night_none": "Keine einzige Nachricht nach 22 Uhr. Wer bist du?",
        "mara_k": "Längstes Gespräch", "mara_line": "Nachrichten in einer Session.",
        "mara_date": "Begonnen am {date}.", "mara_avg": "Dein durchschnittlicher Chat: {a} Nachrichten.", "mara_x": "{x}× länger.", "mara_hidden": "Titel ausgeblendet. Du entscheidest, was du zeigst.",
        "tok_k": "Verarbeitete Tokens", "tok_line": "Tokens. Das ist ungefähr",
        "tok_hp": "alle sieben Bände Harry Potter.", "tok_hobbit": "Der Hobbit.", "tok_pages": "{p} eines Romans.", "tok_lt_page": "weniger als eine Romanseite.",
        "tok_cache": "Dazu {c} aus dem Cache gelesen. Dein Agent hat ein sehr gutes Gedächtnis.",
        "tok_note": "1 Token ≈ 0,75 Wörter. Harry Potter 1 bis 7 ≈ 1,08 Mio. Wörter.",
        "crew_k": "Deine Nachtschicht-Crew", "crew_line": "Jobs liefen ohne dich.",
        "crew_sub": "Dazu {n} Subagenten, die du losgeschickt hast.",
        "crew_punch": "Du bist kein Nutzer.<br>Du bist Manager.",
        "model_k": "Dein Hauptmodell", "model_line": "{n} {chats} zusammen.",
        "model_cheat": "Aber du bist fremdgegangen. {n}× mit {m}.",
        "status": "Beziehungsstatus:", "st_excl": "Exklusiv.", "st_compl": "Es ist kompliziert.",
        "st_open": "Offene Beziehung.",
        "proj_k": "Projekte", "proj_started": "Projekte angefangen.", "proj_closed": "{n} archiviert.",
        "proj_folders": "Ordner, in denen du gearbeitet hast.", "proj_quiet": "{n} davon seit 30 Tagen still.",
        "proj_lo": "Anfangen ist deine Superkraft.", "proj_mid": "Gesunde Mischung aus Anfangen und Abschließen.",
        "proj_hi": "Seltene Spezies: jemand, der abschließt.",
        "word_k": "Wort des Jahres", "word_line": "in {n} deiner Nachrichten.", "word_runners": "Knapp dahinter",
        "sum_sessions": "Chats", "sum_msgs": "Nachrichten", "sum_tools": "Tool-Aufrufe", "sum_polite": "× „{w}“",
        "sum_tokens": "Tokens", "sum_latest": "späteste Nachricht", "sum_cron": "Cron-Jobs", "sum_hp": "Harry Potter",
        "sum_top_tool": "Top-Tool", "sum_top_model": "Top-Modell", "sum_busiest": "Aktivster Tag",
        "sum_word": "Wort des Jahres", "sum_msgs_day": "{n} {msgs}",
        "foot_local": "Lokal gezählt. Nichts hochgeladen.",
    },
}


# ------------------------------------------------------------------------------------------
# Formatting helpers
# ------------------------------------------------------------------------------------------

def fmt_int(n, lang: str) -> str:
    s = f"{int(round(n)):,}"
    return s.replace(",", ".") if lang == "de" else s


def fmt_big(n: float, lang: str) -> str:
    """1.43 B, 11.1 B, 51.8K: short form for big counts."""
    for div, en, de in ((1e9, " B", " Mrd."), (1e6, " M", " Mio."), (1e3, "K", " Tsd.")):
        if n >= div:
            v = n / div
            s = f"{v:.1f}" if v < 100 else f"{v:.0f}"
            s = s[:-2] if s.endswith(".0") else s
            return (s.replace(".", ",") + de) if lang == "de" else (s + en)
    return fmt_int(n, lang)


def fmt_date(iso: Optional[str], lang: str) -> str:
    if not iso:
        return ""
    d = _dt.date.fromisoformat(iso)
    return f"{d.day}. {MONTHS['de'][d.month - 1]}" if lang == "de" else f"{d.day} {MONTHS['en'][d.month - 1]}"


UNITS = {
    "en": {"day": ("active day", "active days"), "msg": ("message", "messages"), "chat": ("chat", "chats"), "conv": ("conversation", "conversations"),
           "call": ("tool call", "tool calls"), "coin": ("coin", "coins"), "page": ("page", "pages")},
    "de": {"day": ("aktiver Tag", "aktive Tage"), "msg": ("Nachricht", "Nachrichten"), "chat": ("Chat", "Chats"), "conv": ("Gespräch", "Gespräche"),
           "call": ("Tool-Aufruf", "Tool-Aufrufe"), "coin": ("Münze", "Münzen"), "page": ("Seite", "Seiten")},
}


def unit(lang: str, key: str, n: int) -> str:
    one, many = UNITS.get(lang, UNITS["en"])[key]
    return one if n == 1 else many


def pct(x: float) -> int:
    return int(round(100 * x))


def fit(text: str, width: int, base: int, factor: float = 0.6) -> int:
    """Font size so a single line of heavy sans text fits into width px."""
    n = max(1, len(text))
    return int(max(40, min(base, width / (n * factor))))


def e(text) -> str:
    """Escape for HTML and glue a short last word to the one before it (no lone word on the last line)."""
    out = html.escape(str(text))
    head, _sp, tail = out.rpartition(" ")
    # Sentences (ending in . ! ?) keep their last word company; titles without a full stop stay breakable.
    limit = 16 if out.rstrip().endswith((".", "!", "?")) else 7
    if out.count(" ") >= 2 and len(out) > 24 and len(tail) <= limit:
        out = head + "&nbsp;" + tail
    return out

CSS_BASE = """
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:1080px;height:1920px;overflow:hidden}
body{font-family:'Inter',-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#fff;
padding:200px 84px 210px;display:flex;flex-direction:column;position:relative;
-webkit-font-smoothing:antialiased}
.mono{font-family:'JetBrains Mono',ui-monospace,Menlo,Consolas,monospace}
.k{font:700 34px 'JetBrains Mono',ui-monospace,Menlo,monospace;letter-spacing:.16em;text-transform:uppercase;opacity:.85}
.big{font-weight:900;letter-spacing:-.045em;line-height:.95}
.line{font-size:58px;font-weight:650;line-height:1.25;letter-spacing:-.01em}
.small{font-size:42px;font-weight:550;line-height:1.3}
.muted{opacity:.82}
.grow{flex:1}
.foot{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;
font:600 23px 'JetBrains Mono',ui-monospace,Menlo,monospace;opacity:.85;white-space:nowrap;line-height:1.4}
.foot b{font-weight:800;opacity:1;font-size:30px}
.foot .r{text-align:right}
.layer{position:absolute;inset:0;pointer-events:none}
.content{position:relative;display:flex;flex-direction:column;height:100%}
/* the block between kicker and footer sits in the optical middle of the card */
.content>.k+*{margin-top:auto!important}.content>.foot{margin-top:auto;padding-top:60px}
"""


def page(title: str, css: str, body: str, foot_color: str = "") -> str:
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=1080">'
            f"<title>{e(title)}</title><style>{CSS_BASE}{css}</style></head><body>{body}</body></html>")


def foot(t: dict, period: str, style: str = "") -> str:
    return (f'<div class="foot" style="{style}"><div><b>$ hermes wrapped</b><br>{e(period)}</div>'
            f'<div class="r">{e(t["foot_local"])}<br>{e(REPO_HINT)}</div></div>')


# ------------------------------------------------------------------------------------------
# Cards. Each returns (slug, html) or None when there is nothing honest to show.
# ------------------------------------------------------------------------------------------

def card_cover(st: Stats, t, lang, period, **_):
    n = st.sessions
    css = (".bg{background:radial-gradient(circle at 18% 14%,#ff3d7f 0,transparent 42%),"
           "radial-gradient(circle at 88% 72%,#6c3dff 0,transparent 48%),"
           "radial-gradient(circle at 30% 95%,#ff9d3d55 0,transparent 40%),#120a24}")
    body = (f'<div class="layer bg"></div><div class="content">'
            f'<div class="k">{e(t["wrapped"])} {e(period)}</div>'
            f'<div class="big" style="font-size:{fit(fmt_int(n, lang), 900, 330)}px;margin-top:330px">{fmt_int(n, lang)}</div>'
            f'<div class="line" style="margin-top:40px">{e(t["cover_big"].format(conv=unit(lang, "conv", n)))}</div>'
            f'<div class="small muted" style="margin-top:22px">'
            f'{e(t["cover_sub"].format(d=fmt_int(st.active_days, lang), m=fmt_int(st.user_messages, lang), days=unit(lang, "day", st.active_days), msgs=unit(lang, "msg", st.user_messages)))}</div>'
            f'<div class="line" style="margin-top:110px;font-size:66px;font-weight:800">{e(t["cover_hook"])}</div>'
            f'{foot(t, period)}</div>')
    return "cover", page("Hermes Wrapped", css, body)


def card_persona(st: Stats, t, lang, period, **_):
    p = st.persona
    if not p:
        return None
    code = p["code"]
    emoji, en_name, de_name, en_desc, de_desc = PERSONAS[code]
    name, desc = (de_name, de_desc) if lang == "de" else (en_name, en_desc)
    ax = [
        t["ax_night" if code[0] == "N" else "ax_day"].format(p=pct(p["night"])),
        t["ax_build" if code[1] == "B" else "ax_ask"].format(p=pct(p["build"])),
        t["ax_term" if code[2] == "T" else "ax_chat"].format(p=pct(p["terminal"])),
        t["ax_loyal" if code[3] == "L" else "ax_multi"].format(p=pct(p["loyal"]), m=p["top_model"] or "?"),
    ]
    rows = "".join(
        f'<div class="ax"><div class="axc mono">{AXIS_CODES[c]}</div><div class="axt">{e(txt)}</div></div>'
        for c, txt in zip(code, ax))
    css = (".bg{background:linear-gradient(160deg,#0d1b3d,#05070f 62%)}"
           ".holo{background:conic-gradient(from 200deg at 72% 26%,transparent,#3fd0ff40,#c66bff40,#ff6bd540,transparent 42%)}"
           ".emo{font-size:190px;line-height:1;margin-top:70px}"
           ".ax{display:flex;gap:26px;align-items:baseline;margin-top:22px}"
           ".axc{color:#8fe8ff;font-weight:800;font-size:32px;min-width:96px}"
           ".axt{font-size:35px;font-weight:550;line-height:1.3;opacity:.92}"
           ".code{color:#8fe8ff;font-size:32px;font-weight:700;letter-spacing:.12em;margin-top:44px}")
    size = fit(max(name.split(" "), key=len), 910, 132, 0.62)
    body = (f'<div class="layer bg"></div><div class="layer holo"></div><div class="content">'
            f'<div class="k" style="color:#3fd0ff">{e(t["your_type"])}</div>'
            f'<div class="emo">{emoji}</div>'
            f'<div class="big" style="font-size:{size}px;margin-top:34px;line-height:1.08">{e(name)}</div>'
            f'<div class="small" style="margin-top:38px;font-size:42px">{e(desc)}</div>'
            f'<div style="margin-top:46px">{rows}</div>'
            f'<div class="code mono">{"·".join(AXIS_CODES[c] for c in code)} &nbsp; {e(t["type_of"])}</div>'
            f'{foot(t, period, "color:#bfeaff")}</div>')
    return "persona", page(name, css, body)


def card_tools(st: Stats, t, lang, period, **_):
    top = st.tools.most_common(5)
    if not top:
        return None
    first = top[0][0]
    if first in ("terminal", "execute_code", "process"):
        head = t["tools_terminal"]
    elif first in ("read_file", "search_files", "session_search"):
        head = t["tools_read"]
    elif first.startswith("web_") or first.startswith("browser"):
        head = t["tools_web"]
    elif first in ("write_file", "patch"):
        head = t["tools_write"]
    else:
        head = t["tools_other"]
    mx = top[0][1]
    rows = "".join(
        f'<div class="row"><span>{i} &nbsp;{e(name)}</span><span>{fmt_int(n, lang)}</span></div>'
        f'<div class="bar" style="width:{max(4, round(100 * n / mx))}%"></div>'
        for i, (name, n) in enumerate(top, 1))
    css = ("body{background:#d7ff3d;color:#0b0b0f}"
           ".row{display:flex;justify-content:space-between;font-weight:800;font-size:46px;margin-top:40px;letter-spacing:-.01em}"
           ".bar{height:62px;border-radius:14px;background:#0b0b0f;margin-top:14px}"
           ".total{font-size:40px;font-weight:650;margin-top:56px}")
    total = sum(st.tools.values())
    kick = t["tools_k"].format(n=len(top)) if len(top) > 1 else t["tools_k1"]
    body = (f'<div class="content"><div class="k">{e(kick)}</div>'
            f'<div class="big" style="font-size:116px;margin:60px 0 34px">{head}</div>{rows}'
            f'<div class="total">{e(fmt_int(total, lang))} {e(unit(lang, "call", total))}</div>'
            f'{foot(t, period)}</div>')
    return "tools", page("Top tools", css, body)


def card_skill(st: Stats, t, lang, period, **_):
    top = st.skills.most_common(5)
    if not top:
        return None
    name, n = top[0]
    rest = "".join(f'<div class="sk"><span>{i}</span><b>{e(s)}</b><em>{fmt_int(c, lang)}×</em></div>'
                   for i, (s, c) in enumerate(top[1:], 2))
    css = ("body{background:linear-gradient(165deg,#00e0c6 0%,#00b3ff 100%);color:#03222b}"
           ".book{font-size:150px;line-height:1;margin-top:80px}"
           ".sk{display:flex;gap:26px;align-items:baseline;font-size:42px;margin-top:24px}"
           ".sk span{font:800 32px 'JetBrains Mono',monospace;opacity:.6;min-width:40px}"
           ".sk b{font-weight:800;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}"
           ".sk em{font-style:normal;font-weight:700;opacity:.75}"
           ".pill{display:inline-block;background:#03222b;color:#7ff6ff;border-radius:28px;padding:18px 34px 24px;"
           "font-weight:900;letter-spacing:-.03em;margin-top:40px;max-width:100%;word-break:break-word;line-height:1.05}")
    body = (f'<div class="content"><div class="k">{e(t["skill_k"])}</div>'
            f'<div class="book">📖</div>'
            f'<div><span class="pill" style="font-size:{fit(name, 840, 104, 0.6)}px">{e(name)}</span></div>'
            f'<div class="line" style="margin-top:36px">{e(t["skill_line"].format(n=fmt_int(n, lang)))}</div>'
            f'<div style="margin-top:46px">{rest}</div>'
            f'<div class="small" style="margin-top:50px;opacity:.8">{e(t["skill_more"].format(k=fmt_int(len(st.skills), lang)))}</div>'
            f'{foot(t, period)}</div>')
    return "skill", page("Most used skill", css, body)


def card_manners(st: Stats, t, lang, period, **_):
    if not st.user_messages:
        return None
    if st.polite_total:
        word, n = st.polite.most_common(1)[0]
    else:
        word, n = ("bitte" if lang == "de" else "please"), 0
    others = " · ".join(f"{fmt_int(v, lang)}× {e(k)}" for k, v in st.polite.most_common(4)[1:])
    p_rank, s_rank = _m.rank(st.polite_total, st.swear_total, st.user_messages, lang)
    coins = min(st.swear_total, 30)
    coin_html = "".join('<span class="coin"></span>' for _ in range(coins))
    if st.swear_total:
        jar_txt = t["jar"].format(n=fmt_int(st.swear_total, lang), coins=unit(lang, "coin", st.swear_total),
                                  w=st.swear.most_common(1)[0][0])
    else:
        jar_txt = t["jar_empty"]
    css = ("body{background:radial-gradient(circle at 85% 8%,#fff6e2 0,transparent 38%),"
           "linear-gradient(175deg,#ffe3b3 0%,#ffbf6e 60%,#ff9a4a 100%);color:#2b1600}"
           ".word{display:inline-block;background:#fff;border:7px solid #2b1600;border-radius:28px;padding:6px 30px 14px;"
           "font-size:96px;font-weight:900;letter-spacing:-.03em;transform:rotate(-3deg);box-shadow:12px 12px 0 #2b1600}"
           ".jar{border:9px solid #2b1600;border-top:none;border-radius:0 0 70px 70px;padding:22px;width:470px;"
           "min-height:220px;display:flex;flex-wrap:wrap;align-content:flex-end;gap:8px;background:rgba(255,255,255,.35)}"
           ".coin{width:56px;height:56px;border-radius:50%;background:radial-gradient(circle at 35% 35%,#fff1a8,#f2b631 60%,#b57b0c);"
           "box-shadow:0 3px 0 #7a5400}"
           ".stamp{display:inline-block;border:8px solid #b3261e;color:#b3261e;border-radius:22px;padding:10px 28px 14px;"
           "transform:rotate(-4deg);font-size:56px;font-weight:900;text-transform:uppercase;line-height:1;"
           "background:rgba(255,255,255,.4)}")
    body = (f'<div class="content"><div class="k">{e(t["manners_k"])}</div>'
            f'<div style="display:flex;align-items:flex-end;gap:28px;margin-top:50px">'
            f'<div class="big" style="font-size:{fit(fmt_int(n, lang) + "×", 560, 230)}px">{fmt_int(n, lang)}×</div>'
            f'<div class="line" style="padding-bottom:24px">{e(t["said"])}</div></div>'
            f'<div style="margin-top:26px"><span class="word">{e(word)}</span></div>'
            + (f'<div class="small" style="margin-top:44px;font-weight:700">{others}</div>' if others else "")
            + f'<div class="small" style="margin-top:22px">{t["manners_tok"].format(t=e(fmt_int(st.polite_tokens, lang)))}</div>'
            f'<div class="k" style="margin-top:60px">{e(t["jar_k"])}</div>'
            f'<div style="display:flex;gap:40px;align-items:flex-end;margin-top:20px"><div class="jar">{coin_html}</div>'
            f'<div class="small" style="font-weight:700">{e(jar_txt)}</div></div>'
            f'<div style="margin-top:56px;display:flex;align-items:center;gap:30px"><span class="stamp">{e(p_rank)}</span>'
            f'<span class="small" style="font-weight:800">{e(s_rank)}</span></div>'
            f'{foot(t, period)}</div>')
    return "manners", page("Manners", css, body)


def card_night(st: Stats, t, lang, period, **_):
    if not st.latest_clock:
        return None
    hour = int(st.latest_clock[:2])
    date = fmt_date(st.latest_date, lang)
    sub = t["night_awake" if 2 <= hour < 5 else "night_early"].format(date=date)
    if 5 <= hour < 22:
        sub = date + "."
    if st.deep_night_messages:
        extra = t["night_deep"].format(n=fmt_int(st.deep_night_messages, lang))
    elif st.night_messages:
        extra = t["night_late"].format(n=fmt_int(st.night_messages, lang))
    else:
        extra = t["night_none"]
    css = ("body{background:linear-gradient(180deg,#05061a,#1b1550 70%,#2d1f6e)}"
           ".moon{position:absolute;right:120px;top:170px;width:200px;height:200px;border-radius:50%;"
           "background:#f5f1c8;box-shadow:0 0 120px #f5f1c877}"
           ".moon:after{content:'';position:absolute;left:-60px;top:-30px;width:200px;height:200px;border-radius:50%;"
           "background:#0b0b2a;opacity:0}"
           ".star{position:absolute;width:8px;height:8px;border-radius:50%;background:#fff;opacity:.7}")
    stars = "".join(f'<div class="star" style="left:{x}px;top:{y}px"></div>'
                    for x, y in ((140, 300), (330, 210), (520, 360), (760, 520), (230, 610), (900, 680), (610, 160)))
    body = (f'<div class="layer">{stars}<div class="moon"></div></div><div class="content">'
            f'<div class="k">{e(t["night_k"])}</div>'
            f'<div class="big mono" style="font-size:300px;letter-spacing:-.06em">{e(st.latest_clock)}</div>'
            f'<div class="line" style="margin-top:40px">{e(t["night_line"])}</div>'
            f'<div class="small muted" style="margin-top:14px">{e(sub)}</div>'
            f'<div class="line" style="margin-top:80px;font-size:56px;color:#f5f1c8">{e(extra)}</div>'
            f'{foot(t, period)}</div>')
    return "night", page("Night shift", css, body)


def card_marathon(st: Stats, t, lang, period, show_titles=False, **_):
    if st.longest_messages < 2:
        return None
    title = st.longest_title.strip() if show_titles else ""
    css = ("body{background:linear-gradient(170deg,#ff7a1f,#ff4b1f 60%,#e8301b)}"
           ".bars{margin-top:80px}.bars div{height:70px;border-radius:16px;margin-top:18px}"
           ".b1{background:#fff;width:100%}.b2{background:#2b0d00}")
    title_html = (f'<div class="line" style="margin-top:56px;font-size:64px;font-weight:800">“{e(title[:80])}”</div>'
                  if title else f'<div class="small muted" style="margin-top:56px">{e(t["mara_hidden"])}</div>')
    n = fmt_int(st.longest_messages, lang)
    avg_html = ""
    ratio = st.longest_messages / st.avg_messages if st.avg_messages >= 1 else 0
    if ratio >= 1.5:
        x = fmt_int(ratio, lang) if ratio >= 10 else f"{ratio:.1f}".replace(".", "," if lang == "de" else ".")
        w_avg = max(2.0, 100.0 / ratio)
        avg_html = (f'<div class="bars"><div class="b1"></div><div class="b2" style="width:{w_avg:.1f}%"></div></div>'
                    f'<div class="small" style="margin-top:22px">{e(t["mara_avg"].format(a=fmt_int(st.avg_messages, lang)))}</div>'
                    f'<div class="line" style="font-size:72px;font-weight:900">{e(t["mara_x"].format(x=x))}</div>')
    body = (f'<div class="content"><div class="k">{e(t["mara_k"])}</div>'
            f'<div class="big" style="font-size:{fit(n, 900, 360)}px">{n}</div>'
            f'<div class="line" style="margin-top:30px">{e(t["mara_line"])}</div>'
            f'<div class="small" style="margin-top:16px;opacity:.85">{e(t["mara_date"].format(date=fmt_date(st.longest_date, lang)))}</div>'
            f'{avg_html}{title_html}{foot(t, period)}</div>')
    return "marathon", page("Marathon", css, body)


def card_tokens(st: Stats, t, lang, period, **_):
    if st.tokens_in_out <= 0:
        return None
    hp = st.tokens_in_out / HP_TOKENS
    if hp >= 1:
        mult, what = (fmt_int(hp, lang) if hp >= 10 else f"{hp:.1f}".replace(".", "," if lang == "de" else ".")), t["tok_hp"]
    elif st.tokens_in_out >= HOBBIT_TOKENS / 10:
        hob = st.tokens_in_out / HOBBIT_TOKENS
        mult = f"{hob:.1f}".replace(".", "," if lang == "de" else ".")
        what = t["tok_hobbit"]
    else:  # a small history: count novel pages (about 300 words, 400 tokens each)
        pages = round(st.tokens_in_out / PAGE_TOKENS)
        mult = ""
        what = (t["tok_pages"].format(p=f"{fmt_int(pages, lang)} {unit(lang, 'page', pages)}") if pages >= 1
                else t["tok_lt_page"])
    css = ("body{background:radial-gradient(circle at 80% 15%,#7b2bff 0,transparent 45%),"
           "linear-gradient(170deg,#2346ff,#1020a0 75%)}"
           ".mult{color:#ffd84d}")
    cache = (f'<div class="small muted" style="margin-top:56px">'
             f'{e(t["tok_cache"].format(c=fmt_big(st.tokens_cache_read, lang)))}</div>') if st.tokens_cache_read else ""
    big = fmt_big(st.tokens_in_out, lang)
    body = (f'<div class="content"><div class="k">{e(t["tok_k"])}</div>'
            f'<div class="big" style="font-size:{fit(big, 900, 250)}px;margin-top:220px">{e(big)}</div>'
            f'<div class="line" style="margin-top:28px">{e(t["tok_line"])}</div>'
            + (f'<div class="big mult" style="font-size:{fit("≈ " + mult + "×", 900, 220)}px;margin-top:40px">≈ {e(mult)}×</div>'
             if mult else "")
            + f'<div class="line" style="margin-top:24px">{e(what)}</div>{cache}'
            f'<div class="small" style="margin-top:30px;font-size:27px;opacity:.75">{e(t["tok_note"])}</div>'
            f'{foot(t, period)}</div>')
    return "tokens", page("Tokens", css, body)


def card_crew(st: Stats, t, lang, period, **_):
    if st.cron_runs <= 0:
        return None
    n = fmt_int(st.cron_runs, lang)
    sub = (f'<div class="small" style="margin-top:20px;color:#7dffb5">{e(t["crew_sub"].format(n=fmt_int(st.subagent_runs, lang)))}</div>'
           if st.subagent_runs else "")
    css = ("body{background:linear-gradient(180deg,#00170f,#003322);color:#7dffb5}"
           ".term{font:500 40px 'JetBrains Mono',ui-monospace,Menlo,monospace;line-height:1.6}")
    body = (f'<div class="content"><div class="k">{e(t["crew_k"])}</div>'
            f'<div class="term" style="margin-top:150px">$ hermes cron list<br>&gt; running...</div>'
            f'<div class="big" style="font-size:{fit(n, 900, 320)}px;margin-top:60px;color:#fff">{n}</div>'
            f'<div class="line" style="color:#fff;margin-top:28px">{e(t["crew_line"])}</div>{sub}'
            f'<div class="term" style="margin-top:90px;font-size:50px;font-weight:700">{t["crew_punch"]}</div>'
            f'{foot(t, period, "color:#7dffb5")}</div>')
    return "crew", page("Night crew", css, body)


def card_model(st: Stats, t, lang, period, **_):
    if not st.models:
        return None
    ranked = st.models.most_common()
    top, n = ranked[0]
    share = n / sum(st.models.values())
    status = t["st_excl"] if share >= 0.9 else t["st_compl"] if share >= 0.6 else t["st_open"]
    cheat = (f'<div class="line muted" style="margin-top:44px;font-size:46px">'
             f'{e(t["model_cheat"].format(n=fmt_int(ranked[1][1], lang), m=ranked[1][0]))}</div>') if len(ranked) > 1 else ""
    others = ""
    if len(ranked) > 2:
        others = ('<div class="small" style="margin-top:26px;opacity:.85;font-size:34px">'
                  + "".join(f'<span class="nw">{html.escape(m)} {fmt_int(c, lang)}</span>' for m, c in ranked[2:6])
                  + "</div>")
    css = ("body{background:radial-gradient(circle at 20% 85%,#ff5fa255 0,transparent 45%),"
           "linear-gradient(150deg,#2b0a3d,#7a1f5c)}.heart{font-size:150px;line-height:1;margin-top:120px}"
           ".nw{display:inline-block;white-space:nowrap;margin-right:30px;border-bottom:3px solid #ffffff55}")
    body = (f'<div class="content"><div class="k">{e(t["model_k"])}</div><div class="heart">💘</div>'
            f'<div class="big" style="font-size:{fit(top, 900, 150, 0.58)}px;margin-top:50px">{e(top)}</div>'
            f'<div class="line" style="margin-top:30px">{e(t["model_line"].format(n=fmt_int(n, lang), chats=unit(lang, "chat", n)))}</div>'
            f'{cheat}{others}'
            f'<div class="line" style="margin-top:80px;font-size:56px">{e(t["status"])}<br><b style="font-weight:900;font-size:76px">{e(status)}</b></div>'
            f'{foot(t, period)}</div>')
    return "model", page("Model loyalty", css, body)


def card_projects(st: Stats, t, lang, period, **_):
    if not st.projects_source or st.projects_started <= 0:
        return None
    s, c = st.projects_started, st.projects_closed
    ratio = c / s
    verdict = t["proj_lo"] if ratio < 0.34 else t["proj_mid"] if ratio < 0.67 else t["proj_hi"]
    if st.projects_source == "projects":
        lab, sub = t["proj_started"], t["proj_closed"].format(n=fmt_int(c, lang))
    else:
        lab, sub = t["proj_folders"], t["proj_quiet"].format(n=fmt_int(c, lang))
    blocks = "".join(f'<span class="blk{" done" if i < c else ""}"></span>' for i in range(min(s, 60)))
    css = ("body{background:#ffd23f;color:#1a1400}"
           ".blk{display:inline-block;width:64px;height:64px;border-radius:14px;border:6px solid #1a1400;margin:0 12px 12px 0}"
           ".blk.done{background:#1a1400}")
    n = fmt_int(s, lang)
    body = (f'<div class="content"><div class="k">{e(t["proj_k"])}</div>'
            f'<div class="big" style="font-size:{fit(n, 900, 330)}px;margin-top:150px">{n}</div>'
            f'<div class="line" style="margin-top:26px">{e(lab)}</div>'
            f'<div class="line" style="margin-top:10px;font-weight:900">{e(sub)}</div>'
            f'<div style="margin-top:56px;line-height:0">{blocks}</div>'
            f'<div class="line" style="margin-top:50px;font-size:60px;font-weight:850">{e(verdict)}</div>'
            f'{foot(t, period)}</div>')
    return "projects", page("Projects", css, body)


def card_word(st: Stats, t, lang, period, **_):
    if not st.words:
        return None
    word, n = st.words[0]
    runners = "".join(f'<span class="chip">{e(w)} <i>{fmt_int(c, lang)}</i></span>' for w, c in st.words[1:9])
    css = ("body{background:#f4efe6;color:#141414}"
           ".serif{font-family:Georgia,'Times New Roman',serif}.quote{font-size:300px;line-height:.6;color:#ff5ca8;font-weight:700;margin-bottom:30px}"
           ".hl{background:linear-gradient(180deg,transparent 58%,#ff5ca8 58%,#ff5ca8 88%,transparent 88%);padding:0 10px}"
           ".chip{display:inline-block;border:5px solid #141414;border-radius:999px;padding:10px 30px 14px;"
           "font-size:40px;font-weight:800;margin:0 16px 18px 0}.chip i{font-style:normal;opacity:.7;font-weight:700}")
    body = (f'<div class="content"><div class="k">{e(t["word_k"])}</div>'
            f'<div class="quote serif">“</div><div class="serif big" style="font-size:{fit(word, 880, 230, 0.55)}px;letter-spacing:-.02em;font-weight:700">'
            f'<span class="hl">{e(word)}</span></div>'
            f'<div class="line" style="margin-top:50px">{e(t["word_line"].format(n=fmt_int(n, lang)))}</div>'
            + (f'<div class="k" style="margin-top:120px">{e(t["word_runners"])}</div><div style="margin-top:28px">{runners}</div>'
               if runners else "")
            + f'{foot(t, period)}</div>')
    return "word", page("Word of the year", css, body)


def card_summary(st: Stats, t, lang, period, **_):
    p = st.persona
    name = persona_name(p["code"], lang) if p else ""
    emoji = PERSONAS[p["code"]][0] if p else ""
    pw = st.polite.most_common(1)[0] if st.polite else None
    cells = [(fmt_int(st.sessions, lang), unit(lang, "chat", st.sessions)),
             (fmt_big(st.user_messages, lang), unit(lang, "msg", st.user_messages))]
    if st.tools:
        n_tools = sum(st.tools.values())
        cells.append((fmt_big(n_tools, lang), unit(lang, "call", n_tools)))
    if pw:
        cells.append((fmt_int(pw[1], lang), t["sum_polite"].format(w=pw[0])))
    if st.latest_clock:
        cells.append((st.latest_clock, t["sum_latest"]))
    if st.cron_runs:
        cells.append((fmt_big(st.cron_runs, lang), t["sum_cron"]))
    if st.tokens_in_out:
        cells.append((fmt_big(st.tokens_in_out, lang), t["sum_tokens"]))
    cells = cells[:6]
    grid = "".join(f'<div><b>{e(v)}</b>{e(k)}</div>' for v, k in cells)
    facts = []
    if st.tools:
        facts.append((t["sum_top_tool"], st.tools.most_common(1)[0][0]))
    if st.models:
        facts.append((t["sum_top_model"], st.models.most_common(1)[0][0]))
    if st.busiest_day:
        facts.append((t["sum_busiest"], f"{fmt_date(st.busiest_day, lang)}, {t['sum_msgs_day'].format(n=fmt_int(st.busiest_day_msgs, lang), msgs=unit(lang, 'msg', st.busiest_day_msgs))}"))
    if st.words:
        facts.append((t["sum_word"], st.words[0][0]))
    fact_html = "".join(f'<div class="fact"><span>{e(k)}</span><b>{e(v)}</b></div>' for k, v in facts)
    css = ("body{background:#0d0d0d}"
           ".frame{position:absolute;inset:40px;border:5px solid #d4af37;border-radius:44px}"
           ".gold{color:#d4af37}"
           ".grid{display:grid;grid-template-columns:1fr 1fr;gap:38px 36px;margin-top:60px}"
           ".grid div{font-size:30px;text-transform:uppercase;letter-spacing:.08em;opacity:.85;font-weight:600}"
           ".grid b{display:block;font-size:96px;font-weight:900;color:#d4af37;letter-spacing:-.04em;line-height:1;"
           "margin-bottom:8px;text-transform:none}"
           ".fact{display:flex;justify-content:space-between;gap:30px;font-size:36px;border-top:2px solid #d4af3755;"
           "padding:20px 0}.fact span{opacity:.7}.fact b{font-weight:800;text-align:right}")
    size = fit(max(name.split(" "), key=len) if name else "x", 900, 104, 0.62)
    body = (f'<div class="layer"><div class="frame"></div></div><div class="content">'
            f'<div class="k gold">{e(t["wrapped"])} {e(period)}</div>'
            + (f'<div class="big" style="font-size:{size}px;margin-top:50px;line-height:1.08">{emoji} {e(name)}</div>' if name else "")
            + f'<div class="grid">{grid}</div><div style="margin-top:50px">{fact_html}</div>'
            f'{foot(t, period, "color:#d4af37")}</div>')
    return "summary", page("Hermes Wrapped summary", css, body)


CARDS: list[Callable] = [card_cover, card_persona, card_tools, card_skill, card_manners, card_night,
                         card_marathon, card_tokens, card_crew, card_model, card_projects, card_word, card_summary]


def period_label(st: Stats, lang: str) -> str:
    w = st.window
    if w.year:
        return str(w.year)
    if w.days:
        return T[lang]["days"].format(d=w.days)
    return T[lang]["all"]


def render_all(st: Stats, lang: str = "en", show_titles: bool = False) -> list[tuple[str, str]]:
    t = T.get(lang, T["en"])
    period = period_label(st, lang)
    out = []
    for fn in CARDS:
        res = fn(st, t, lang, period, show_titles=show_titles)
        if res:
            out.append(res)
    return out


def gallery(files: list[str], title: str) -> str:
    frames = "".join(
        f'<div class="w"><iframe src="{e(f)}" scrolling="no" loading="lazy"></iframe><a href="{e(f)}">{e(f)}</a></div>'
        for f in files)
    css = ("body{background:#0b0b0f;color:#aaa;font:15px -apple-system,Inter,sans-serif;padding:40px}"
           "h1{color:#fff;font-size:26px;margin:0 0 30px}"
           ".g{display:flex;flex-wrap:wrap;gap:30px}.w{width:324px}"
           ".w iframe{width:1080px;height:1920px;border:0;transform:scale(.3);transform-origin:0 0;margin-bottom:-1344px;"
           "margin-right:-756px;border-radius:60px;display:block}"
           ".w a{color:#aaa;display:block;margin-top:10px;font-family:monospace}")
    return ('<!doctype html><html><head><meta charset="utf-8"><title>' + e(title) + "</title><style>" + css
            + "</style></head><body><h1>" + e(title) + '</h1><div class="g">' + frames + "</div></body></html>")
