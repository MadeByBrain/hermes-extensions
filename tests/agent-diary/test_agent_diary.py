"""Offline tests for the agent-diary helper (standard library only).

Run: python3 tests/agent-diary/test_agent_diary.py
"""
import atexit
import datetime as dt
import importlib.util
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "agent-diary" / "scripts" / "diary.py"

HOME = Path(tempfile.mkdtemp(prefix="agent-diary-test-"))
atexit.register(shutil.rmtree, HOME, True)
os.environ["HERMES_HOME"] = str(HOME)
os.environ["AGENT_DIARY_DIR"] = str(HOME / "diary")
os.environ.pop("AGENT_DIARY_STATE_DB", None)
os.environ.pop("AGENT_DIARY_EXCLUDE", None)

spec = importlib.util.spec_from_file_location("diary", SCRIPT)
diary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diary)

TZ = dt.timezone.utc
DAY = dt.date(2026, 3, 10)


def ts(h, m=0, day=DAY):
    return dt.datetime(day.year, day.month, day.day, h, m, tzinfo=TZ).timestamp()


def build_db(path: Path):
    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT NOT NULL, title TEXT, started_at REAL NOT NULL,
                           ended_at REAL, last_activity_at REAL);
    CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, role TEXT NOT NULL,
                           content TEXT, tool_name TEXT, timestamp REAL NOT NULL);
    """)
    sessions = [
        ("s1", "telegram", "Pricing for Acme Corp", ts(8), None, ts(12)),
        ("s2", "cli", "Fix the deploy", ts(22), None, ts(23, 50)),
        ("cron1", "cron", "nightly job", ts(3), None, ts(3, 5)),
        ("old", "cli", "first day ever", ts(9, day=DAY - dt.timedelta(days=9)), None,
         ts(9, day=DAY - dt.timedelta(days=9))),
        ("prev", "cli", "yesterday chat", ts(23, day=DAY - dt.timedelta(days=1)), None, ts(0, 30)),
    ]
    con.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?)", sessions)
    msgs = [
        ("s1", "user", "Good morning, please check the Acme Corp offer", None, ts(8, 5)),
        ("s1", "assistant", "Sure.", None, ts(8, 6)),
        ("s1", "tool", "{}", "terminal", ts(8, 7)),
        ("s1", "tool", "{}", "terminal", ts(8, 8)),
        ("s1", "tool", "{}", "read_file", ts(8, 9)),
        ("s1", "user", "no, that's wrong. again please", None, ts(9, 0)),
        ("s1", "assistant", "You're right, my mistake.", None, ts(9, 1)),
        ("s1", "user", "THIS IS STILL NOT WORKING AT ALL", None, ts(11, 0)),
        ("s1", "user", "[IMPORTANT: background process finished]", None, ts(11, 30)),
        ("s1", "user", "\x60\x60\x60\nplease please please\n\x60\x60\x60\nthanks", None, ts(11, 40)),
        ("s2", "user", "deploy it, damn", None, ts(22, 10)),
        ("s2", "tool", "{}", "patch", ts(22, 11)),
        ("cron1", "user", "please run the nightly job", None, ts(3, 1)),
        ("cron1", "tool", "{}", "terminal", ts(3, 2)),
        ("prev", "user", "late one before midnight", None, ts(23, 10, day=DAY - dt.timedelta(days=1))),
        ("prev", "user", "and one after midnight, thanks", None, ts(0, 20)),
    ]
    con.executemany("INSERT INTO messages (session_id, role, content, tool_name, timestamp) VALUES (?,?,?,?,?)",
                    msgs)
    con.commit()
    con.close()


build_db(HOME / "state.db")


class FactsTest(unittest.TestCase):
    def setUp(self):
        self.f = diary.collect_facts(DAY, TZ, "UTC")

    def test_counts_only_the_day_and_only_real_typing(self):
        u = self.f["user"]
        # 4 typed messages in s1 (IMPORTANT notice dropped), 1 in s2, 1 after midnight in "prev"; cron excluded
        self.assertEqual(u["messages"], 6)
        self.assertEqual(u["first_message"], "00:20")
        self.assertEqual(u["last_message"], "22:10")
        self.assertEqual(u["messages_after_midnight"], 1)
        self.assertEqual(u["longest_message_time"], "08:05")

    def test_code_blocks_do_not_count_as_politeness(self):
        # please (08:05), please (09:00), thanks (11:40), thanks (00:20); the fenced block is ignored
        self.assertEqual(self.f["user"]["please_thanks"], 4)
        self.assertEqual(self.f["user"]["swears"], 1)

    def test_corrections_shouts_admissions(self):
        self.assertEqual(self.f["user"]["corrections"], 1)
        self.assertEqual(self.f["user"]["all_caps_messages"], 1)
        self.assertEqual(self.f["agent"]["admissions"], 1)

    def test_tools_exclude_background_jobs(self):
        a = self.f["agent"]
        self.assertEqual(a["tool_calls"], 4)
        self.assertEqual(a["top_tools"][0], {"tool": "terminal", "calls": 2})
        self.assertEqual(a["background_jobs_today"], 1)

    def test_day_number_and_sessions(self):
        self.assertEqual(self.f["day_number"], 10)
        self.assertEqual(self.f["sessions"]["count"], 3)
        self.assertNotIn("nightly job", self.f["sessions"]["titles"])

    def test_snippets_are_tagged_and_short(self):
        tags = {s["tag"] for s in self.f["snippets"]}
        self.assertTrue({"first", "last", "correction", "all_caps"} <= tags)
        self.assertTrue(all(len(s["text"]) <= diary.SNIPPET_MAX for s in self.f["snippets"]))

    def test_quiet_day(self):
        f = diary.collect_facts(DAY + dt.timedelta(days=5), TZ, "UTC")
        self.assertTrue(f["quiet_day"])
        self.assertEqual(f["user"]["messages"], 0)
        self.assertEqual(f["snippets"], [])

    def test_private_vocab_is_not_printed(self):
        self.assertIn("_vocab", self.f)
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            diary._print(self.f)
        self.assertNotIn("_vocab", json.loads(buf.getvalue()))


class LineCheckTest(unittest.TestCase):
    def setUp(self):
        self.f = diary.collect_facts(DAY, TZ, "UTC")

    def test_names_from_today_are_flagged(self):
        w = diary.check_line("Acme wanted three offers today.", self.f)
        self.assertTrue(any(x.startswith("check_names") and "Acme" in x for x in w))

    def test_weekdays_are_not_names(self):
        f = dict(self.f, _vocab=set(self.f["_vocab"]) | {"friday"})
        self.assertEqual(diary.check_line("Friday the 13th, you never know.", f), [])

    def test_brand_names_in_entry_are_flagged(self):
        w = diary.check_body("We listed the site on GoodFirms and fixed example.com. Then Acme called.", self.f)
        self.assertTrue(w and all(x in w[0] for x in ("GoodFirms", "example.com", "Acme")))
        self.assertEqual(diary.check_body("A quiet Friday. Nobody called.", self.f), [])

    def test_clean_line_passes(self):
        self.assertEqual(diary.check_line("Six messages from my human, four tool calls from me.", self.f), [])

    def test_dash_link_length(self):
        w = diary.check_line("a \u2014 b https://x.y " + "x" * 300)
        self.assertTrue(any("too_long" in x for x in w))
        self.assertTrue(any("contains_dash" in x for x in w))
        self.assertTrue(any("link" in x for x in w))


class EntryAndCardTest(unittest.TestCase):
    def test_save_read_recent_streak_card(self):
        f = diary.collect_facts(DAY, TZ, "UTC")
        r = diary.save_entry(DAY.isoformat(), "Six   messages, four commands.", "Day 10. Test", "Body text.", f)
        self.assertTrue(r["ok"])
        p = Path(r["path"])
        self.assertEqual(oct(p.stat().st_mode & 0o777), "0o600")
        e = diary.read_entry(p)
        self.assertEqual(e["line"], "Six messages, four commands.")
        self.assertEqual(e["stats"]["messages"], 6)
        self.assertEqual(e["body"], "Body text.")
        nxt = DAY + dt.timedelta(days=1)
        self.assertEqual(diary._streak(nxt), 1)
        self.assertEqual(diary.recent_entries(3, before=nxt)[0]["title"], "Day 10. Test")
        self.assertEqual(diary.recent_entries(3, before=DAY), [])

        html = diary.card_html(e, "de", "night")
        self.assertIn("Tag 10", html)
        self.assertIn("vier&nbsp;commands.".replace("vier", "four"), html)
        self.assertEqual(html.count("commands"), 1)  # last two words joined, nothing duplicated
        self.assertNotIn("\u2014", html)

    def test_saved_stats_match_what_the_agent_read(self):
        f = diary.collect_facts(DAY, TZ, "UTC")
        diary.write_snapshot(f)
        later = json.loads(json.dumps({k: v for k, v in f.items() if not k.startswith("_")}))
        later["agent"]["tool_calls"] = 999  # the day went on between facts and save
        r = diary.save_entry(DAY.isoformat(), "A line.", "T", "Body.", later)
        self.assertEqual(diary.read_entry(Path(r["path"]))["stats"]["tool_calls"], 4)

    def test_empty_body_rejected(self):
        self.assertFalse(diary.save_entry("2026-03-11", "x", "", "   ", None)["ok"])

    def test_card_without_entry(self):
        self.assertFalse(diary.render_card("2026-01-01", "en", "night")["ok"])


class CliTest(unittest.TestCase):
    def test_main_facts_prints_json(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = diary.main(["facts", "--date", DAY.isoformat(), "--tz", "UTC"])
        self.assertEqual(code, 0)
        d = json.loads(buf.getvalue())
        self.assertTrue(d["ok"])
        self.assertEqual(d["date"], DAY.isoformat())

    def test_timezone_from_config(self):
        (HOME / "config.yaml").write_text("model: x\ntimezone: Europe/Berlin\n", encoding="utf-8")
        try:
            _tz, name = diary._tz("")
            self.assertEqual(name, "Europe/Berlin")
        finally:
            (HOME / "config.yaml").unlink()


if __name__ == "__main__":
    unittest.main(verbosity=1)
