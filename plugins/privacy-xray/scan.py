"""Read-only search of Hermes' local stores for a set of strings (canary values or a person).

Stores: state.db (messages, session titles, system prompts), sessions/ files (including request
dumps), memories/, logs/, cron/output/, other plugins' plugin-data, paste and pending folders.
Everything is opened read-only; SQLite through ``file:<escaped path>?mode=ro``.

state.db messages: candidates come from Hermes' own full-text indexes (``messages_fts``: words, all
roles, tool output up to its first 8 KB; ``messages_fts_trigram``: substrings, no tool rows); each
candidate is confirmed with LIKE. Without full-text indexes (old schema) a LIKE scan is the fallback.
The index does not hold tool output beyond 8 KB: ``deep=True`` adds a LIKE scan over those long tool
rows (seconds on a large database). Without it the result says so in ``coverage``; a deadline that
cuts a query sets ``partial``.

Files are read in blocks under a byte and time budget. A file larger than ``max_file_bytes`` is
read from its end (logs grow at the end, so the newest lines are covered); such files and files cut
by the budget are listed in ``partial_files`` and make the search incomplete.
"""
from __future__ import annotations

import os
import re
import sqlite3
import time
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Optional

from . import detect

BLOCK = 1 << 20
TEXT_SUFFIXES = {".jsonl", ".json", ".md", ".txt", ".log", ".yaml", ".yml", ".csv", ".html", ".xml", ""}
FILE_STORES = (
    ("sessions", "sessions", "session files (JSONL transcripts, request dumps)"),
    ("memories", "memories", "memory files (MEMORY.md, USER.md)"),
    ("logs", "logs", "log files"),
    ("cron_output", "cron/output", "scheduled job output"),
    ("plugin_data", "plugin-data", "data of other plugins"),
    ("pastes", "pastes", "pasted text"),
    ("composer_pastes", "composer-pastes", "pasted text (composer)"),
    ("pending", "pending_messages", "queued messages"),
)


class Budget:
    def __init__(self, seconds: float, max_bytes: int):
        self.deadline = time.monotonic() + seconds
        self.left = max_bytes
        self.cut = False

    def ok(self) -> bool:
        if time.monotonic() > self.deadline or self.left <= 0:
            self.cut = True
            return False
        return True


def _phrase(term: str) -> Optional[str]:
    tokens = re.findall(r"[^\W_]{1,64}", term)
    if not tokens:
        return None
    return '"' + " ".join(tokens[:16]) + '"'


def _like(term: str) -> str:
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _connect(db: Path, clock: dict) -> sqlite3.Connection:
    """Read-only connection; a query is interrupted once ``clock['deadline']`` has passed."""
    conn = sqlite3.connect("file:" + urllib.request.pathname2url(str(db)) + "?mode=ro", uri=True, timeout=2.0)
    conn.set_progress_handler(lambda: 1 if time.monotonic() > clock["deadline"] else 0, 20000)
    return conn


def _tables(conn: sqlite3.Connection) -> set:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}


