"""Personal-data detectors and request scanning for privacy-xray.

Everything here is pure Python (standard library) and works on plain strings. Every regex is
built to run in linear time on hostile input: each pattern either starts with a lookbehind that
only allows a match at the start of a run, or uses bounded quantifiers, so a long run of digits,
letters, spaces or ``@`` signs cannot trigger quadratic backtracking. Matches are then validated
(IBAN mod 97, Luhn, Steuer-ID and USt-IdNr check digits) to keep false positives low.

Only counts leave this module. Matched values are never stored or returned to the ledger.

Canary values and watch terms are matched as whole words: a hit needs a non-word character (or the
start/end of the text) on both sides, so the watch term "Tim" does not hit "timestamp".
"""
from __future__ import annotations

import hashlib
import json
import re
import ipaddress
import threading
from collections import OrderedDict
from typing import Any, Iterable, Iterator, Optional

# Regex detection looks at the first MAX_REGEX_CHARS of every message, and at most
# MAX_REQUEST_REGEX_CHARS of new (not cached) text per request, newest message first. A request
# whose text did not fit is marked incomplete. Canary and watch-term matching (substring search in
# C plus a word-boundary check per occurrence) looks at up to MAX_SUBSTRING_CHARS per message.
MAX_REGEX_CHARS = 1_000_000
MAX_REQUEST_REGEX_CHARS = 2_000_000
MAX_SUBSTRING_CHARS = 4_000_000
CACHE_SIZE = 4096

DETECTORS = ("email", "iban", "card", "phone", "ipv4", "tax_id_de", "vat_id_de")

# --------------------------------------------------------------------------- patterns

EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]{1,64}@(?:[A-Za-z0-9-]{1,63}\.){1,8}[A-Za-z]{2,24}"
    r"(?![A-Za-z0-9-])")
