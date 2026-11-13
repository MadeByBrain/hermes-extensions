"""Offline tests for year-wrapped. No network, no model, no browser.

Run:  python -m unittest discover -s tests -v      (from the plugin folder; Python 3.10+)
"""
from __future__ import annotations

import atexit
import datetime as dt
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
HOME = Path(tempfile.mkdtemp(prefix="year-wrapped-test-"))
atexit.register(shutil.rmtree, HOME, True)
os.environ["HERMES_HOME"] = str(HOME)

_spec = importlib.util.spec_from_file_location("year_wrapped_plugin", ROOT / "__init__.py",
                                               submodule_search_locations=[str(ROOT)])
hw = importlib.util.module_from_spec(_spec)
sys.modules["year_wrapped_plugin"] = hw
_spec.loader.exec_module(hw)
from year_wrapped_plugin import cards, manners, render, stats, words  # noqa: E402

UTC = dt.timezone.utc
FENCE = "\x60" * 3
DASHES = re.compile("[\u2013\u2014]")


class FakeCtx:
    def __init__(self, settings=None):
        self.settings = dict(settings or {})
        self.commands, self.cli = {}, {}

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_command(self, name, handler, description="", args_hint="", **kw):
        self.commands[name] = handler

    def register_cli_command(self, name, help, setup_fn, handler_fn=None, description=""):
        self.cli[name] = (setup_fn, handler_fn)


def ts(y, mo, d, h=12, mi=0):
    return dt.datetime(y, mo, d, h, mi, tzinfo=UTC).timestamp()


