"""Runtime state of privacy-xray under <HERMES_HOME>/plugin-data/privacy-xray/.

* ledger.jsonl (+ ledger.1.jsonl after rotation): one line of METADATA per outgoing model request.
  Never message content, never matched values.
* canaries.json: the fictitious canary persons (they are made up, so storing them is harmless).
* reports/: HTML leak maps and access reports the user asked for.

Gateway, desktop and CLI can run in parallel: every write takes an exclusive file lock, whole-file
writes go through a temp file and os.replace.

Permissions: the folder is 0700 and every file the plugin writes is created 0600 (``os.open`` with
a mode, so there is no moment with wider rights), like Hermes keeps state.db. Access reports hold
masked but real excerpts about third persons.
"""
from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Iterable, Optional

from . import detect

try:
    import fcntl  # Linux/macOS; without it writes run unlocked
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

PLUGIN_ID = "privacy-xray"
MAX_CANARIES = 5
DIR_MODE = 0o700
FILE_MODE = 0o600


def hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home  # public helper
        return Path(get_hermes_home())
    except Exception:  # noqa: BLE001
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def _private_dir(d: Path) -> Path:
    d.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
    try:
        if d.stat().st_mode & 0o777 != DIR_MODE:
            os.chmod(d, DIR_MODE)
    except OSError:
        pass
    return d


def data_dir() -> Path:
    return _private_dir(hermes_home() / "plugin-data" / PLUGIN_ID)


def open_private(path: Path, flags: int = os.O_WRONLY | os.O_CREAT | os.O_TRUNC, encoding: str = "utf-8"):
    """Text file handle on a file created with mode 0600 (an existing file is narrowed to 0600)."""
    fd = os.open(path, flags, FILE_MODE)
    try:
        os.fchmod(fd, FILE_MODE)
    except (OSError, AttributeError):
        pass
    return os.fdopen(fd, "a" if flags & os.O_APPEND else "w", encoding=encoding)


def write_text_private(path: Path, text: str) -> None:
    """Atomic write (PID temp file + os.replace) of a 0600 file."""
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    with open_private(tmp) as fh:
        fh.write(text)
    os.replace(tmp, path)


class Locked:
    """Exclusive inter-process lock on <data_dir>/.lock."""

    def __init__(self, path: Optional[Path] = None):
        self.fh = open_private(path or (data_dir() / ".lock"), os.O_WRONLY | os.O_CREAT | os.O_APPEND)

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


def write_json(path: Path, data: Any) -> None:
    write_text_private(path, json.dumps(data, ensure_ascii=False, indent=1))


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default

# --------------------------------------------------------------------------- ledger


def ledger_paths() -> tuple[Path, Path]:
    d = data_dir()
    return d / "ledger.jsonl", d / "ledger.1.jsonl"


def append_ledger(record: dict, max_bytes: int) -> None:
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    cur, old = ledger_paths()
    with Locked():
        try:
            size = cur.stat().st_size
        except OSError:
            size = 0
        if size and size + len(line) > max_bytes:
            os.replace(cur, old)
            try:
                os.chmod(old, FILE_MODE)
            except OSError:
                pass
        with open_private(cur, os.O_WRONLY | os.O_CREAT | os.O_APPEND) as fh:
            fh.write(line)


def read_ledger(limit: int = 50000, since: float = 0.0) -> list[dict]:
    """Newest-last list of ledger records (rotated file first)."""
    out: list[dict] = []
    cur, old = ledger_paths()
    for path in (old, cur):
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        rec = json.loads(line)
                    except Exception:  # noqa: BLE001
                        continue
                    if isinstance(rec, dict) and float(rec.get("ts") or 0) >= since:
                        out.append(rec)
        except OSError:
            continue
    return out[-limit:]


def ledger_size() -> int:
    total = 0
    for p in ledger_paths():
        try:
            total += p.stat().st_size
        except OSError:
            pass
    return total

# --------------------------------------------------------------------------- canaries

