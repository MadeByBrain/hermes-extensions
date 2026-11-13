"""manners-meter core: count politeness and swearing in your own Hermes history.

Pure functions plus one read-only reader for ``state.db``. Standard library only.
Nothing here writes to the database or sends anything over the network.
"""
from __future__ import annotations

import math
import re
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

# --------------------------------------------------------------------------------------
# Word lists. Each entry: (rule id, label shown to the user, regex). Matching is case
# insensitive on word boundaries. Multi word phrases come first so "thank you" is not
# also counted as a lone "thank".
# --------------------------------------------------------------------------------------

POLITE: list[tuple[str, str, str]] = [
    ("de.vielen_dank", "vielen dank", r"vielen\s{1,3}dank"),
    ("de.dankeschoen", "dankeschön", r"danke\s{0,2}sch(?:ö|oe)n"),
    ("de.danke", "danke", r"danke"),
    ("de.bitte", "bitte", r"bitte"),
    ("de.entschuldigung", "entschuldigung", r"entschuldigung"),
    ("en.thank_you", "thank you", r"thank\s{1,3}you"),
    ("en.thanks", "thanks", r"thanks|thx|tysm"),
    ("en.please", "please", r"please|pls|plz"),
    ("en.appreciate", "appreciate it", r"(?:i\s{1,3})?appreciate\s{1,3}it"),
    ("en.sorry", "sorry", r"sorry"),
    ("es.por_favor", "por favor", r"por\s{1,3}favor"),
    ("es.gracias", "gracias", r"gracias"),
    ("fr.svp", "s'il vous plaît", r"s'il\s{1,3}(?:vous|te)\s{1,3}pla(?:î|i)t|svp"),
    ("fr.merci", "merci", r"merci"),
]

SWEAR: list[tuple[str, str, str]] = [
    ("en.fuck", "f***", r"fuck(?:ing|ed|er|s)?|wtf|ffs"),
    ("en.shit", "s***", r"shit(?:ty|s)?|bullshit"),
    ("en.damn", "damn", r"damn(?:it)?|goddamn"),
    ("en.crap", "crap", r"crap(?:py)?"),
    ("de.scheisse", "sch***e", r"schei(?:ß|ss)(?:e|dreck|ding)?"),
    ("de.verdammt", "verdammt", r"verdammt(?:e|er|es)?|verflucht(?:e|er|es)?"),
    ("de.mist", "mist", r"mist(?:ding|stück)?"),
    ("de.kacke", "kacke", r"kacke"),
]

# The agent's side of the courtesy: how often it answered a thank you.
WELCOME: list[tuple[str, str, str]] = [
    ("de.gern", "gern geschehen", r"gern(?:e)?\s{1,3}geschehen"),
    ("en.welcome", "you're welcome", r"you(?:'|’)?re\s{1,3}(?:very\s{1,3})?welcome"),
    ("en.happy", "happy to help", r"happy\s{1,3}to\s{1,3}help"),
]


def _compile(rules: list[tuple[str, str, str]]) -> tuple[re.Pattern, list[tuple[str, str]]]:
    """One alternation with a group per rule: a single pass per message. At the same
    position the earlier rule wins, so phrases listed first beat their single words."""
    body = "|".join("(" + rx + ")" for _rid, _label, rx in rules)
    meta = [(rid, label) for rid, label, _rx in rules]
    return re.compile(r"(?<![\w])(?:" + body + r")(?![\w])", re.I), meta


_POLITE = _compile(POLITE)
_SWEAR = _compile(SWEAR)
_WELCOME = _compile(WELCOME)

_FENCE = re.compile("\x60{3}.*?(?:\x60{3}|$)", re.S)
_QUOTE = re.compile(r"^[ \t]{0,8}>.*$", re.M)
_SYSTEM_PREFIXES = ("[system", "[out-of-band", "[skill", "[context", "<system")

# Platforms whose "user" messages are written by machines, not by you.
WELCOME_WINDOW = 200  # "you're welcome" is looked for at the start of an answer only

DEFAULT_EXCLUDED_SOURCES = ("cron", "subagent", "kanban", "batch", "webhook", "tool")