def make_db(sessions, messages, projects=None):
    """sessions: (id, source, model, started_at, message_count, tin, tout, tcache, title, cwd)
    messages: (session_id, role, content, tool_name, timestamp)"""
    for name in ("state.db", "projects.db"):
        f = HOME / name
        if f.exists():
            f.unlink()
    con = sqlite3.connect(HOME / "state.db")
    con.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT NOT NULL, model TEXT, started_at REAL NOT NULL, "
                "message_count INTEGER DEFAULT 0, input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0, "
                "cache_read_tokens INTEGER DEFAULT 0, estimated_cost_usd REAL, actual_cost_usd REAL, title TEXT, "
                "cwd TEXT, git_repo_root TEXT)")
    con.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, role TEXT NOT NULL, "
                "content TEXT, tool_call_id TEXT, tool_calls TEXT, tool_name TEXT, timestamp REAL NOT NULL)")
    con.execute("CREATE INDEX idx_messages_session ON messages(session_id, timestamp)")
    con.execute("CREATE INDEX idx_sessions_started ON sessions(started_at DESC)")
    for sid, src, model, started, mc, tin, tout, tc, title, cwd in sessions:
        con.execute("INSERT INTO sessions (id, source, model, started_at, message_count, input_tokens, output_tokens, "
                    "cache_read_tokens, estimated_cost_usd, actual_cost_usd, title, cwd) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (sid, src, model, started, mc, tin, tout, tc, -999.0, -999.0, title, cwd))
    for sid, role, content, tool, t in messages:
        con.execute("INSERT INTO messages (session_id, role, content, tool_name, timestamp) VALUES (?,?,?,?,?)",
                    (sid, role, content, tool, t))
    con.commit()
    con.close()
    if projects is not None:
        pc = sqlite3.connect(HOME / "projects.db")
        pc.execute("CREATE TABLE projects (id TEXT PRIMARY KEY, slug TEXT, name TEXT, created_at INTEGER NOT NULL, "
                   "archived INTEGER NOT NULL DEFAULT 0)")
        for i, (created, archived) in enumerate(projects):
            pc.execute("INSERT INTO projects VALUES (?,?,?,?,?)", (f"p{i}", f"s{i}", f"Project {i}", created, archived))
        pc.commit()
        pc.close()


def skill_result(name):
    return json.dumps({"success": True, "name": name, "description": "x" * 400})


SESSIONS = [
    ("a", "cli", "anthropic/claude-opus-4.6", ts(2026, 3, 2, 9), 40, 1000, 500, 9000, "Secret client plan", "/work/alpha"),
    ("b", "telegram", "claude-opus-5-5", ts(2026, 3, 3, 23), 6, 800, 200, 0, "Other title", "/work/beta"),
    ("c", "tui", "deepseek/deepseek-v4-pro", ts(2026, 4, 1, 14), 4, 300, 100, 0, None, "/work/alpha"),
    ("cron1", "cron", "deepseek-v4-flash", ts(2026, 4, 2, 3), 3, 5000, 100, 0, None, None),
    ("cron2", "cron", "deepseek-v4-flash", ts(2026, 4, 3, 3), 3, 5000, 100, 0, None, None),
    ("sub1", "subagent", "claude-opus-5-5", ts(2026, 4, 3, 10), 3, 100, 10, 0, None, None),
    ("old", "cli", "gpt-5", ts(2025, 12, 31, 12), 3, 77, 7, 0, None, None),
]
MESSAGES = [
    ("a", "user", "Bitte baue das Dashboard. Danke!", None, ts(2026, 3, 2, 9, 0)),
    ("a", "assistant", "ok", None, ts(2026, 3, 2, 9, 1)),
    ("a", "tool", "done", "terminal", ts(2026, 3, 2, 9, 2)),
    ("a", "tool", "done", "terminal", ts(2026, 3, 2, 9, 3)),
    ("a", "tool", "{}", "write_file", ts(2026, 3, 2, 9, 4)),
    ("a", "tool", skill_result("dashboard-builder"), "skill_view", ts(2026, 3, 2, 9, 5)),
    ("a", "tool", skill_result("dashboard-builder"), "skill_view", ts(2026, 3, 2, 9, 6)),
    ("a", "tool", skill_result("mail-flow"), "skill_view", ts(2026, 3, 2, 9, 7)),
    ("a", "tool", '{"success": false, "error": "not found"}', "skill_view", ts(2026, 3, 2, 9, 8)),
    ("a", "user", "Dashboard again please, the dashboard " + FENCE + "\nfuck code fuck\n" + FENCE, None, ts(2026, 3, 2, 10)),
    ("a", "user", "[IMPORTANT: Background process finished. dashboard dashboard dashboard]", None, ts(2026, 3, 2, 11)),
    ("a", "user", "[CONTEXT COMPACTION] summary with bitte bitte bitte", None, ts(2026, 3, 2, 11, 5)),
    ("b", "user", "[Replying to: \"bitte bitte\"]\n\nSo ein Mist, the dashboard is broken", None, ts(2026, 3, 4, 3, 40)),
    ("b", "tool", "{}", "web_search", ts(2026, 3, 4, 3, 41)),
    ("c", "user", "what is the weather? dashboard\n[Attached files: /tmp/dashboard_screenshot.png]", None, ts(2026, 4, 1, 14, 5)),
    ("cron1", "user", "run the nightly job please please please dashboard", None, ts(2026, 4, 2, 3)),
    ("old", "user", "last year bitte", None, ts(2025, 12, 31, 12)),
]


class Base(unittest.TestCase):
    def setUp(self):
        hw._ctx = None
        make_db(SESSIONS, MESSAGES, projects=[(int(ts(2026, 2, 1)), 0), (int(ts(2026, 5, 1)), 1),
                                               (int(ts(2026, 6, 1)), 0), (int(ts(2025, 5, 1)), 1)])

    def collect(self, **kw):
        return stats.collect(HOME, stats.year_window(2026, UTC), tz=UTC, tz_name="UTC", **kw)


class TestCollect(Base):
    def test_counts_only_typed_text_of_people(self):
        st = self.collect()
        self.assertEqual(st.sessions, 3)              # a, b, c; cron and subagent excluded
        self.assertEqual(st.user_messages, 4)         # injected notice and compaction skipped
        self.assertEqual(st.polite["bitte"], 1)       # quoted reply and compaction text do not count
        self.assertEqual(st.polite["please"], 1)
        self.assertEqual(st.polite["danke"], 1)
        self.assertEqual(st.swear_total, 1)           # "fuck" inside a code block is ignored, "Mist" counts
        self.assertEqual(st.swear["mist"], 1)

    def test_year_window_excludes_last_year(self):
        st = self.collect()
        self.assertNotIn("Gpt", "".join(st.models))
        self.assertNotIn("GPT", st.models)

    def test_tools_skills_and_build_share(self):
        st = self.collect()
        self.assertEqual(st.tools["terminal"], 2)
        self.assertEqual(st.skills.most_common(1)[0], ("dashboard-builder", 2))
        self.assertEqual(sum(st.skills.values()), 3)  # the failed skill_view is not counted
        self.assertEqual(st.build_sessions, 1)        # only session a ran commands or wrote files

    def test_time_of_day_and_latest_clock(self):
        st = self.collect()
        self.assertEqual(st.latest_clock, "03:40")    # closest to dawn wins over 14:05 and 10:00
        self.assertEqual(st.latest_date, "2026-03-04")
        self.assertEqual(st.deep_night_messages, 1)
        self.assertEqual(st.night_messages, 1)

    def test_timezone_shifts_hours(self):
        from zoneinfo import ZoneInfo
        st = stats.collect(HOME, stats.year_window(2026, UTC), tz=ZoneInfo("Asia/Tokyo"), tz_name="Asia/Tokyo")
        self.assertEqual(st.latest_clock, "23:05")    # 14:05 UTC = 23:05 in Tokyo, the latest before dawn

    def test_cron_tokens_and_marathon(self):
        st = self.collect()
        self.assertEqual(st.cron_runs, 2)
        self.assertEqual(st.subagent_runs, 1)
        self.assertEqual(st.tokens_in_out, 1500 + 1000 + 400 + 5100 * 2 + 110)
        self.assertEqual(st.tokens_cache_read, 9000)
        self.assertEqual(st.longest_messages, 40)
        self.assertEqual(st.longest_title, "")        # titles are not even read unless asked for
        self.assertAlmostEqual(st.avg_messages, (40 + 6 + 4) / 3)

    def test_titles_only_on_request(self):
        st = self.collect(with_titles=True)
        self.assertEqual(st.longest_title, "Secret client plan")

    def test_models_grouped_by_family(self):
        st = self.collect()
        self.assertEqual(st.models["Claude Opus"], 2)
        self.assertEqual(st.models["DeepSeek"], 1)

    def test_projects_from_projects_db(self):
        st = self.collect()
        self.assertEqual((st.projects_source, st.projects_started, st.projects_closed), ("projects", 3, 1))

    def test_projects_fall_back_to_folders(self):
        (HOME / "projects.db").unlink()
        st = self.collect()
        self.assertEqual(st.projects_source, "folders")
        self.assertEqual(st.projects_started, 2)      # /work/alpha and /work/beta

    def test_word_of_the_year(self):
        st = self.collect()
        self.assertEqual(st.words[0][0], "dashboard")
        self.assertEqual(st.words[0][1], 4)           # once per message; injected text and file paths ignored
        st2 = self.collect(exclude_words=["dashboard"])
        self.assertNotEqual(st2.words[0][0], "dashboard")

    def test_persona_axes_are_real_shares(self):
        st = self.collect()
        p = st.persona
        self.assertAlmostEqual(p["night"], 1 / 4)
        self.assertAlmostEqual(p["build"], 1 / 3, places=3)
        self.assertAlmostEqual(p["terminal"], 3 / 4)
        self.assertAlmostEqual(p["loyal"], 2 / 3, places=3)
        self.assertEqual(p["code"], "NATM")

    def test_no_cost_columns_used(self):
        src = (ROOT / "stats.py").read_text() + (ROOT / "cards.py").read_text() + (ROOT / "__init__.py").read_text()
        self.assertNotIn("cost_usd", src)
        self.assertNotIn("-999", json.dumps(self.collect().to_dict()))

    def test_database_is_opened_read_only(self):
        before = (HOME / "state.db").read_bytes()
        con = stats.ro_connect(HOME / "state.db")
        with self.assertRaises(sqlite3.OperationalError):
            con.execute("DELETE FROM messages")
        con.close()
        self.collect()
        self.assertEqual(before, (HOME / "state.db").read_bytes())

    def test_messages_read_through_session_index(self):
        con = stats.ro_connect(HOME / "state.db")
        plan = " ".join(str(r) for r in con.execute(
            "EXPLAIN QUERY PLAN SELECT m.session_id FROM messages m WHERE m.role IN ('user','tool') AND m.session_id IN "
            "(SELECT id FROM sessions WHERE started_at >= 0 AND started_at < 9e9 AND COALESCE(source,'') NOT IN ('cron'))"))
        con.close()
        self.assertIn("idx_messages_session", plan)

    def test_missing_database(self):
        os.remove(HOME / "state.db")
        st = self.collect()
        self.assertEqual(st.user_messages, 0)
        self.assertIsNone(st.persona)

    def test_old_schema_without_optional_columns(self):
        os.remove(HOME / "state.db")
        con = sqlite3.connect(HOME / "state.db")
        con.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT, started_at REAL)")
        con.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, timestamp REAL)")
        con.execute("INSERT INTO sessions VALUES ('x','cli',?)", (ts(2026, 1, 5),))
        con.execute("INSERT INTO messages VALUES (1,'x','user','hello please',?)", (ts(2026, 1, 5),))
        con.commit()
        con.close()
        st = self.collect()
        self.assertEqual(st.user_messages, 1)
        self.assertEqual(st.polite["please"], 1)


