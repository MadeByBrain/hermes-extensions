"""Rule-based checks for writing-guard. Pure functions, standard library only, no Hermes imports.

check(text, ...) returns a Report. fix_dashes(text, ...) returns (new_text, count).
Protected spans (fenced code, inline code, URLs, MEDIA lines, optional quotes) are masked with
private-use placeholders before any rule runs and restored afterwards, so they are never counted
and never changed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from .phrases import PHRASES

DASHES = "\u2012\u2013\u2014\u2015"  # figure dash, en dash, em dash, horizontal bar
_D = f"[{DASHES}]"
_PH_OPEN, _PH_CLOSE = "\ue000", "\ue001"
_PH_RE = re.compile(_PH_OPEN + r"(\d+)" + _PH_CLOSE)
MAX_CHARS = 200_000

# ----------------------------------------------------------------------------- masking

_BT = "\x60"  # backtick, written as an escape so security scanners do not read it as shell
_FENCE_RE = re.compile(r"^\s{0,3}(" + _BT + r"{3,}|~{3,})")
_INLINE_CODE_RE = re.compile("(" + _BT + "+)(?!" + _BT + ").+?(?<!" + _BT + r")\1")
_URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>()\[\]]+|<[^<>\s]+@[^<>\s]+>")
_MD_LINK_TARGET_RE = re.compile(r"\]\([^)\s]+\)")


def mask(text: str, skip_quotes: bool = True) -> tuple[str, list[str]]:
    """Replace protected spans with placeholders. Returns (masked_text, originals)."""
    saved: list[str] = []

    def keep(s: str) -> str:
        saved.append(s)
        return f"{_PH_OPEN}{len(saved) - 1}{_PH_CLOSE}"

    out: list[str] = []
    fence: Optional[str] = None
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        nl = line[len(body):]
        if fence is not None:
            out.append(keep(body) + nl)
            m = _FENCE_RE.match(body)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not body.strip()[len(m.group(1)):].strip():
                fence = None
            continue
        m = _FENCE_RE.match(body)
        if m:
            fence = m.group(1)
            out.append(keep(body) + nl)
            continue
        stripped = body.lstrip()
        if stripped.startswith("MEDIA:") or (skip_quotes and stripped.startswith(">")):
            out.append(keep(body) + nl)
            continue
        body = _INLINE_CODE_RE.sub(lambda mm: keep(mm.group(0)), body)
        body = _MD_LINK_TARGET_RE.sub(lambda mm: "]" + keep(mm.group(0)[1:]), body)
        body = _URL_RE.sub(lambda mm: keep(mm.group(0)), body)
        out.append(body + nl)
    return "".join(out), saved


def unmask(masked: str, saved: list[str]) -> str:
    return _PH_RE.sub(lambda m: saved[int(m.group(1))], masked)


def _prose(masked: str) -> str:
    """Masked text with placeholders turned into a neutral word, for detection only."""
    return _PH_RE.sub(" x ", masked)

# ----------------------------------------------------------------------------- language

_DE_WORDS = set("""der die das und ist nicht ich du sie wir ihr es ein eine einen dem den des zu
mit für auf von im in ist sind war hat haben wird werden kann können auch noch nur oder aber wie
wenn dass sich bei nach aus um über unter vor dir dich dein deine ihnen ihre mein meine uns an
einem einer eines kein keine man so schon sehr hier jetzt dann also doch mal gibt bitte danke heute
seite seiten uhr bis zum zur am vom""".split())
_EN_WORDS = set("""the and is are was were be been to of in on for with that this it you your we
they he she not but or as at by from have has had will would can could should an a which what
there their our my me""".split())
_WORD_RE = re.compile(r"[a-zäöüß']+")


def detect_language(text: str) -> str:
    words = _WORD_RE.findall(text.lower())
    de = sum(1 for w in words if w in _DE_WORDS)
    de += 2 * sum(1 for w in words if any(c in w for c in "äöüß"))
    en = sum(1 for w in words if w in _EN_WORDS)
    return "de" if de >= 2 and de > en else "en"

# ----------------------------------------------------------------------------- dashes

def count_dashes(masked: str) -> int:
    return sum(masked.count(c) for c in DASHES)


_WORDCH = r"0-9A-Za-zÄÖÜäöüßÀ-ÿ"
_BULLET_RE = re.compile(rf"^([ \t]*){_D}[ \t]+", re.M)
_LEAD_RE = re.compile(rf"^([ \t]*){_D}(?=\S)", re.M)
_CELL_RE = re.compile(rf"(?<=\|)[ \t]*{_D}[ \t]*(?=\|)")
_RANGE_RE = re.compile(rf"(?<=[{_WORDCH}.])[\u2012\u2013](?=[{_WORDCH}])")
_NUM_RANGE_RE = re.compile(rf"(?<=\d)[ \t]*{_D}[ \t]*(?=\d)")
_END_RE = re.compile(rf"[ \t]*{_D}+[ \t]*$", re.M)
_BEFORE_PUNCT_RE = re.compile(rf"[ \t]*{_D}+[ \t]*(?=[,.;:!?)\]\"“”»])")
_AFTER_OPEN_RE = re.compile(rf"(?<=[(\[„“\"«])[ \t]*{_D}+[ \t]*")
_SPACED_RE = re.compile(rf"[ \t]*{_D}+[ \t]*")


def fix_dashes(masked: str, style: str = "comma") -> tuple[str, int]:
    """Replace every dash in masked text. Returns (new_masked_text, number_of_dashes_replaced)."""
    n = count_dashes(masked)
    if not n:
        return masked, 0
    sep = " - " if style == "hyphen" else ", "
    t = _BULLET_RE.sub(r"\1- ", masked)
    t = _LEAD_RE.sub(r"\1", t)
    t = _CELL_RE.sub(" - ", t)
    t = _NUM_RANGE_RE.sub("-", t)
    # unspaced en dash or figure dash between words/numbers is a range or link: Mo-Fr, Berlin-Hamburg (written with a dash)
    t = _RANGE_RE.sub("-", t)
    t = _END_RE.sub("", t)
    t = _BEFORE_PUNCT_RE.sub("", t)
    t = _AFTER_OPEN_RE.sub("", t)

    def spaced(m: re.Match) -> str:
        before = t[max(0, m.start() - 8):m.start()].rstrip(" \t")
        if before.endswith((",", ";", ":", ".", "!", "?")):
            return " "
        return sep

    t = _SPACED_RE.sub(spaced, t)
    return t, n

# ----------------------------------------------------------------------------- phrases

_COMPILED = [(pid, lang, re.compile(rx, re.I)) for pid, lang, rx in PHRASES]


@dataclass
class PhraseHit:
    id: str
    text: str
    count: int = 1


def find_phrases(prose: str, extra: Iterable[str] = (), ignore: Iterable[str] = ()) -> list[PhraseHit]:
    ignore_set = {str(i).strip().lower() for i in ignore if str(i).strip()}
    hits: dict[str, PhraseHit] = {}
    rules = list(_COMPILED)
    for i, phrase in enumerate(extra or ()):
        phrase = str(phrase).strip()
        if phrase:
            rules.append((f"custom.{i + 1}", "any", re.compile(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", re.I)))
    for pid, _lang, rx in rules:
        if pid.lower() in ignore_set:
            continue
        for m in rx.finditer(prose):
            found = m.group(0).strip(" \n,.!:")
            if found.lower() in ignore_set:
                continue
            if pid in hits:
                hits[pid].count += 1
            else:
                hits[pid] = PhraseHit(pid, found[:60])
    return list(hits.values())

# ----------------------------------------------------------------------------- du / Sie

_INFORMAL_RE = re.compile(r"\b(?:du|dich|dir|dein|deine|deinem|deinen|deiner|deines|"
                          r"euch|euer|eure|eurem|euren|eurer|eures)\b", re.I)
_FORMAL_RE = re.compile(r"\b(?:Sie|Ihnen|Ihr|Ihre|Ihrem|Ihren|Ihrer|Ihres)\b")
_LEAD_CHARS = " \t*_\"'„“”»«‚‘(#>-•+"


def _sentence_start(text: str, pos: int) -> bool:
    start = max(0, pos - 80)
    before = text[start:pos].rstrip(_LEAD_CHARS)
    if not before and start > 0:
        return False
    if not before or before.endswith("\n"):
        return True
    before = before.rstrip(" \t")
    if re.search(r"(?:^|\n)[ \t]*\d+[.)]$", before):
        return True
    return before.endswith((".", "!", "?", ":", "|", "\n"))


# Talking ABOUT the forms is not using them: "du/Sie", "du oder Sie", "Sie-Form", „Sie“, `duzen`.
_META_RE = re.compile(
    r"\b(?:du|Du|DU)\s*(?:/|oder|und|bzw\.?|vs\.?|statt|or|and)\s*(?:Sie|SIE)\b"
    r"|\b(?:Sie|SIE)\s*(?:/|oder|und|bzw\.?|vs\.?|statt|or|and)\s*(?:du|Du|DU)\b"
    r"|\b(?:du|Du|Sie|Ihr|Ihre|Ihnen)-(?=\w)"
    r"|\b(?:per|das|beim|ins|zum|aufs)\s+(?:du|Du|Sie)\b"
    r"|[„“\"'‚‘»«](?:du|Du|Sie|Ihnen|Ihr|dein|dich|dir)[“”\"'‘’«»]"
)


# Inline quotations are someone else's words: „...“, "...", »...«.
_INLINE_QUOTE_RE = re.compile(r"„[^“”\n]{1,300}[“”]|\"[^\"\n]{1,300}\"|»[^«\n]{1,300}«|«[^»\n]{1,300}»")


def address_counts(prose: str) -> tuple[int, int]:
    prose = _INLINE_QUOTE_RE.sub(" ", _META_RE.sub(" ", prose))
    du = len(_INFORMAL_RE.findall(prose))
    sie = sum(1 for m in _FORMAL_RE.finditer(prose) if not _sentence_start(prose, m.start()))
    return du, sie


def mixed_paragraphs(prose: str) -> list[tuple[int, int]]:
    """Paragraphs that use both forms: list of (du, Sie) counts."""
    out = []
    for para in re.split(r"\n[ \t]*\n", prose):
        du, sie = address_counts(para)
        if du and sie:
            out.append((du, sie))
    return out

# ----------------------------------------------------------------------------- report

@dataclass
class Report:
    language: str = "en"
    dashes: int = 0
    dashes_fixed: int = 0
    phrases: list[PhraseHit] = field(default_factory=list)
    du: int = 0
    sie: int = 0
    mixed: list[tuple[int, int]] = field(default_factory=list)
    form: Optional[str] = None          # du, sie, mixed or None (no address, or not German)
    expected: Optional[str] = None      # du or sie when the user fixed a form
    previous_form: Optional[str] = None # set when the form switched against the last answer
    text: Optional[str] = None          # fixed text (fix mode only)

    @property
    def wrong_form(self) -> int:
        if self.expected == "du":
            return self.sie
        if self.expected == "sie":
            return self.du
        return 0

    @property
    def has_findings(self) -> bool:
        return bool(self.dashes or self.dashes_fixed or self.phrases or self.mixed
                    or self.wrong_form or self.previous_form)

    def as_dict(self) -> dict:
        return {
            "language": self.language,
            "dashes_found": self.dashes,
            "dashes_replaced": self.dashes_fixed,
            "ai_phrases": [{"id": p.id, "text": p.text, "count": p.count} for p in self.phrases],
            "address": {
                "du": self.du, "sie": self.sie, "form": self.form, "expected": self.expected,
                "mixed_paragraphs": len(self.mixed), "wrong_form": self.wrong_form,
                "switched_from": self.previous_form,
            },
        }


def check(text: str, *, fix: bool = False, dash_style: str = "comma", check_dashes: bool = True,
          check_phrases: bool = True, check_address: bool = True, address: str = "auto",
          extra_phrases: Iterable[str] = (), ignore_phrases: Iterable[str] = (),
          skip_quotes: bool = True, previous_form: Optional[str] = None,
          track_switches: bool = True) -> Report:
    text = text or ""
    if len(text) > MAX_CHARS:
        return Report()
    masked, saved = mask(text, skip_quotes=skip_quotes)
    prose = _prose(masked)
    rep = Report(language=detect_language(prose))
    if check_dashes:
        if fix:
            new_masked, rep.dashes_fixed = fix_dashes(masked, dash_style)
            if rep.dashes_fixed:
                rep.text = unmask(new_masked, saved)
                prose = _prose(new_masked)
        else:
            rep.dashes = count_dashes(masked)
    if check_phrases:
        rep.phrases = find_phrases(prose, extra_phrases, ignore_phrases)
    if check_address and rep.language == "de":
        rep.du, rep.sie = address_counts(prose)
        rep.mixed = mixed_paragraphs(prose)
        if rep.du and rep.sie:
            rep.form = "mixed"
        elif rep.du:
            rep.form = "du"
        elif rep.sie:
            rep.form = "sie"
        if address in ("du", "sie"):
            rep.expected = address
        if (track_switches and previous_form in ("du", "sie") and rep.form in ("du", "sie")
                and rep.form != previous_form):
            rep.previous_form = previous_form
    return rep

# ----------------------------------------------------------------------------- footer

_LABEL = {
    "de": {"du": "du", "sie": "Sie"},
    "en": {"du": "du", "sie": "Sie"},
}


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _quote(s: str, lang: str) -> str:
    s = s.replace("*", "").replace("_", " ").strip()
    return f"„{s}“" if lang == "de" else f"\"{s}\""


def footer(rep: Report, lang: str) -> str:
    """One italic line that summarises the findings, or "" when there are none."""
    if not rep.has_findings:
        return ""
    de = lang == "de"
    parts: list[str] = []
    if rep.dashes_fixed:
        parts.append(_plural(rep.dashes_fixed, "Gedankenstrich ersetzt", "Gedankenstriche ersetzt") if de
                     else _plural(rep.dashes_fixed, "dash replaced", "dashes replaced"))
    elif rep.dashes:
        parts.append(_plural(rep.dashes, "Gedankenstrich", "Gedankenstriche") if de
                     else _plural(rep.dashes, "dash", "dashes"))
    if rep.phrases:
        total = sum(p.count for p in rep.phrases)
        shown = ", ".join(_quote(p.text, lang) for p in rep.phrases[:3])
        more = len(rep.phrases) - 3
        if more > 0:
            shown += f" +{more}"
        label = (_plural(total, "KI-Floskel", "KI-Floskeln") if de
                 else _plural(total, "AI phrase", "AI phrases"))
        parts.append(f"{label} ({shown})")
    if rep.mixed:
        du = sum(a for a, _ in rep.mixed)
        sie = sum(b for _, b in rep.mixed)
        parts.append(f"du und Sie im selben Absatz gemischt (du {du}, Sie {sie})" if de
                     else f"du and Sie mixed in one paragraph (du {du}, Sie {sie})")
    if rep.wrong_form and rep.expected:
        want = _LABEL["de"][rep.expected]
        other = "Sie" if rep.expected == "du" else "du"
        parts.append(f"{rep.wrong_form}x {other} statt {want}" if de
                     else f"{rep.wrong_form}x {other} instead of {want}")
    elif rep.previous_form and not rep.mixed:
        a, b = _LABEL["de"][rep.previous_form], _LABEL["de"][rep.form or "du"]
        parts.append(f"Anrede gewechselt: vorher {a}, jetzt {b}" if de
                     else f"form of address switched: {a} before, {b} now")
    return "*writing-guard: " + "; ".join(parts) + ".*"