def search_state_db(home: Path, terms: list[str], seconds: float = 15.0, snippets: int = 0,
                    snippet_term: str = "", deep: bool = False) -> dict:
    """Hits in state.db per place: messages (by role), session titles, system prompts."""
    db = home / "state.db"
    out: dict[str, Any] = {"store": "state.db", "path": str(db), "exists": db.exists(), "places": {},
                           "partial": False, "snippets": [], "coverage": [], "deep": bool(deep)}
    if not db.exists() or not terms:
        return out
    t_end = time.monotonic() + seconds
    clock = {"deadline": t_end}
    try:
        conn = _connect(db, clock)
    except sqlite3.Error as exc:
        out["error"] = str(exc)[:200]
        return out
    try:
        tabs = _tables(conn)
        likes = [_like(t) for t in terms]
        where_like = " OR ".join(["m.content LIKE ? ESCAPE '\\'"] * len(likes)
                                 + (["m.tool_calls LIKE ? ESCAPE '\\'"] * len(likes)))
        params_like = likes + likes
        candidate_sql = None
        cand_params: list = []
        fts = []
        for t in terms:
            ph = _phrase(t)
            if not ph:
                continue
            if "messages_fts" in tabs:
                fts.append(("SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?", ph))
            if "messages_fts_trigram" in tabs and len(t) >= 3:
                fts.append(("SELECT rowid FROM messages_fts_trigram WHERE messages_fts_trigram MATCH ?",
                            '"' + t.replace('"', '""') + '"'))
        if fts:
            candidate_sql = " UNION ".join(q for q, _ in fts)
            cand_params = [p for _, p in fts]
        role_rows: list = []
        try:
            if candidate_sql:
                sql = (f"SELECT m.role, m.session_id, COUNT(*), MIN(m.timestamp), MAX(m.timestamp) "
                       f"FROM messages m WHERE m.id IN ({candidate_sql}) AND ({where_like}) GROUP BY m.role, m.session_id")
                role_rows = conn.execute(sql, cand_params + params_like).fetchall()
            else:
                sql = (f"SELECT m.role, m.session_id, COUNT(*), MIN(m.timestamp), MAX(m.timestamp) "
                       f"FROM messages m WHERE ({where_like}) GROUP BY m.role, m.session_id")
                role_rows = conn.execute(sql, params_like).fetchall()
        except sqlite3.OperationalError:
            out["partial"] = True
            out["cut"] = "messages"
        # session titles and stored system prompts (small tables / bounded scans)
        title_where = " OR ".join(["title LIKE ? ESCAPE '\\'"] * len(likes))
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM sessions WHERE {title_where}", likes).fetchone()[0]
            if n:
                out["places"]["session_titles"] = {"count": n}
        except sqlite3.OperationalError:
            out["partial"] = True
        if "system_prompts" in tabs:
            sp_where = " OR ".join(["prompt LIKE ? ESCAPE '\\'"] * len(likes))
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM system_prompts WHERE {sp_where}", likes).fetchone()[0]
                if n:
                    out["places"]["system_prompts"] = {"count": n}
            except sqlite3.OperationalError:
                out["partial"] = True
        if "delivery_obligations" in tabs:
            d_where = " OR ".join(["content LIKE ? ESCAPE '\\'"] * len(likes))
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM delivery_obligations WHERE {d_where}", likes).fetchone()[0]
                if n:
                    out["places"]["delivery_queue"] = {"count": n}
            except sqlite3.OperationalError:
                out["partial"] = True
        # The word index holds tool output only up to its first 8 KB: long tool outputs are searched
        # in full only on request (deep), as one LIKE pass over those rows, last, with the remaining
        # time. Measured on a 1.6 GB state.db: about 1 s with a warm page cache, up to 16 s cold.
        deep_rows: list = []
        if candidate_sql and deep:
            sql2 = ("SELECT m.role, m.session_id, COUNT(*), MIN(m.timestamp), MAX(m.timestamp) "
                    f"FROM messages m WHERE m.role = 'tool' AND length(m.content) > 8192 "
                    f"AND m.id NOT IN ({candidate_sql}) AND ({where_like}) GROUP BY m.role, m.session_id")
            try:
                deep_rows = conn.execute(sql2, cand_params + params_like).fetchall()
            except sqlite3.OperationalError:
                out["partial"] = True
                out["deep_scan_cut"] = True
                out["cut"] = "deep"
        elif candidate_sql:
            out["coverage"].append("tool_tail")
        role_rows = list(role_rows) + deep_rows
        merged: dict[str, int] = {}
        sessions: set = set()
        times: list = []
        for role, sid, n, t0, t1 in role_rows:
            merged[role] = merged.get(role, 0) + int(n)
            sessions.add(sid)
            times += [t for t in (t0, t1) if t is not None]
        if merged:
            out["places"]["messages"] = {
                "count": sum(merged.values()),
                "sessions": len(sessions),
                "by_role": dict(sorted(merged.items())),
                "first": min(times) if times else None,
                "last": max(times) if times else None,
            }
        if snippets and snippet_term and merged:
            clock["deadline"] = time.monotonic() + 3.0
            q = (f"SELECT m.session_id, m.role, m.timestamp, m.content FROM messages m WHERE "
                 + (f"m.id IN ({candidate_sql}) AND " if candidate_sql else "")
                 + "m.content LIKE ? ESCAPE '\\' ORDER BY m.timestamp DESC LIMIT ?")
            try:
                rows = conn.execute(q, (cand_params if candidate_sql else []) + [_like(snippet_term), snippets]).fetchall()
            except sqlite3.OperationalError:
                rows = []
            low_term = snippet_term.lower()
            for sid, role, ts, content in rows:
                text = str(content or "")
                pos = text.lower().find(low_term)
                if pos >= 0:
                    out["snippets"].append({"place": "messages", "session": sid, "role": role, "ts": ts,
                                            "text": detect.masked_snippet(text, pos, pos + len(snippet_term))})
    finally:
        conn.close()
    return out


def _iter_files(root: Path, exclude: Iterable[Path], max_files: int = 20000):
    excl = [e.resolve() for e in exclude]
    n = 0
    if not root.is_dir():
        return
    for p in sorted(root.rglob("*")):
        if n >= max_files:
            return
        try:
            if not p.is_file() or p.is_symlink():
                continue
            rp = p.resolve()
        except OSError:
            continue
        if any(rp == e or e in rp.parents for e in excl):
            continue
        name = p.name.lower()
        suffix = p.suffix.lower()
        rotated = re.fullmatch(r".{1,200}\.log\.[0-9]{1,3}", name) is not None
        if suffix not in TEXT_SUFFIXES and not rotated:
            continue
        if suffix in (".db", ".sqlite") or name.endswith(("-wal", "-shm", ".lock", ".pid")):
            continue
        n += 1
        yield p