class TestHelpers(unittest.TestCase):
    def test_clean_user_text(self):
        self.assertEqual(manners.clean_user_text("[System: note]"), "")
        self.assertEqual(manners.clean_user_text("[ASYNC DELEGATION BATCH] result"), "")
        out = manners.clean_user_text("[Workspace::v1: /x]\nhello\n> quoted\n[Attached files: /a.png]")
        self.assertEqual(out.strip(), "hello")
        self.assertIn("real text", manners.clean_user_text('[Replying to: "line one\nline two"]\n\nreal text'))
        self.assertNotIn("line two", manners.clean_user_text('[Replying to: "line one\nline two"]\n\nreal text'))

    def test_clean_user_text_is_fast_on_huge_input(self):
        t = time.time()
        for s in ("[" * 200000, " \n" * 100000, '[Replying to: "' + "a" * 100000, FENCE * 30000, "/" * 200000):
            manners.clean_user_text(s)
            words.words_in(s)
        self.assertLess(time.time() - t, 2.0)

    def test_word_ties_are_deterministic(self):
        wc = words.WordCounter()
        for text in ("zebra apple", "apple zebra mango"):
            wc.add(text)
        self.assertEqual(wc.top(3), [("apple", 2), ("zebra", 2), ("mango", 1)])

    def test_rename_words(self):
        self.assertEqual(words.parse_renames(["Acme=Northstar", "bad", "x=", " globex = Client B "]),
                         {"acme": "Northstar", "globex": "Client B"})
        wc = words.WordCounter(rename={"acme": "Northstar"})
        for text in ("acme has time", "Acme and Northstar", "northstar again"):
            wc.add(text)
        self.assertEqual(dict(wc.top(5))["Northstar"], 3)
        self.assertNotIn("acme", dict(wc.top(5)))

    def test_singular_units(self):
        self.assertEqual(cards.unit("en", "day", 1), "active day")
        self.assertEqual(cards.unit("de", "day", 2), "aktive Tage")

    def test_words_skip_links_and_short_words(self):
        w = words.words_in("see https://example.com/dashboard and /tmp/server.log, user@mail.com, a cat and dashboard")
        self.assertEqual(w, {"dashboard"})

    def test_model_family(self):
        f = stats.model_family
        self.assertEqual(f("claude-opus-5-5"), "Claude Opus")
        self.assertEqual(f("anthropic/claude-sonnet-4.6"), "Claude Sonnet")
        self.assertEqual(f("deepseek/deepseek-v4-pro"), "DeepSeek")
        self.assertEqual(f("openrouter/auto"), "OpenRouter Auto")
        self.assertEqual(f("qwen/qwen3.8-max"), "Qwen")
        self.assertEqual(f("gpt-5.1"), "GPT")
        self.assertEqual(f(""), "")

    def test_sixteen_personas_complete(self):
        codes = {a + b + c + d for a in "ND" for b in "BA" for c in "TC" for d in "LM"}
        self.assertEqual(set(cards.PERSONAS), codes)
        names = [p[1] for p in cards.PERSONAS.values()] + [p[2] for p in cards.PERSONAS.values()]
        self.assertEqual(len(set(names)), 32)
        for p in cards.PERSONAS.values():
            self.assertNotRegex(" ".join(p), r"\d{1,3}\s?%")  # no invented percentages in type texts
            self.assertNotRegex(" ".join(p), DASHES)

    def test_formatting(self):
        self.assertEqual(cards.fmt_int(1234567, "de"), "1.234.567")
        self.assertEqual(cards.fmt_big(1_432_000_000, "en"), "1.4 B")
        self.assertEqual(cards.fmt_big(1_432_000_000, "de"), "1,4 Mrd.")
        self.assertEqual(cards.fmt_date("2026-07-21", "de"), "21. Juli")
        self.assertEqual(cards.fmt_date("2026-07-21", "en"), "21 July")
        self.assertIn("&nbsp;", cards.e("Plus 237 subagents you sent off to work."))
        self.assertNotIn("&nbsp;", cards.e("Der gesprächige Bauleiter"))

    def test_browser_search_prefers_non_snap(self):
        with mock.patch.object(render.shutil, "which", side_effect=lambda n: {"chromium": "/snap/bin/chromium",
                                                                            "google-chrome": "/usr/bin/google-chrome"}.get(n)), \
                mock.patch.object(render.glob, "glob", return_value=[]), \
                mock.patch.object(render.os.path, "isfile", return_value=False), \
                mock.patch.object(render.os.path, "realpath", side_effect=lambda p: p):
            self.assertEqual(render.find_browsers(), ["/usr/bin/google-chrome", "/snap/bin/chromium"])


