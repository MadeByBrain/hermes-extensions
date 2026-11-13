"""Offline tests for manners-meter. No network, no model.

Run:  python -m unittest discover -s tests -v      (from the plugin folder; Python 3.11+)
"""
from __future__ import annotations

import atexit
import importlib.util
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path(tempfile.mkdtemp(prefix="manners-meter-test-"))
atexit.register(shutil.rmtree, HOME, True)
os.environ["HERMES_HOME"] = str(HOME)

_spec = importlib.util.spec_from_file_location("manners_meter_plugin", ROOT / "__init__.py",
                                               submodule_search_locations=[str(ROOT)])
mm = importlib.util.module_from_spec(_spec)
sys.modules["manners_meter_plugin"] = mm
_spec.loader.exec_module(mm)
from manners_meter_plugin import card, meter  # noqa: E402

FENCE = "\x60" * 3


class FakeCtx:
    def __init__(self, settings=None):
        self.settings = dict(settings or {})
        self.hooks, self.commands, self.cli = {}, {}, {}

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_hook(self, name, fn, **kw):
        self.hooks[name] = fn

    def register_command(self, name, handler, description="", args_hint="", **kw):
        self.commands[name] = handler

    def register_cli_command(self, name, help, setup_fn, handler_fn=None, description=""):
        self.cli[name] = (setup_fn, handler_fn)


def make_db(rows):
    """rows: (session_id, source, role, content, timestamp)."""
    db = HOME / "state.db"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT)")
    con.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, role TEXT, "
                "content TEXT, tool_calls TEXT, timestamp REAL)")
    for sid, src, *_ in rows:
        con.execute("INSERT OR IGNORE INTO sessions VALUES (?,?)", (sid, src))
    for sid, _src, role, content, ts in rows:
        con.execute("INSERT INTO messages (session_id, role, content, tool_calls, timestamp) VALUES (?,?,?,?,?)",
                    (sid, role, content, None, ts))
    con.commit()
    con.close()
    return db


NOW = time.time()
SAMPLE = [
    ("s1", "cli", "user", "Bitte prüf das. Vielen Dank!", NOW - 100),
    ("s1", "cli", "assistant", "Erledigt.", NOW - 99),
    ("s1", "cli", "assistant", "Gern geschehen.", NOW - 98),
    ("s1", "cli", "user", "So ein Mist, das ist kaputt", NOW - 90),
    ("s1", "cli", "assistant", "Schauen wir.", NOW - 89),
    ("s2", "telegram", "user", "please fix this, thanks", NOW - 50),
    ("s2", "telegram", "assistant", "You're welcome", NOW - 49),
    ("s3", "cron", "user", "please please please run the job", NOW - 40),  # machine, excluded
    ("s4", "cli", "user", "old message, thank you", NOW - 90 * 86400),
]


class CountingTests(unittest.TestCase):
    def test_phrases_win_over_single_words(self):
        hits = {label: n for _r, label, n in meter.polite_hits("Vielen Dank! Danke schön. Danke. Thank you, thanks")}
        self.assertEqual(hits, {"vielen dank": 1, "dankeschön": 1, "danke": 1, "thank you": 1, "thanks": 1})

    def test_word_boundaries(self):
        self.assertEqual(meter.polite_hits("pleased, unthankful, bitter, dankbar"), [])
        self.assertEqual(meter.swear_hits("mistake, Mistral, shitake? no: shitake"), [])
        self.assertEqual(sum(n for *_x, n in meter.swear_hits("Fucking hell, so ein Mist, Scheiße")), 3)

    def test_clean_drops_code_quotes_and_system(self):
        text = f"danke\n{FENCE}\nplease please\n{FENCE}\n> thanks from a quote\nok"
        self.assertEqual(sum(n for *_x, n in meter.polite_hits(meter.clean_user_text(text))), 1)
        self.assertEqual(meter.clean_user_text("[System: please do x]"), "")
        self.assertEqual(meter.clean_user_text("[OUT-OF-BAND USER MESSAGE] thanks"), "")

    def test_extra_words(self):
        hits = meter.polite_hits("Merci vielmals, sehr nett", extra=["sehr nett"])
        self.assertIn(("custom.sehr nett", "sehr nett", 1), hits)

    def test_tokens_estimate(self):
        self.assertEqual(meter.estimate_tokens("bitte"), 2)
        self.assertEqual(meter.estimate_tokens("ty"), 1)