IBAN_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2}[0-9]{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?(?![A-Za-z0-9])")
# A digit run right after "+" is a phone number (+49 176 ...), never a card.
CARD_RE = re.compile(r"(?<![0-9+])[0-9](?:[ -]?[0-9]){12,18}(?![0-9])")
PHONE_RE = re.compile(r"(?<![A-Za-z0-9+])\+[1-9](?:[ ./-]?[0-9]){7,14}(?![0-9])")
# Not after a letter, digit or dot (v1.2.3.4, x1.2.3.4, 1.2.3.4.5), not followed by ".digit".
IPV4_RE = re.compile(
    r"(?<![0-9.A-Za-z])(?:(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\.){3}"
    r"(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])(?![0-9]|\.[0-9])")
TAX_ID_RE = re.compile(r"(?<![0-9])[1-9][0-9](?: ?[0-9]{3}){3}(?![0-9])")
VAT_DE_RE = re.compile(r"(?<![A-Za-z0-9])DE ?[0-9]{9}(?![0-9])")

# IBAN lengths per country (ISO 13616 registry, common countries; others accepted at 15..34).
IBAN_LENGTHS = {
    "AD": 24, "AE": 23, "AT": 20, "BE": 16, "BG": 22, "CH": 21, "CY": 28, "CZ": 24, "DE": 22,
    "DK": 18, "EE": 20, "ES": 24, "FI": 18, "FR": 27, "GB": 22, "GI": 23, "GR": 27, "HR": 21,
    "HU": 28, "IE": 22, "IS": 26, "IT": 27, "LI": 21, "LT": 20, "LU": 20, "LV": 21, "MC": 27,
    "MT": 31, "NL": 18, "NO": 15, "PL": 28, "PT": 25, "RO": 24, "SE": 24, "SI": 19, "SK": 24,
    "SM": 27, "TR": 26, "UA": 29,
}


def iban_valid(raw: str) -> bool:
    s = raw.replace(" ", "").upper()
    if len(s) < 15 or len(s) > 34 or not s[:2].isalpha() or not s[2:4].isdigit():
        return False
    want = IBAN_LENGTHS.get(s[:2])
    if want is not None and len(s) != want:
        return False
    moved = s[4:] + s[:4]
    digits = "".join(str(int(ch, 36)) for ch in moved)
    return int(digits) % 97 == 1


def iban_check_digits(country: str, bban: str) -> str:
    """Two check digits that make ``country + cd + bban`` a valid IBAN."""
    digits = "".join(str(int(ch, 36)) for ch in (bban + country + "00").upper())
    return f"{98 - int(digits) % 97:02d}"


def luhn_valid(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = ord(ch) - 48
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def _card_brand_ok(d: str) -> bool:
    """Known issuer ranges (IIN) with their lengths: Visa 4, Mastercard 51-55 and 2221-2720,
    Amex 34/37, Discover 6011/644-649/65, JCB 3528-3589, Diners 300-305/36/38-39, UnionPay 62."""
    n = len(d)
    if d[0] == "4":
        return n in (13, 16, 19)
    two, three, four = int(d[:2]), int(d[:3]), int(d[:4])
    if 51 <= two <= 55 or 2221 <= four <= 2720:
        return n == 16
    if two in (34, 37):
        return n == 15
    if d.startswith("6011") or two == 65 or 644 <= three <= 649:
        return n in (16, 19)
    if 3528 <= four <= 3589:
        return 16 <= n <= 19
    if 300 <= three <= 305 or two in (36, 38, 39):
        return 14 <= n <= 19
    if two == 62:
        return 16 <= n <= 19
    return False


def card_valid(raw: str) -> bool:
    d = re.sub(r"[ -]", "", raw)
    if len(d) < 13 or len(d) > 19 or len(set(d)) < 2:
        return False
    return _card_brand_ok(d) and luhn_valid(d)


def tax_id_de_valid(raw: str) -> bool:
    """German Steuerliche Identifikationsnummer: 11 digits, ISO 7064 MOD 11,10 check digit and the
    digit distribution rule (in the first ten digits exactly one digit repeats, 2 or 3 times)."""
    d = raw.replace(" ", "")
    if len(d) != 11 or not d.isdigit() or d[0] == "0":
        return False
    counts = [d[:10].count(c) for c in set(d[:10])]
    if not ((sorted(counts)[-1] in (2, 3)) and sum(1 for c in counts if c > 1) == 1):
        return False
    product = 10
    for ch in d[:10]:
        s = (int(ch) + product) % 10 or 10
        product = (s * 2) % 11
    check = (11 - product) % 10
    return check == int(d[10])


def vat_de_valid(raw: str) -> bool:
    d = raw.replace(" ", "")[2:]
    if len(d) != 9 or not d.isdigit():
        return False
    product = 10
    for ch in d[:8]:
        s = (int(ch) + product) % 10 or 10
        product = (2 * s) % 11
    check = 11 - product
    return (0 if check == 10 else check) == int(d[8])


def phone_valid(raw: str) -> bool:
    digits = sum(1 for ch in raw if ch.isdigit())
    return 8 <= digits <= 15


def ipv4_valid(raw: str) -> bool:
    """Public addresses only: no loopback, private, link-local, CGNAT (100.64/10), multicast,
    reserved, documentation ranges, 0.0.0.0 or broadcast."""
    try:
        ip = ipaddress.IPv4Address(raw)
    except ValueError:
        return False
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_reserved \
            or ip.is_unspecified or ip in _CGNAT or str(ip) == "255.255.255.255":
        return False
    return ip.is_global


_CGNAT = ipaddress.IPv4Network("100.64.0.0/10")
# Role and system mailboxes are not personal data of a person.
_ROLE_MAILBOXES = frozenset({"git", "noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon",
                             "postmaster", "notifications", "notification"})


def email_valid(raw: str) -> bool:
    return raw.split("@", 1)[0].lower() not in _ROLE_MAILBOXES


_CHECKS = (
    ("email", EMAIL_RE, email_valid),
    ("iban", IBAN_RE, iban_valid),
    ("card", CARD_RE, card_valid),
    ("phone", PHONE_RE, phone_valid),
    ("ipv4", IPV4_RE, ipv4_valid),
    ("tax_id_de", TAX_ID_RE, tax_id_de_valid),
    ("vat_id_de", VAT_DE_RE, vat_de_valid),
)


def detect(text: str, enabled: Iterable[str] = DETECTORS, limit: int = MAX_REGEX_CHARS) -> dict[str, int]:
    """Count validated matches per data type in ``text[:limit]``. Only counts are returned."""
    out: dict[str, int] = {}
    if not text:
        return out
    chunk = text[:limit] if limit and len(text) > limit else text
    on = set(enabled)
    phone_spans: list[tuple[int, int]] = []
    if "card" in on:
        phone_spans = [(m.start(), m.end()) for m in PHONE_RE.finditer(chunk) if phone_valid(m.group(0))]
    for name, rx, check in _CHECKS:
        if name not in on:
            continue
        n = 0
        for m in rx.finditer(chunk):
            if check is not None and not check(m.group(0)):
                continue
            if name == "card" and _inside(m.start(), m.end(), phone_spans):
                continue
            n += 1
        if n:
            out[name] = n
    return out


def _inside(a: int, b: int, spans: list[tuple[int, int]]) -> bool:
    """Whether [a, b) overlaps one of the (sorted) spans; binary search, so linear overall."""
    lo, hi = 0, len(spans)
    while lo < hi:
        mid = (lo + hi) // 2
        if spans[mid][1] <= a:
            lo = mid + 1
        else:
            hi = mid
    return lo < len(spans) and spans[lo][0] < b


def find_spans(text: str, enabled: Iterable[str] = DETECTORS) -> list[tuple[int, int, str]]:
    """Spans of validated matches (used only to mask snippets, never stored)."""
    spans: list[tuple[int, int, str]] = []
    on = set(enabled)
    phone_spans = [(m.start(), m.end()) for m in PHONE_RE.finditer(text) if phone_valid(m.group(0))]
    for name, rx, check in _CHECKS:
        if name not in on:
            continue
        for m in rx.finditer(text):
            if check is not None and not check(m.group(0)):
                continue
            if name == "card" and _inside(m.start(), m.end(), phone_spans):
                continue
            spans.append((m.start(), m.end(), name))
    return spans

# --------------------------------------------------------------------------- message walking

_SKIP_KEYS = {"image_url", "source", "data", "image", "input_audio", "audio", "file", "file_data",
              "cache_control", "signature", "encrypted_content", "id", "tool_use_id", "call_id",
              "type", "name", "role", "status"}
FIELDS = ("system", "user", "assistant", "tool")


def _collect(obj: Any, out: list[str], depth: int = 0) -> None:
    if depth > 8:
        return
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in _SKIP_KEYS:
                continue
            if k in ("input", "arguments") and isinstance(v, (dict, list)):
                try:
                    out.append(json.dumps(v, ensure_ascii=False))
                except Exception:  # noqa: BLE001
                    pass
                continue
            _collect(v, out, depth + 1)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect(v, out, depth + 1)


def _get(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def iter_fields(request_messages: Any, system_prompt: Any = None) -> Iterator[tuple[str, str]]:
    """Yield ``(field, text)`` for every message part: system, user, assistant or tool.

    Handles chat-completions messages, Anthropic content blocks (``tool_result`` inside a user
    message counts as tool) and Responses API input items. Images and binary parts are skipped."""
    saw_system = False
    for msg in request_messages if isinstance(request_messages, (list, tuple)) else []:
        role = str(_get(msg, "role") or "").lower()
        mtype = str(_get(msg, "type") or "").lower()
        if mtype in ("function_call_output", "custom_tool_call_output", "tool_result"):
            parts: list[str] = []
            _collect(_get(msg, "output") if _get(msg, "output") is not None else _get(msg, "content"), parts)
            yield "tool", "\n".join(parts)
            continue
        if mtype in ("function_call", "custom_tool_call", "reasoning"):
            parts = []
            _collect(_get(msg, "arguments") or _get(msg, "input") or _get(msg, "summary"), parts)
            yield "assistant", "\n".join(parts)
            continue
        if role in ("system", "developer"):
            field = "system"
            saw_system = True
        elif role == "tool" or role == "function":
            field = "tool"
        elif role == "assistant" or role == "model":
            field = "assistant"
        else:
            field = "user"
        content = _get(msg, "content")
        if isinstance(content, list) and field in ("user", "assistant"):
            normal: list[str] = []
            tool_parts: list[str] = []
            for block in content:
                btype = str(_get(block, "type") or "").lower()
                target = tool_parts if btype == "tool_result" else normal
                _collect(block, target)
            if normal:
                yield field, "\n".join(normal)
            if tool_parts:
                yield "tool", "\n".join(tool_parts)
        else:
            parts = []
            _collect(content, parts)
            if parts:
                yield field, "\n".join(parts)
        calls = _get(msg, "tool_calls")
        if calls:
            parts = []
            _collect(calls, parts)
            if parts:
                yield "assistant", "\n".join(parts)
    if system_prompt and not saw_system:
        parts = []
        _collect(system_prompt, parts)
        if parts:
            yield "system", "\n".join(parts)

# --------------------------------------------------------------------------- matcher


def _is_word(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def contains_word(low: str, value: str) -> bool:
    """``value`` occurs in ``low`` with no word character directly before or after it.

    Linear: ``str.find`` (C) per occurrence plus two character checks. Both are lowercase."""
    if not value:
        return False
    first_word, last_word = _is_word(value[0]), _is_word(value[-1])
    start = 0
    n = len(value)
    while True:
        pos = low.find(value, start)
        if pos < 0:
            return False
        before_ok = pos == 0 or not first_word or not _is_word(low[pos - 1])
        end = pos + n
        after_ok = end >= len(low) or not last_word or not _is_word(low[end])
        if before_ok and after_ok:
            return True
        start = pos + 1


class Needles:
    """Canary values and watch terms, lowercased, for plain substring search."""

    def __init__(self, canaries: Iterable[dict] = (), watch_terms: Iterable[str] = ()):
        self.canary: list[tuple[str, tuple[str, ...]]] = []
        for c in canaries:
            cid = str(c.get("id") or "")
            vals = tuple(sorted({v.lower() for v in c.get("match", []) if isinstance(v, str) and len(v) >= 4}))
            if cid and vals:
                self.canary.append((cid, vals))
        self.watch: tuple[str, ...] = tuple(sorted({t.strip().lower() for t in watch_terms
                                                    if isinstance(t, str) and len(t.strip()) >= 3}))
        sig = json.dumps([self.canary, self.watch])
        self.generation = hashlib.sha1(sig.encode("utf-8")).hexdigest()[:12]

    def all_values(self) -> list[str]:
        vals = [v for _, vs in self.canary for v in vs] + list(self.watch)
        return sorted(set(vals), key=len, reverse=True)


class Scanner:
    """Per-message detection with a bounded LRU cache keyed by content hash.

    A long conversation is re-sent on every API call; only new messages cost regex time."""

    def __init__(self, size: int = CACHE_SIZE):
        self.size = size
        self._cache: "OrderedDict[str, tuple]" = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def _scan_one(self, text: str, needles: Needles, enabled: tuple[str, ...], limit: int) -> tuple:
        counts = detect(text, enabled, limit=limit) if limit > 0 else {}
        low = text[:MAX_SUBSTRING_CHARS].lower() if (needles.canary or needles.watch) else ""
        canary = tuple(cid for cid, vals in needles.canary if any(contains_word(low, v) for v in vals))
        watch = sum(1 for t in needles.watch if contains_word(low, t))
        return counts, canary, watch

    def scan_text(self, field: str, text: str, needles: Needles, enabled: tuple[str, ...],
                  regex_budget: int) -> tuple:
        """``(counts, canary_ids, watch_hits, complete, regex_chars_spent)`` for one text.

        A cached result costs no budget. ``complete`` is False when regex detection did not see the
        whole text (per-message cap or request budget). A result cut by the request budget is never
        cached: the same message in a shorter request is scanned again, fully."""
        digest = hashlib.sha1(text.encode("utf-8", "surrogatepass")).hexdigest()
        key = f"{needles.generation}|{','.join(enabled)}|{digest}"
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                self.hits += 1
                return hit + (0,)
        limit = max(0, min(MAX_REGEX_CHARS, regex_budget))
        counts, canary, watch = self._scan_one(text, needles, enabled, limit)
        complete = len(text) <= limit
        budget_cut = limit < min(MAX_REGEX_CHARS, len(text))
        result = (counts, canary, watch, complete)
        with self._lock:
            self.misses += 1
            if not budget_cut:
                self._cache[key] = result
                while len(self._cache) > self.size:
                    self._cache.popitem(last=False)
        return result + (min(len(text), limit),)

    def scan_request(self, request_messages: Any, system_prompt: Any, needles: Needles,
                     enabled: tuple[str, ...]) -> dict[str, Any]:
        """Summary for one outgoing request: chars, type counts, canary fields, watch hits.

        Messages are scanned newest first, so the text that just came in always gets the regex
        budget; ``truncated`` says that some text was not (fully) scanned for data types."""
        chars = 0
        types: dict[str, int] = {}
        canary: dict[str, set] = {}
        watch_fields: set = set()
        budget = MAX_REQUEST_REGEX_CHARS
        truncated = False
        parts = [(f, t) for f, t in iter_fields(request_messages, system_prompt) if t]
        # The system prompt (yielded last when it is not part of the messages) is stable and almost
        # always cached; the newest message is the last one in the list.
        for field, text in reversed(parts):
            chars += len(text)
            counts, cids, watch, complete, spent = self.scan_text(field, text, needles, enabled, budget)
            budget -= spent
            truncated = truncated or not complete
            for k, v in counts.items():
                types[k] = types.get(k, 0) + v
            for cid in cids:
                canary.setdefault(cid, set()).add(field)
            if watch:
                watch_fields.add(field)
        return {
            "chars": chars,
            "types": types,
            "canary": [{"id": cid, "fields": sorted(f, key=FIELDS.index)} for cid, f in sorted(canary.items())],
            "watch_fields": sorted(watch_fields, key=FIELDS.index),
            "truncated": truncated,
        }

# --------------------------------------------------------------------------- masking


def mask_value(value: str) -> str:
    """'Mara Vintrell' -> 'M*** V*******'; keeps the first character of each word."""
    out = []
    for word in value.split(" "):
        out.append(word[:1] + "*" * max(len(word) - 1, 0) if word else word)
    return " ".join(out)


_DIGIT_RUN_RE = re.compile(r"[0-9](?:[ ./-]?[0-9]){5,40}")


def masked_snippet(text: str, start: int, end: int, radius: int = 48,
                   enabled: Iterable[str] = DETECTORS) -> str:
    """A short window around ``text[start:end]``: the hit, every detected value and every run of
    six or more digits are masked (the detection window is wider, so values cut by the edge of
    the snippet are still recognised)."""
    a, b = max(0, start - radius), min(len(text), end + radius)
    wa, wb = max(0, a - 48), min(len(text), b + 48)
    wide = text[wa:wb]
    spans = [(start - wa, end - wa)] + [(s, e) for s, e, _ in find_spans(wide, enabled)]
    spans += [(m.start(), m.end()) for m in _DIGIT_RUN_RE.finditer(wide)]
    chars = list(wide)
    for s, e in spans:
        s, e = max(0, s), min(len(chars), e)
        for i in range(s + 1, e):
            if chars[i] not in " .-@":
                chars[i] = "*"
    window = "".join(chars)[a - wa: a - wa + (b - a)]
    snippet = window.replace("\n", " ").replace("\r", " ")
    return ("..." if a > 0 else "") + snippet.strip() + ("..." if b < len(text) else "")


def compile_masker(values: list[str]) -> Optional[re.Pattern]:
    """Case-insensitive alternation of literal values (longest first) for the guard, as whole
    words: no word character directly before or after a match ("Tim" never hits "timestamp").

    Linear: the lookarounds are single characters and the alternation holds literals only."""
    vals = [v for v in values if v]
    if not vals:
        return None
    alts = []
    for v in sorted(set(vals), key=len, reverse=True):
        alts.append((r"(?<!\w)" if _is_word(v[0]) else "") + re.escape(v) + (r"(?!\w)" if _is_word(v[-1]) else ""))
    return re.compile("|".join(alts), re.IGNORECASE)