class TestCards(Base):
    def render(self, lang="en", **kw):
        st = self.collect(**kw)
        return st, cards.render_all(st, lang=lang, show_titles=kw.get("with_titles", False))

    def test_all_cards_render_in_both_languages(self):
        for lang in ("en", "de"):
            st, out = self.render(lang)
            slugs = [s for s, _ in out]
            self.assertEqual(slugs, ["cover", "persona", "tools", "skill", "manners", "night", "marathon", "tokens",
                                     "crew", "model", "projects", "word", "summary"])
            for slug, doc in out:
                self.assertNotRegex(doc, DASHES, f"{lang}/{slug} contains a dash")
                self.assertNotRegex(doc, r"(?i)<script|https?://|@import|url\(", f"{lang}/{slug} loads something")
                self.assertIn("width:1080px;height:1920px", doc)

    def test_title_hidden_by_default(self):
        _st, out = self.render("en")
        self.assertNotIn("Secret client plan", "".join(d for _s, d in out))
        _st, out = self.render("en", with_titles=True)
        self.assertIn("Secret client plan", dict(out)["marathon"])

    def test_cards_escape_user_text(self):
        make_db([("x", "cli", "<b>m</b>", ts(2026, 5, 1), 3, 1, 1, 0, "<script>t</script>", None)],
                [("x", "user", "<script>alert(1)</script> scriptword scriptword", None, ts(2026, 5, 1))])
        st = self.collect(with_titles=True)
        out = cards.render_all(st, lang="en", show_titles=True)
        self.assertNotIn("<script>", "".join(d for _s, d in out))

    def test_empty_history_renders_cover_and_summary_only(self):
        os.remove(HOME / "state.db")
        os.remove(HOME / "projects.db")
        st = self.collect()
        self.assertEqual([s for s, _ in cards.render_all(st, "en")], ["cover", "summary"])

    def test_small_token_count_uses_the_hobbit(self):
        st = self.collect()
        st.tokens_in_out = 62_000
        doc = cards.card_tokens(st, cards.T["en"], "en", "2026")[1]
        self.assertIn("The Hobbit", doc)
        self.assertIn("0.5", doc)
        st.tokens_in_out = 367
        doc = cards.card_tokens(st, cards.T["en"], "en", "2026")[1]
        self.assertIn("1 page of a novel", doc)
        self.assertNotIn("0.0", doc)

    def test_singular_wording_on_tiny_history(self):
        make_db([("x", "cli", "m", ts(2026, 5, 1), 3, 1, 1, 0, None, None)],
                [("x", "user", "damn it works", None, ts(2026, 5, 1)), ("x", "tool", "ok", "terminal", ts(2026, 5, 1, 12, 1))])
        st = self.collect()
        docs = "".join(d for _s, d in cards.render_all(st, "en"))
        for bad in ("1 coins", "1 tool calls", "1 messages", "1 active days", "top 1 tools", "Your top 5 tools",
                    "1 chats", "1 conversations", ">1</b>chats", ">1</b>messages", ">1</b>tool calls"):
            self.assertFalse(bad in docs, bad)
        self.assertNotIn("damn</span>", docs)  # swear words never become the word of the year
        self.assertIn("Your top tool", docs)