_FIRST = ("Mara", "Ilse", "Jonas", "Theo", "Lena", "Oskar", "Frieda", "Milan", "Nora", "Elias", "Greta",
          "Jasper", "Ida", "Linus", "Wilma", "Anton")
_SURNAME_A = ("Vint", "Quill", "Brask", "Holt", "Marw", "Tesk", "Lorr", "Fenn", "Drav", "Kell", "Ostr",
              "Pell", "Rusk", "Sorv", "Wend", "Zell")
_SURNAME_B = ("rell", "ander", "ovic", "mayr", "ingham", "steed", "berg", "quist", "ova", "hardt", "ley",
              "wick", "enko", "aine", "dorf", "son")
# Combinations that are real names or words (the surname alone is a match value).
_REAL_SURNAMES = frozenset({"lorraine", "ostrander", "ostrova", "kellberg", "fennwick", "wendley", "holtson",
                            "kellson", "pellwick", "zellberg", "wendson", "holtdorf", "brasksteed", "fennley",
                            "kelley", "holtley", "rusksteed", "pellley", "kellley", "zelley", "wendell",
                            "quillberg", "marwick", "holtberg", "teskey", "fennson", "pellson", "ruskin"})


def _pick(seq: tuple[str, ...]) -> str:
    return seq[secrets.randbelow(len(seq))]


def _digits(n: int) -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(n))


def make_canary() -> dict:
    """A fictitious person. Every value is fake on purpose:

    * e-mail at example.org (reserved for documentation by RFC 2606),
    * German IBAN with a valid check sum, bank code starting with 0 (outside the regular German
      clearing areas 1 to 8, so it cannot belong to a real bank), random account number,
    * phone number in the UK Ofcom range +44 7700 900000 to 900999, reserved for drama and fiction.
    """
    first = _pick(_FIRST)
    last = _pick(_SURNAME_A) + _pick(_SURNAME_B)
    while last.lower() in _REAL_SURNAMES:
        last = _pick(_SURNAME_A) + _pick(_SURNAME_B)
    tag = secrets.token_hex(2)
    email = f"{first.lower()}.{last.lower()}.{tag}@example.org"
    bban = "0" + _digits(7) + _digits(10)
    iban = "DE" + detect.iban_check_digits("DE", bban) + bban
    iban_grouped = " ".join(iban[i:i + 4] for i in range(0, len(iban), 4))
    ph = _digits(3)
    phone = f"+44 7700 900{ph}"
    cid = "c" + secrets.token_hex(3)
    return {
        "id": cid,
        "created": int(time.time()),
        "name": f"{first} {last}",
        "email": email,
        "iban": iban_grouped,
        "phone": phone,
        # exact substrings that count as a canary hit (case insensitive)
        "match": sorted({f"{first} {last}", last, email, iban, iban_grouped, phone, f"+447700900{ph}"}),
    }


def load_canaries() -> list[dict]:
    data = read_json(data_dir() / "canaries.json", {})
    items = data.get("canaries") if isinstance(data, dict) else None
    return [c for c in items if isinstance(c, dict) and c.get("id")] if isinstance(items, list) else []


def add_canary() -> dict:
    c = make_canary()
    path = data_dir() / "canaries.json"
    with Locked():
        items = load_canaries()
        items.append(c)
        write_json(path, {"version": 1, "canaries": items[-MAX_CANARIES:]})
    return c


def latest_canary() -> Optional[dict]:
    items = load_canaries()
    return items[-1] if items else None


def canary_by_id(cid: str) -> Optional[dict]:
    for c in load_canaries():
        if c.get("id") == cid:
            return c
    return None


def reports_dir() -> Path:
    return _private_dir(data_dir() / "reports")


def save_last(name: str, data: Any) -> None:
    try:
        with Locked():
            write_json(data_dir() / f"last-{name}.json", data)
    except Exception:  # noqa: BLE001
        pass


def load_last(name: str) -> Any:
    return read_json(data_dir() / f"last-{name}.json", None)


def file_list(paths: Iterable[Path]) -> list[str]:
    return [str(p) for p in paths]