def clean_user_text(text: str) -> str:
    """Drop what the user did not type: code blocks, quoted lines, injected system blocks."""
    if not isinstance(text, str) or not text:
        return ""
    if text.lstrip()[:14].lower().startswith(_SYSTEM_PREFIXES):
        return ""
    text = _FENCE.sub(" ", text)
    text = _QUOTE.sub(" ", text)
    # Injected blocks inside a message ("[System: ...]" lines, steering wrappers).
    lines = [ln for ln in text.splitlines() if not ln.lstrip()[:14].lower().startswith(_SYSTEM_PREFIXES)]
    return "\n".join(lines)


def _hits(rules, text: str, extra: Iterable[str] = ()) -> list[tuple[str, str, int]]:
    """Return (rule id, label, count) for every rule that matched at least once."""
    rx, meta = rules
    counts: Counter = Counter()
    for m in rx.finditer(text):
        counts[m.lastindex - 1] += 1
    out = [(meta[i][0], meta[i][1], n) for i, n in sorted(counts.items())]
    for phrase in extra:
        p = str(phrase).strip()
        if not p:
            continue
        crx = re.compile(r"(?<![\w])" + re.escape(p) + r"(?![\w])", re.I)
        n = len(crx.findall(text))
        if n:
            out.append(("custom." + p.lower(), p.lower(), n))
    return out


def polite_hits(text: str, extra: Iterable[str] = ()) -> list[tuple[str, str, int]]:
    return _hits(_POLITE, text, extra)


def swear_hits(text: str, extra: Iterable[str] = ()) -> list[tuple[str, str, int]]:
    return _hits(_SWEAR, text, extra)


def welcome_hits(text: str) -> list[tuple[str, str, int]]:
    return _hits(_WELCOME, text)


def estimate_tokens(label: str) -> int:
    """Rough tokenizer free estimate: about 4 characters per token, at least 1."""
    return max(1, math.ceil(len(label) / 4))


# --------------------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------------------

@dataclass
class Report:
    days: Optional[int] = None
    user_messages: int = 0
    sessions: int = 0
    polite: Counter = field(default_factory=Counter)  # label -> count
    swear: Counter = field(default_factory=Counter)
    welcome: Counter = field(default_factory=Counter)
    polite_tokens: int = 0  # tokens you typed for politeness
    carried_tokens: int = 0  # the same tokens re-sent with every later model call of the session
    de_votes: int = 0
    en_votes: int = 0
    first_ts: Optional[float] = None
    last_ts: Optional[float] = None

    @property
    def polite_total(self) -> int:
        return sum(self.polite.values())

    @property
    def swear_total(self) -> int:
        return sum(self.swear.values())

    @property
    def welcome_total(self) -> int:
        return sum(self.welcome.values())

    def guess_language(self) -> str:
        return "de" if self.de_votes > self.en_votes else "en"

    def to_dict(self) -> dict:
        return {
            "days": self.days,
            "user_messages": self.user_messages,
            "sessions": self.sessions,
            "polite_total": self.polite_total,
            "polite": dict(self.polite.most_common()),
            "swear_total": self.swear_total,
            "swear": dict(self.swear.most_common()),
            "welcome_total": self.welcome_total,
            "welcome": dict(self.welcome.most_common()),
            "polite_tokens": self.polite_tokens,
            "carried_tokens": self.carried_tokens,
            "first_ts": self.first_ts,
            "last_ts": self.last_ts,
            "rank": rank(self)[0],
        }


def analyze_rows(rows: Iterable[tuple], *, extra_polite=(), extra_swear=(), days: Optional[int] = None) -> Report:
    """rows: (session_id, role, content, has_tool_calls, timestamp), ordered by session then message order.

    Carried tokens: polite tokens of a user message times the number of model calls that
    followed in the same session (each assistant message counts as one call). Most of that
    is served from the prompt cache, so it is an upper bound for re-sent input, not a bill.
    """
    rep = Report(days=days)
    sessions = set()
    pending: list[int] = []  # polite tokens of earlier user messages in this session
    cur_session = None
    for sid, role, content, _has_tools, ts in rows:
        if sid != cur_session:
            cur_session = sid
            pending = []
        if role == "assistant":
            if pending:
                rep.carried_tokens += sum(pending)
            if isinstance(content, str) and content:
                for _rid, label, n in welcome_hits(content):
                    rep.welcome[label] += n
            continue
        if role != "user":
            continue
        text = clean_user_text(content if isinstance(content, str) else "")
        if not text.strip():
            continue
        rep.user_messages += 1
        sessions.add(sid)
        if ts:
            rep.first_ts = ts if rep.first_ts is None else min(rep.first_ts, ts)
            rep.last_ts = ts if rep.last_ts is None else max(rep.last_ts, ts)
        toks = 0
        for rid, label, n in polite_hits(text, extra_polite):
            rep.polite[label] += n
            toks += estimate_tokens(label) * n
            if rid.startswith("de."):
                rep.de_votes += n
            elif rid.startswith("en."):
                rep.en_votes += n
        for rid, label, n in swear_hits(text, extra_swear):
            rep.swear[label] += n
            if rid.startswith("de."):
                rep.de_votes += n
            elif rid.startswith("en."):
                rep.en_votes += n
        if toks:
            rep.polite_tokens += toks
            pending.append(toks)
    rep.sessions = len(sessions)
    return rep


