"""Read state.db (and projects.db) read-only and aggregate everything the cards need.

Performance: state.db can be gigabytes, mostly cron sessions. Sessions are filtered
first, then messages are read per session through the messages index. Assistant text is
never read; tool results only for skill_view (first 200 characters, for the skill name).
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import sqlite3
import time
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from . import manners as _m
from . import words as _w

DEFAULT_EXCLUDED_SOURCES = ("cron", "subagent", "kanban", "batch", "webhook", "tool")
TERMINAL_SOURCES = {"cli", "tui", "local", "oneshot", "acp"}
# Tools that change something: running commands, writing files, editing skills, spawning work.
BUILD_TOOLS = {"terminal", "patch", "write_file", "execute_code", "skill_manage", "delegate_task",
               "process", "process_manage", "cronjob", "cronjob_manage", "browser_exec", "computer_use"}
NIGHT_HOURS = {22, 23, 0, 1, 2, 3, 4, 5}

_SKILL_NAME = re.compile(r'"name"\s{0,3}:\s{0,3}"([^"\\]{1,80})"')


def ro_connect(path: Path) -> sqlite3.Connection:
    uri = "file:" + urllib.request.pathname2url(str(Path(path).resolve())) + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=5)


def model_family(model: Optional[str]) -> str:
    """Readable model family: claude-opus-5-5 -> Claude Opus, deepseek/deepseek-v4-pro -> DeepSeek."""
    m = (model or "").strip().lower()
    if not m:
        return ""
    last = m.split("/")[-1]
    if m in ("openrouter/auto", "auto"):
        return "OpenRouter Auto"
    for key in ("opus", "sonnet", "haiku", "fable"):
        if key in last:
            return "Claude " + key.capitalize()
    table = [("deepseek", "DeepSeek"), ("gpt", "GPT"), ("o1", "OpenAI o1"), ("o3", "OpenAI o3"),
             ("o4", "OpenAI o4"), ("gemini", "Gemini"), ("gemma", "Gemma"), ("grok", "Grok"),
             ("qwen", "Qwen"), ("glm", "GLM"), ("kimi", "Kimi"), ("llama", "Llama"),
             ("mistral", "Mistral"), ("codestral", "Mistral"), ("hermes", "Hermes"), ("minimax", "MiniMax"),
             ("claude", "Claude")]
    for key, name in table:
        if last.startswith(key) or ("/" not in m and key in last):
            return name
    return last[:28]


@dataclass
class Window:
    start: float
    end: float
    label: str  # "2026", "last 30 days", "all time"
    year: Optional[int] = None
    days: Optional[int] = None


def year_window(year: int, tz) -> Window:
    s = _dt.datetime(year, 1, 1, tzinfo=tz).timestamp()
    e = _dt.datetime(year + 1, 1, 1, tzinfo=tz).timestamp()
    return Window(s, e, str(year), year=year)


def days_window(days: int) -> Window:
    now = time.time()
    return Window(now - days * 86400, now + 60, f"{days}d", days=days)


def all_window() -> Window:
    return Window(0.0, time.time() + 60, "all")


@dataclass
class Stats:
    window: Window
    tz_name: str = ""
    # volume
    sessions: int = 0
    user_messages: int = 0
    active_days: int = 0
    first_ts: Optional[float] = None
    last_ts: Optional[float] = None
    busiest_day: Optional[str] = None  # ISO date
    busiest_day_msgs: int = 0
    # time of day
    hours: Counter = field(default_factory=Counter)
    night_messages: int = 0          # 22:00 to 05:59
    deep_night_messages: int = 0     # 02:00 to 04:59
    latest_clock: Optional[str] = None   # "04:58", the message closest to dawn
    latest_date: Optional[str] = None
    # tools and skills
    tools: Counter = field(default_factory=Counter)
    skills: Counter = field(default_factory=Counter)
    build_sessions: int = 0
    # surfaces and models
    sources: Counter = field(default_factory=Counter)      # user messages per source
    terminal_messages: int = 0
    models: Counter = field(default_factory=Counter)       # sessions per model family
    # marathon
    longest_messages: int = 0
    longest_title: str = ""
    longest_date: Optional[str] = None
    avg_messages: float = 0.0          # average messages per chat (sessions.message_count)
    # tokens (all sessions incl. cron: what your agent processed)
    tokens_in_out: int = 0
    tokens_cache_read: int = 0
    # night crew
    cron_runs: int = 0
    subagent_runs: int = 0
    # manners
    polite: Counter = field(default_factory=Counter)
    swear: Counter = field(default_factory=Counter)
    polite_tokens: int = 0
    de_votes: int = 0
    en_votes: int = 0
    # words
    words: list = field(default_factory=list)  # [(word, messages)]
    # projects
    projects_source: str = ""   # "projects", "folders" or ""
    projects_started: int = 0
    projects_closed: int = 0    # archived projects (projects.db) or folders quiet for 30 days
    # persona
    persona: Optional[dict] = None

    @property
    def polite_total(self) -> int:
        return sum(self.polite.values())

    @property
    def swear_total(self) -> int:
        return sum(self.swear.values())

    def guess_language(self) -> str:
        return "de" if self.de_votes > self.en_votes else "en"

    def to_dict(self) -> dict:
        d = {
            "window": {"label": self.window.label, "start": self.window.start, "end": self.window.end},
            "timezone": self.tz_name,
            "sessions": self.sessions, "user_messages": self.user_messages, "active_days": self.active_days,
            "busiest_day": self.busiest_day, "busiest_day_messages": self.busiest_day_msgs,
            "night_messages": self.night_messages, "deep_night_messages": self.deep_night_messages,
            "latest_clock": self.latest_clock, "latest_date": self.latest_date,
            "top_tools": self.tools.most_common(10), "top_skills": self.skills.most_common(10),
            "distinct_skills": len(self.skills), "build_sessions": self.build_sessions,
            "sources": dict(self.sources.most_common()), "models": dict(self.models.most_common()),
            "longest_session_messages": self.longest_messages, "average_session_messages": round(self.avg_messages, 1), "longest_session_date": self.longest_date,
            "tokens_in_out": self.tokens_in_out, "tokens_cache_read": self.tokens_cache_read,
            "cron_runs": self.cron_runs, "subagent_runs": self.subagent_runs,
            "polite_total": self.polite_total, "polite": dict(self.polite.most_common()),
            "swear_total": self.swear_total, "swear": dict(self.swear.most_common()),
            "polite_tokens": self.polite_tokens,
            "word_of_the_year": self.words[:9],
            "projects": {"source": self.projects_source, "started": self.projects_started,
                         "closed": self.projects_closed},
            "persona": self.persona,
        }
        return d


def _cols(con: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


def _sel(cols: set[str], name: str, default: str = "NULL") -> str:
    return name if name in cols else default


def collect(home: Path, window: Window, *, tz=None, tz_name: str = "", excluded=DEFAULT_EXCLUDED_SOURCES,
            exclude_words: Iterable[str] = (), with_titles: bool = False, rename_words: Optional[dict] = None) -> Stats:
    st = Stats(window=window, tz_name=tz_name)
    db = Path(home) / "state.db"
    if not db.is_file():
        st.persona = persona(st)
        return st
    excluded = tuple(excluded)
    con = ro_connect(db)
    try:
        scols = _cols(con, "sessions")
        mcols = _cols(con, "messages")
        sql = ("SELECT id, COALESCE(source,''), " + _sel(scols, "model") + ", started_at, "
               + _sel(scols, "message_count", "0") + ", " + _sel(scols, "input_tokens", "0") + ", "
               + _sel(scols, "output_tokens", "0") + ", " + _sel(scols, "cache_read_tokens", "0") + ", "
               + (_sel(scols, "title") if with_titles else "NULL") + ", "
               + _sel(scols, "git_repo_root") + ", " + _sel(scols, "cwd")
               + " FROM sessions WHERE started_at >= ? AND started_at < ?")
        interactive: dict[str, dict] = {}
        for sid, src, model, started, mcount, tin, tout, tcache, title, repo, cwd in con.execute(
                sql, (window.start, window.end)):
            st.tokens_in_out += int(tin or 0) + int(tout or 0)
            st.tokens_cache_read += int(tcache or 0)
            if src == "cron":
                st.cron_runs += 1
            elif src == "subagent":
                st.subagent_runs += 1
            if src in excluded:
                continue
            interactive[sid] = {"source": src, "model": model, "started": started, "count": int(mcount or 0),
                                "title": title or "", "folder": repo or cwd or ""}
        _read_messages(con, st, interactive, window, excluded, mcols, tz, exclude_words, rename_words)
    finally:
        con.close()
    _projects(home, st, window, interactive)
    st.persona = persona(st)
    return st


def _local(ts: float, tz) -> _dt.datetime:
    return _dt.datetime.fromtimestamp(ts, tz) if tz is not None else _dt.datetime.fromtimestamp(ts)


def _read_messages(con, st: Stats, interactive: dict, window: Window, excluded, mcols, tz, exclude_words,
                   rename_words: Optional[dict] = None) -> None:
    if not interactive:
        return
    has_tool_name = "tool_name" in mcols
    sess = "SELECT id FROM sessions WHERE started_at >= ? AND started_at < ?"
    params: list = [window.start, window.end]
    if excluded:
        sess += " AND COALESCE(source,'') NOT IN (%s)" % ",".join("?" * len(excluded))
        params.extend(excluded)
    tool_sel = "m.tool_name" if has_tool_name else "NULL"
    skill_case = ("WHEN m.role = 'tool' AND m.tool_name = 'skill_view' THEN substr(m.content, 1, 200) "
                  if has_tool_name else "")
    roles = "('user','tool')" if has_tool_name else "('user')"
    sql = ("SELECT m.session_id, m.role, CASE WHEN m.role = 'user' THEN m.content " + skill_case
           + "ELSE NULL END, " + tool_sel + ", m.timestamp FROM messages m WHERE m.role IN " + roles
           + " AND m.session_id IN (" + sess + ") ORDER BY m.session_id, m.timestamp, m.id")

    skip_words = list(_m.polite_labels()) + ["vielen", "dank", "dankeschön", "thank", "danke"]
    wc = _w.WordCounter(exclude=exclude_words, skip=skip_words, skip_fn=_m.swear_hits, rename=rename_words)
    per_day: Counter = Counter()
    sessions_with_user: set[str] = set()
    build: set[str] = set()
    best_clock = -1  # minutes after 05:00, the message closest to dawn wins
    for sid, role, content, tool_name, ts in con.execute(sql, params):
        if role == "tool":
            if tool_name:
                st.tools[tool_name] += 1
                if tool_name in BUILD_TOOLS:
                    build.add(sid)
                if tool_name == "skill_view" and content:
                    m = _SKILL_NAME.search(content)
                    if m and '"success": true' in content[:40].replace("'", '"'):
                        st.skills[m.group(1)] += 1
            continue
        text = _m.clean_user_text(content if isinstance(content, str) else "")
        if not text.strip():
            continue
        info = interactive.get(sid)
        if info is None:
            continue
        st.user_messages += 1
        sessions_with_user.add(sid)
        st.sources[info["source"]] += 1
        if info["source"] in TERMINAL_SOURCES:
            st.terminal_messages += 1
        if ts:
            st.first_ts = ts if st.first_ts is None else min(st.first_ts, ts)
            st.last_ts = ts if st.last_ts is None else max(st.last_ts, ts)
            lt = _local(ts, tz)
            per_day[lt.date().isoformat()] += 1
            st.hours[lt.hour] += 1
            if lt.hour in NIGHT_HOURS:
                st.night_messages += 1
            if 2 <= lt.hour < 5:
                st.deep_night_messages += 1
            clock = ((lt.hour - 5) % 24) * 60 + lt.minute
            if clock > best_clock:
                best_clock = clock
                st.latest_clock = f"{lt.hour:02d}:{lt.minute:02d}"
                st.latest_date = lt.date().isoformat()
        toks = 0
        for rid, label, n in _m.polite_hits(text):
            st.polite[label] += n
            toks += _m.estimate_tokens(label) * n
            st.de_votes += n if rid.startswith("de.") else 0
            st.en_votes += n if rid.startswith("en.") else 0
        st.polite_tokens += toks
        for rid, label, n in _m.swear_hits(text):
            st.swear[label] += n
            st.de_votes += n if rid.startswith("de.") else 0
            st.en_votes += n if rid.startswith("en.") else 0
        wc.add(text)

    st.sessions = len(sessions_with_user)
    st.build_sessions = len(build & sessions_with_user)
    st.active_days = len(per_day)
    if per_day:
        day, n = max(per_day.items(), key=lambda kv: (kv[1], kv[0]))
        st.busiest_day, st.busiest_day_msgs = day, n
    st.words = wc.top(9)
    counts = [interactive[sid]["count"] for sid in sessions_with_user]
    st.avg_messages = (sum(counts) / len(counts)) if counts else 0.0
    for sid in sessions_with_user:
        info = interactive[sid]
        fam = model_family(info["model"])
        if fam:
            st.models[fam] += 1
        if info["count"] > st.longest_messages:
            st.longest_messages = info["count"]
            st.longest_title = info["title"]
            st.longest_date = _local(info["started"], tz).date().isoformat() if info["started"] else None


def _projects(home: Path, st: Stats, window: Window, interactive: dict) -> None:
    """Projects started vs. closed. Desktop projects (projects.db) when they exist, else working folders."""
    pdb = Path(home) / "projects.db"
    if pdb.is_file():
        try:
            con = ro_connect(pdb)
            try:
                cols = _cols(con, "projects")
                if {"created_at", "archived"} <= cols:
                    rows = con.execute("SELECT created_at, archived FROM projects").fetchall()
                    started = [a for c, a in rows if c is not None and window.start <= _norm_ts(c) < window.end]
                    if started:
                        st.projects_source = "projects"
                        st.projects_started = len(started)
                        st.projects_closed = sum(1 for a in started if a)
                        return
            finally:
                con.close()
        except sqlite3.Error:
            pass
    last_seen: dict[str, float] = {}
    for info in interactive.values():
        f = (info.get("folder") or "").rstrip("/")
        if not f or f in ("/", str(Path.home())) or f.endswith("/.hermes"):
            continue
        last_seen[f] = max(last_seen.get(f, 0.0), float(info.get("started") or 0.0))
    if len(last_seen) >= 2:
        cutoff = min(time.time(), window.end) - 30 * 86400
        st.projects_source = "folders"
        st.projects_started = len(last_seen)
        st.projects_closed = sum(1 for t in last_seen.values() if t < cutoff)


def _norm_ts(v) -> float:
    v = float(v)
    return v / 1000.0 if v > 1e11 else v  # milliseconds tolerated


# --------------------------------------------------------------------------------------
# Persona: four axes, 16 types. Every axis value is a real share from the history.
# --------------------------------------------------------------------------------------

NIGHT_THRESHOLD = 0.20      # share of messages typed between 22:00 and 05:59
BUILD_THRESHOLD = 0.50      # share of chats in which the agent ran commands or wrote files
TERMINAL_THRESHOLD = 0.50   # share of messages typed in a terminal (cli, tui)
LOYAL_THRESHOLD = 0.75      # share of chats with the main model family


def persona(st: Stats) -> Optional[dict]:
    if st.user_messages == 0:
        return None
    night = st.night_messages / st.user_messages
    build = st.build_sessions / max(1, st.sessions)
    term = st.terminal_messages / st.user_messages
    total_models = sum(st.models.values())
    top_model, top_n = (st.models.most_common(1)[0] if st.models else ("", 0))
    loyal = (top_n / total_models) if total_models else 1.0
    code = ("N" if night >= NIGHT_THRESHOLD else "D") + ("B" if build >= BUILD_THRESHOLD else "A") \
        + ("T" if term >= TERMINAL_THRESHOLD else "C") + ("L" if loyal >= LOYAL_THRESHOLD else "M")
    return {"code": code, "night": round(night, 4), "build": round(build, 4), "terminal": round(term, 4),
            "loyal": round(loyal, 4), "top_model": top_model}


def dumps(st: Stats) -> str:
    return json.dumps(st.to_dict(), ensure_ascii=False, indent=2, default=str)