def search_file(path: Path, needles: list[str], budget: Budget, max_file_bytes: int,
                snippet_term: str = "") -> tuple[int, Optional[str], Optional[str]]:
    """Occurrences of any needle (lowercase) in a file, block by block; plus one masked snippet.

    The third value is why the file was not read completely ('size' or 'budget'), else None. A
    file over ``max_file_bytes`` is read from its end (the newest part of a log)."""
    longest = max((len(n) for n in needles), default=0)
    count, snippet, cut = 0, None, None
    try:
        with open(path, "rb") as fh:
            try:
                size = os.fstat(fh.fileno()).st_size
            except OSError:
                size = 0
            if size > max_file_bytes:
                fh.seek(size - max_file_bytes)
                cut = "size"
            tail = ""
            read = 0
            while read < max_file_bytes:
                if not budget.ok():
                    cut = cut or "budget"
                    break
                raw = fh.read(min(BLOCK, max_file_bytes - read))
                if not raw:
                    break
                read += len(raw)
                budget.left -= len(raw)
                text = tail + raw.decode("utf-8", "replace")
                low = text.lower()
                spans = []
                for nd in needles:
                    start = 0
                    while True:
                        pos = low.find(nd, start)
                        if pos < 0:
                            break
                        # Skip hits fully inside the carried-over tail (counted in the last block).
                        if pos + len(nd) > len(tail):
                            spans.append((pos, pos + len(nd)))
                        start = pos + 1
                # Overlapping hits of different needles (name inside an e-mail) count once.
                spans.sort()
                last_end = -1
                for a, b in spans:
                    if a >= last_end:
                        count += 1
                        if snippet is None and snippet_term:
                            snippet = detect.masked_snippet(text, a, b)
                    last_end = max(last_end, b)
                tail = text[-(longest - 1):] if longest > 1 else ""
            else:
                if cut is None and fh.read(1):  # the file grew while it was read
                    cut = "size"
    except OSError:
        return 0, None, None
    return count, snippet, cut


def search_files(home: Path, terms: list[str], own_dir: Path, seconds: float = 20.0,
                 max_bytes: int = 768 << 20, max_file_bytes: int = 64 << 20,
                 snippet_term: str = "") -> list[dict]:
    needles = sorted({t.lower() for t in terms if t}, key=len, reverse=True)
    budget = Budget(seconds, max_bytes)
    results = []
    for key, rel, label in FILE_STORES:
        root = home / rel
        entry: dict[str, Any] = {"store": key, "path": str(root), "label": label, "exists": root.is_dir(),
                                 "files": [], "count": 0, "partial": False, "partial_files": []}
        if root.is_dir() and needles:
            for p in _iter_files(root, exclude=[own_dir]):
                if not budget.ok():
                    entry["partial"] = True
                    entry["unsearched"] = True
                    break
                n, snip, cut = search_file(p, needles, budget, max_file_bytes, snippet_term)
                if cut:
                    entry["partial"] = True
                    entry["partial_files"].append({"path": str(p.relative_to(home)), "reason": cut})
                if n:
                    rec = {"path": str(p.relative_to(home)), "count": n,
                           "request_dump": p.name.startswith("request_dump_")}
                    if snip:
                        rec["snippet"] = snip
                    entry["files"].append(rec)
                    entry["count"] += n
        results.append(entry)
    return results


def search_all(home: Path, terms: list[str], own_dir: Path, seconds: float = 30.0,
               snippet_term: str = "", snippets: int = 0, deep: bool = False) -> dict:
    t0 = time.monotonic()
    db = search_state_db(home, terms, seconds=max(2.0, seconds / 2), snippets=snippets,
                         snippet_term=snippet_term, deep=deep)
    files = search_files(home, terms, own_dir, seconds=max(5.0, seconds - (time.monotonic() - t0)),
                         snippet_term=snippet_term)
    places = []
    for name, info in db.get("places", {}).items():
        places.append({"store": "state.db", "place": name, "count": info.get("count", 0), "detail": info})
    for entry in files:
        for f in entry["files"]:
            places.append({"store": entry["store"], "place": f["path"], "count": f["count"],
                           "request_dump": f.get("request_dump", False), "snippet": f.get("snippet")})
    partial_files = [pf for e in files for pf in e.get("partial_files") or []]
    reasons = []
    if db.get("partial"):
        reasons.append("state_db_deadline")
    if any(e.get("unsearched") for e in files):
        reasons.append("file_budget")
    if partial_files:
        reasons.append("partial_files")
    return {"state_db": db, "files": files, "places": places,
            "partial": bool(reasons), "partial_reasons": reasons, "partial_files": partial_files,
            "coverage": list(db.get("coverage") or []), "deep": bool(deep),
            "seconds": round(time.monotonic() - t0, 2)}