def read_rows(db_path: Path, *, days: Optional[int] = None, excluded_sources=DEFAULT_EXCLUDED_SOURCES,
              session_id: Optional[str] = None) -> list[tuple]:
    """Read user and assistant messages read-only. Missing database returns []."""
    if not Path(db_path).is_file():
        return []
    uri = "file:" + str(db_path) + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        # Filter sessions first so the messages index is used and machine sessions (often most of
        # the database) are never read. Assistant text is only fetched when its first 200
        # characters may hold a "you're welcome"; skipping the rest keeps a large history fast.
        where = ["m.role IN ('user','assistant')"]
        params: list = []
        sess = "SELECT id FROM sessions"
        if excluded_sources:
            sess += " WHERE COALESCE(source,'') NOT IN (%s)" % ",".join("?" * len(excluded_sources))
            params.extend(excluded_sources)
        where.append("m.session_id IN (" + sess + ")")
        if days:
            where.append("m.timestamp >= ?")
            params.append(time.time() - days * 86400)
        if session_id:
            where.append("m.session_id = ?")
            params.append(session_id)
        head = "substr(m.content, 1, %d)" % WELCOME_WINDOW
        sql = ("SELECT m.session_id, m.role, CASE WHEN m.role = 'user' THEN m.content "
               f"WHEN {head} LIKE '%geschehen%' OR {head} LIKE '%welcome%' "
               f"OR {head} LIKE '%happy to help%' THEN {head} ELSE NULL END, "
               "(m.tool_calls IS NOT NULL), m.timestamp "
               "FROM messages m WHERE " + " AND ".join(where) +
               " ORDER BY m.session_id, m.timestamp, m.id")
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


# --------------------------------------------------------------------------------------
# Ranks (deliberately silly) and text output
# --------------------------------------------------------------------------------------

RANKS = [  # (min politeness per 100 messages, en, de)
    (40.0, "Butler of Butlers", "Oberbutler"),
    (20.0, "Diplomat", "Diplomat"),
    (8.0, "Polite Professional", "Höflicher Profi"),
    (2.0, "Efficient Operator", "Effizienter Operator"),
    (0.0, "Cold Commander", "Kalter Kommandant"),
]
SWEAR_RANKS = [  # (min swears per 100 messages, en, de)
    (5.0, "Sailor", "Seemann"),
    (1.0, "Occasionally Spicy", "Gelegentlich scharf"),
    (0.01, "Mostly Clean", "Weitgehend sauber"),
    (0.0, "Saint", "Heilig"),
]


def rank(rep: Report, lang: str = "en") -> tuple[str, str]:  # noqa: D401
    """Return (politeness rank, swear rank) in the given language."""
    per100 = 100.0 * rep.polite_total / max(1, rep.user_messages)
    sw100 = 100.0 * rep.swear_total / max(1, rep.user_messages)
    idx = 1 if lang == "en" else 2
    p = str(next(r for r in RANKS if per100 >= r[0])[idx])
    s = str(next(r for r in SWEAR_RANKS if sw100 >= r[0])[idx])
    return p, s


def fmt_int(n: float, lang: str) -> str:
    s = f"{int(round(n)):,}"
    return s.replace(",", ".") if lang == "de" else s


def fmt_tokens(n: float, lang: str) -> str:
    if n >= 1_000_000:
        v = f"{n / 1_000_000:.1f}"
        return (v.replace(".", ",") + " Mio.") if lang == "de" else (v + "M")
    if n >= 10_000:
        v = f"{n / 1000:.0f}"
        return v + ("k" if lang == "en" else " Tsd.")
    return fmt_int(n, lang)


