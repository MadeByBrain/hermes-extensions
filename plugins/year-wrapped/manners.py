"""Politeness and swear jar counting for year-wrapped.

The word lists, the cleaning rules and the ranks follow the manners-meter plugin
(same maintainer, MIT). They are copied here on purpose so year-wrapped has no
dependency on another plugin. Standard library only.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable

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


def _compile(rules):
    body = "|".join("(" + rx + ")" for _rid, _label, rx in rules)
    meta = [(rid, label) for rid, label, _rx in rules]
    return re.compile(r"(?<![\w])(?:" + body + r")(?![\w])", re.I), meta


_POLITE = _compile(POLITE)
_SWEAR = _compile(SWEAR)

_FENCE = re.compile("\x60{3}.*?(?:\x60{3}|$)", re.S)
_QUOTE = re.compile(r"^[ \t]{0,8}>.*$", re.M)
# Text Hermes injects as a "user" message (background notices, compaction handoffs, delegation
# results, task lists): the whole message is skipped.
_DROP_MESSAGE = ("[system", "[skill", "[context", "<system", "[important:", "[async delegation",
                 "[your active task list", "[ide")
# Wrapper and annotation lines around real typed text: only the line is skipped.
_DROP_LINE = _DROP_MESSAGE + ("[workspace::", "[out-of-band", "[/out-of-band", "[attached", "[the user sent",
                              "[group chat:", "[image", "[replying to:")
_REPLY_QUOTE = re.compile(r'^[ \t\n]{0,8}\[Replying to: "[\s\S]{0,2000}?"\]')
# Long pastes (logs, documents) are not typed text: only the first part of a message counts.
MAX_TYPED_CHARS = 4000


def clean_user_text(text: str) -> str:
    """Drop what the user did not type: injected notices, wrappers, code blocks, quoted lines."""
    if not isinstance(text, str) or not text:
        return ""
    if text.lstrip()[:24].lower().startswith(_DROP_MESSAGE):
        return ""
    text = text[:MAX_TYPED_CHARS * 3]
    text = _REPLY_QUOTE.sub(" ", text)
    text = _FENCE.sub(" ", text)
    text = _QUOTE.sub(" ", text)
    lines = [ln for ln in text.splitlines() if not ln.lstrip()[:24].lower().startswith(_DROP_LINE)]
    return "\n".join(lines)[:MAX_TYPED_CHARS]


def _hits(rules, text: str) -> list[tuple[str, str, int]]:
    rx, meta = rules
    counts: Counter = Counter()
    for m in rx.finditer(text):
        counts[m.lastindex - 1] += 1
    return [(meta[i][0], meta[i][1], n) for i, n in sorted(counts.items())]


def polite_hits(text: str) -> list[tuple[str, str, int]]:
    return _hits(_POLITE, text)


def swear_hits(text: str) -> list[tuple[str, str, int]]:
    return _hits(_SWEAR, text)


def estimate_tokens(label: str) -> int:
    """Tokenizer free estimate: about 4 characters per token, at least 1."""
    return max(1, math.ceil(len(label) / 4))


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


def rank(polite_total: int, swear_total: int, messages: int, lang: str = "en") -> tuple[str, str]:
    per100 = 100.0 * polite_total / max(1, messages)
    sw100 = 100.0 * swear_total / max(1, messages)
    idx = 1 if lang == "en" else 2
    p = str(next(r for r in RANKS if per100 >= r[0])[idx])
    s = str(next(r for r in SWEAR_RANKS if sw100 >= r[0])[idx])
    return p, s


def polite_labels() -> Iterable[str]:
    return [label for _r, label, _x in POLITE]