class ReportTests(unittest.TestCase):
    def setUp(self):
        make_db(SAMPLE)
        mm.register(FakeCtx())

    def test_report_all_time(self):
        rep = mm.build_report()
        self.assertEqual(rep.user_messages, 4)  # cron excluded
        self.assertEqual(rep.sessions, 3)
        self.assertEqual(rep.polite["bitte"], 1)
        self.assertEqual(rep.polite["vielen dank"], 1)
        self.assertEqual(rep.polite["please"], 1)
        self.assertEqual(rep.polite_total, 5)
        self.assertEqual(rep.swear_total, 1)
        self.assertEqual(rep.welcome_total, 2)
        # s1: first user message (bitte 2 + vielen dank 3 tokens) is carried by 3 later assistant calls
        self.assertEqual(rep.carried_tokens, 5 * 3 + 4)  # plus s2: please 2 + thanks 2, one call

    def test_days_filter(self):
        rep = mm.build_report(days=30)
        self.assertEqual(rep.user_messages, 3)
        self.assertNotIn("thank you", rep.polite)

    def test_missing_db(self):
        (HOME / "state.db").unlink()
        rep = mm.build_report()
        self.assertEqual(rep.user_messages, 0)
        self.assertIn("Cold Commander", meter.render_text(rep, lang="en"))

    def test_slash_command(self):
        out = mm.slash_manners("")
        self.assertIn("4", out)
        self.assertIn("1", out)
        self.assertIn("Swear jar", out)  # 3 German vs 3 English votes: a tie falls back to English
        mm.register(FakeCtx({"language": "de"}))
        self.assertIn("Schimpfglas: 1 Münzen = 1,00 €", mm.slash_manners(""))
        mm.register(FakeCtx())
        chat = mm.slash_manners("chat", session_id="s2")
        self.assertIn("1", chat)
        self.assertIn("thanks", chat)
        data = json.loads(mm.slash_manners("json"))
        self.assertEqual(data["swear_total"], 1)
        self.assertIn("/manners 30", mm.slash_manners("help"))

    def test_language_setting(self):
        mm.register(FakeCtx({"language": "en", "currency": "CHF", "jar_price": 2}))
        out = mm.slash_manners("")
        self.assertIn("Swear jar: 1 coins = 2.00 CHF", out)

    def test_card(self):
        out = mm.slash_manners("card")
        path = Path(out.rsplit(": ", 1)[1])
        self.assertTrue(path.is_file())
        doc = path.read_text()
        self.assertIn("manners-meter", doc)
        self.assertIn("1080", doc)
        self.assertNotIn("http", doc.replace("hermes plugins install", ""))  # no external resources
        self.assertTrue(str(path).startswith(str(HOME / "plugin-data" / "manners-meter")))

    def test_card_escapes(self):
        rep = meter.Report(user_messages=1)
        rep.polite["<script>"] = 3
        self.assertNotIn("<script>", card.render_card(rep))

    def test_cli(self):
        import argparse
        import contextlib
        import io
        ctx = FakeCtx()
        mm.register(ctx)
        setup, handler = ctx.cli["manners"]
        p = argparse.ArgumentParser()
        setup(p)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(handler(p.parse_args(["--json"])), 0)
        self.assertEqual(json.loads(buf.getvalue())["user_messages"], 4)
        target = HOME / "c.html"
        with contextlib.redirect_stdout(io.StringIO()):
            handler(Namespace(days=None, json=False, card=str(target)))
        self.assertTrue(target.is_file())


class JarHookTests(unittest.TestCase):
    def setUp(self):
        make_db(SAMPLE)
        mm._JAR_CACHE.clear()

    def test_reacts_to_swear(self):
        mm.register(FakeCtx())
        r = mm.on_pre_llm_call(user_message="verdammt, schon wieder", session_id="new", platform="cli")
        self.assertIn("Schimpfglas", r["context"])
        self.assertIn("2 Münzen", r["context"])  # 1 stored + this one
        r2 = mm.on_pre_llm_call(user_message="shit happens", session_id="new", platform="cli")
        self.assertIn("3 coins", r2["context"])  # cached path

    def test_counts_stored_message_once(self):
        mm.register(FakeCtx())
        r = mm.on_pre_llm_call(user_message="So ein Mist, das ist kaputt", session_id="s1", platform="cli")
        self.assertIn("1 Münzen", r["context"])

    def test_quiet_cases(self):
        mm.register(FakeCtx())
        self.assertIsNone(mm.on_pre_llm_call(user_message="danke dir", session_id="x", platform="cli"))
        self.assertIsNone(mm.on_pre_llm_call(user_message="shit", session_id="x", platform="cron"))
        self.assertIsNone(mm.on_pre_llm_call(user_message=None, session_id="x", platform="cli"))
        mm.register(FakeCtx({"jar_reactions": False}))
        self.assertIsNone(mm.on_pre_llm_call(user_message="shit", session_id="x", platform="cli"))

    def test_hook_never_raises(self):
        mm.register(FakeCtx({"extra_swear": "not a list"}))
        mm.on_pre_llm_call(user_message="shit", session_id="x", platform="cli")


class SpeedTests(unittest.TestCase):
    """Every user message runs through these regexes; no input may take long."""

    def test_adversarial_inputs(self):
        limit = 200_000
        probes = ["\n" * limit, " " * limit, "\t" * limit, "a" * limit, ("danke " * 40000)[:limit],
                  ("please" * 40000)[:limit], (FENCE + "x") * 50000, ">" * limit, "vielen  " * 25000,
                  ("s'il " * 40000)[:limit], ("[System " * 25000)[:limit]]
        for p in probes:
            t = time.time()
            text = meter.clean_user_text(p)
            meter.polite_hits(text)
            meter.swear_hits(text)
            meter.welcome_hits(p)
            self.assertLess(time.time() - t, 1.5, repr(p[:20]))


if __name__ == "__main__":
    unittest.main()