def fmt_money(v: float, currency: str, lang: str) -> str:
    s = f"{v:,.2f}"
    if lang == "de":
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{s} {currency}"
    return f"{currency}{s}" if len(currency) == 1 else f"{s} {currency}"


TEXT = {
    "en": {
        "title": "Manners meter",
        "scope_all": "all time",
        "scope_days": "last {d} days",
        "scope_session": "this chat",
        "msgs": "{n} messages from you in {s} chats",
        "polite": "You were polite {n}x:",
        "none_polite": "No please, no thank you. Your agent does not take it personally.",
        "typed": "Tokens you typed for it: {t}",
        "carried": "Re-sent with every later model call: about {t} (mostly from cache, at most {m} uncached at {p} per million)",
        "welcome": "Your agent answered \"you're welcome\": {n}x",
        "jar": "Swear jar: {n} coins = {v}. Top word: {w}",
        "jar_empty": "Swear jar: empty. Suspiciously clean.",
        "rank": "Rank: {p} / {s}",
        "foot": "Counted locally from state.db. Nothing left your machine.",
    },
    "de": {
        "title": "Manners Meter",
        "scope_all": "gesamt",
        "scope_days": "letzte {d} Tage",
        "scope_session": "dieser Chat",
        "msgs": "{n} Nachrichten von dir in {s} Chats",
        "polite": "Höflich warst du {n}x:",
        "none_polite": "Kein Bitte, kein Danke. Dein Agent nimmt es dir nicht übel.",
        "typed": "Dafür getippte Tokens: {t}",
        "carried": "Bei jedem späteren Modellaufruf mitgeschickt: etwa {t} (meist aus dem Cache, ohne Cache höchstens {m} bei {p} pro Million)",
        "welcome": "Dein Agent sagte \"gern geschehen\": {n}x",
        "jar": "Schimpfglas: {n} Münzen = {v}. Häufigstes Wort: {w}",
        "jar_empty": "Schimpfglas: leer. Verdächtig sauber.",
        "rank": "Rang: {p} / {s}",
        "foot": "Lokal aus state.db gezählt. Nichts hat deinen Rechner verlassen.",
    },
}


def render_text(rep: Report, *, lang: str = "en", scope: str = "all", jar_price: float = 1.0,
                currency: str = "", price_per_mtok: float = 3.0) -> str:
    t = TEXT[lang]
    cur = currency or ("€" if lang == "de" else "$")
    if scope == "session":
        sc = t["scope_session"]
    elif rep.days:
        sc = t["scope_days"].format(d=rep.days)
    else:
        sc = t["scope_all"]
    lines = [f"{t['title']} ({sc})", t["msgs"].format(n=fmt_int(rep.user_messages, lang), s=fmt_int(rep.sessions, lang))]
    if rep.polite_total:
        top = ", ".join(f"\"{k}\" {fmt_int(v, lang)}x" for k, v in rep.polite.most_common(5))
        lines.append(t["polite"].format(n=fmt_int(rep.polite_total, lang)) + " " + top)
        lines.append(t["typed"].format(t=fmt_int(rep.polite_tokens, lang)))
        if rep.carried_tokens:
            money = rep.carried_tokens / 1_000_000 * price_per_mtok
            money_s = fmt_money(money, "$", lang) if money >= 0.01 else "< " + fmt_money(0.01, "$", lang)
            lines.append(t["carried"].format(t=fmt_tokens(rep.carried_tokens, lang),
                                             m=money_s,
                                             p=fmt_money(price_per_mtok, "$", lang)))
    else:
        lines.append(t["none_polite"])
    if rep.welcome_total:
        lines.append(t["welcome"].format(n=fmt_int(rep.welcome_total, lang)))
    if rep.swear_total:
        w = rep.swear.most_common(1)[0][0]
        lines.append(t["jar"].format(n=fmt_int(rep.swear_total, lang),
                                     v=fmt_money(rep.swear_total * jar_price, cur, lang), w=w))
    else:
        lines.append(t["jar_empty"])
    p, s = rank(rep, lang)
    lines.append(t["rank"].format(p=p, s=s))
    lines.append(t["foot"])
    return "\n".join(lines)