class TestCommands(Base):
    def test_register(self):
        ctx = FakeCtx()
        hw.register(ctx)
        self.assertIn("year-wrapped", ctx.commands)
        self.assertIn("year-wrapped", ctx.cli)

    def args(self, **kw):
        base = dict(year=2026, days=None, all=False, lang="en", tz="UTC", show_titles=False, out=None, no_png=True,
                    json=False, rename=[])
        base.update(kw)
        return Namespace(**base)

    def test_cli_writes_cards_and_index(self):
        hw._ctx = FakeCtx()
        buf = StringIO()
        with redirect_stdout(buf):
            rc = hw._cli_handler(self.args())
        self.assertEqual(rc, 0)
        d = HOME / "plugin-data" / "year-wrapped" / "2026"
        self.assertEqual(len(list(d.glob("[0-9][0-9]-*.html"))), 13)
        self.assertTrue((d / "index.html").is_file())
        self.assertIn("Session titles are hidden", buf.getvalue())
        self.assertNotIn("Secret client plan", buf.getvalue())

    def test_cli_out_dir_keeps_foreign_files(self):
        target = HOME / "mine"
        target.mkdir(exist_ok=True)
        (target / "99-holiday.png").write_bytes(b"x")
        with redirect_stdout(StringIO()):
            hw._cli_handler(self.args(out=str(target)))
        self.assertTrue((target / "99-holiday.png").exists())

    def test_cli_rename(self):
        buf = StringIO()
        with redirect_stdout(buf):
            hw._cli_handler(self.args(json=True, rename=["dashboard=Northstar"]))
        top = json.loads(buf.getvalue())["word_of_the_year"]
        self.assertEqual(top[0][0], "Northstar")
        self.assertNotIn("dashboard", [w for w, _n in top])

    def test_cli_json(self):
        buf = StringIO()
        with redirect_stdout(buf):
            hw._cli_handler(self.args(json=True))
        data = json.loads(buf.getvalue())
        self.assertEqual(data["sessions"], 3)
        self.assertEqual(data["persona"]["code"], "NATM")

    def test_slash_command(self):
        hw._ctx = FakeCtx({"language": "en", "timezone": "UTC"})
        out = hw.slash_wrapped("2026")
        self.assertIn("Year Wrapped 2026", out)
        self.assertIn("The Nocturnal Interrogator", out)
        self.assertIn("index.html", out)
        self.assertIn("/year-wrapped 30", hw.slash_wrapped("help"))
        self.assertEqual(json.loads(hw.slash_wrapped("2026 json"))["cron_runs"], 2)

    def test_slash_never_raises(self):
        with mock.patch.object(hw, "build_stats", side_effect=RuntimeError("boom")):
            self.assertIn("could not read", hw.slash_wrapped(""))

    def test_manifest_matches_registrations(self):
        text = (ROOT / "plugin.yaml").read_text()
        self.assertNotIn("provides_hooks", text)
        self.assertNotIn("provides_tools", text)
        for key in hw.DEFAULTS:
            self.assertIn(key + ":", text)


if __name__ == "__main__":
    unittest.main()
