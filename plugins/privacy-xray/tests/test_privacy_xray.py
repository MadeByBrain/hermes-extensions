"""Offline tests for privacy-xray. No network, no model.

Run with the Hermes Python, from the Hermes install dir (so hermes_cli / hermes_state are importable):
    cd <hermes-agent> && PYTHONDONTWRITEBYTECODE=1 venv/bin/python <plugin>/tests/test_privacy_xray.py -v
The tests create their own temporary HERMES_HOME and remove it at exit.
"""
from __future__ import annotations

import atexit
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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path(tempfile.mkdtemp(prefix="privacy-xray-test-"))
atexit.register(shutil.rmtree, HOME, True)
os.environ["HERMES_HOME"] = str(HOME)
if (Path.cwd() / "hermes_cli").is_dir():  # run from the Hermes install dir
    sys.path.insert(0, str(Path.cwd()))
    try:
        # Hermes relaunches itself into its managed runtime and activates its dependencies here.
        # Import it first, so that happens before any test runs (not in the middle of one).
        import hermes_bootstrap  # noqa: F401
    except Exception:  # noqa: BLE001
        pass
os.environ.pop("HERMES_DUMP_REQUESTS", None)

_spec = importlib.util.spec_from_file_location("privacy_xray_plugin", ROOT / "__init__.py",
                                               submodule_search_locations=[str(ROOT)])
px = importlib.util.module_from_spec(_spec)
sys.modules["privacy_xray_plugin"] = px
_spec.loader.exec_module(px)
from privacy_xray_plugin import audit, detect, report, scan, store, vendors, views  # noqa: E402

try:
    import hermes_cli.config as hconfig  # noqa: F401
    HAVE_HERMES = True
except Exception:  # noqa: BLE001
    HAVE_HERMES = False


class FakeCtx:
    def __init__(self, settings=None, surface="cli"):
        self.settings = dict(settings or {})
        self.surface = surface
        self.hooks, self.tools, self.commands, self.skills, self.middleware = {}, {}, {}, {}, {}

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_hook(self, name, fn, **kw):
        self.hooks[name] = fn

    def register_middleware(self, kind, fn):
        self.middleware[kind] = fn

    def register_tool(self, name, toolset, schema, handler, **kw):
        self.tools[name] = (schema, handler)

    def register_command(self, name, handler, description="", args_hint="", **kw):
        self.commands[name] = handler

    def register_skill(self, name, path, description=""):
        self.skills[name] = (Path(path), description)

    def session_surface(self):
        return self.surface


def setup(surface="cli", **settings) -> FakeCtx:
    ctx = FakeCtx({"language": "en", **settings}, surface=surface)
    px.register(ctx)
    return ctx


def write_config(text: str) -> None:
    path = HOME / "config.yaml"
    path.write_text(text, encoding="utf-8")
    t = time.time() + 1
    os.utime(path, (t, t))
    # bump again so mtime-based caches see a change even within one second
    time.sleep(0.01)


def reset_data() -> None:
    shutil.rmtree(HOME / "plugin-data", ignore_errors=True)
    px._needles_cache.update(key=None)


FAKE_IBAN = "DE89 3704 0044 0532 0130 00"  # the well-known documentation IBAN (valid check sum)


def main_kwargs(messages, system="You are Hermes.", **over):
    kw = dict(session_id="s1", turn_id="t1", provider="anthropic", model="claude-opus-5-5",
              base_url="https://api.anthropic.com", api_mode="anthropic_messages", request_messages=messages,
              system_prompt=system, api_request_id="r1", platform="cli", request={"body": "ignored"})
    kw.update(over)
    return kw


class DetectorTests(unittest.TestCase):
    def test_email(self):
        self.assertEqual(detect.detect("mail me: a.b+c@sub.example.org, x@y")["email"], 1)
        self.assertNotIn("email", detect.detect("no mail @ here or a@b"))

    def test_iban(self):
        self.assertTrue(detect.iban_valid(FAKE_IBAN))
        self.assertFalse(detect.iban_valid("DE89 3704 0044 0532 0130 01"))
        self.assertEqual(detect.detect(f"IBAN {FAKE_IBAN} and DE89370400440532013000")["iban"], 2)
        self.assertNotIn("iban", detect.detect("DE00 1234 5678 9012 3456 78"))

    def test_card(self):
        self.assertEqual(detect.detect("card 4111 1111 1111 1111 exp")["card"], 1)
        self.assertNotIn("card", detect.detect("order 4111 1111 1111 1112"))
        self.assertNotIn("card", detect.detect("1234567890123456"))

    def test_phone_ip(self):
        d = detect.detect("call +49 176 1234567 or +44 7700 900123, server 8.8.8.8, lan 192.168.1.20, version 1.2.3")
        self.assertEqual(d["phone"], 2)
        self.assertEqual(d["ipv4"], 1, "only the public address counts")
        self.assertNotIn("phone", detect.detect("+12 or +1 23"))

    def test_german_ids(self):
        # valid Steuer-ID example from the BZSt test set (digit rule + check digit)
        self.assertTrue(detect.tax_id_de_valid("86095742719"))
        self.assertFalse(detect.tax_id_de_valid("86095742718"))
        self.assertTrue(detect.vat_de_valid("DE136695976"))
        self.assertFalse(detect.vat_de_valid("DE136695975"))
        d = detect.detect("Steuer-ID 86 095 742 719, USt DE136695976")
        self.assertEqual(d.get("tax_id_de"), 1)
        self.assertEqual(d.get("vat_id_de"), 1)

    def test_disabled_detectors(self):
        self.assertEqual(detect.detect("a@example.org", enabled=("iban",)), {})


class CanaryTests(unittest.TestCase):
    def test_canary_values_are_fake_and_valid(self):
        for _ in range(50):
            c = store.make_canary()
            self.assertTrue(c["email"].endswith("@example.org"))
            self.assertTrue(detect.iban_valid(c["iban"]))
            self.assertTrue(c["iban"].replace(" ", "")[4] == "0", "bank code must start with 0")
            self.assertRegex(c["phone"], r"^\+44 7700 900[0-9]{3}$")
            self.assertIn(c["name"], c["match"])
            self.assertEqual(detect.detect(c["iban"])["iban"], 1)


class WalkTests(unittest.TestCase):
    def test_shapes(self):
        chat = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"},
                {"role": "assistant", "content": None, "tool_calls": [{"function": {"arguments": "{\"q\":1}"}}]},
                {"role": "tool", "content": "result"}]
        self.assertEqual([f for f, _ in detect.iter_fields(chat, "sys")], ["system", "user", "assistant", "tool"])
        anth = [{"role": "user", "content": [{"type": "text", "text": "hi"},
                                             {"type": "image", "source": {"data": "AAAA"}}]},
                {"role": "assistant", "content": [{"type": "tool_use", "input": {"x": "y"}}]},
                {"role": "user", "content": [{"type": "tool_result", "content": "out"}]}]
        fields = list(detect.iter_fields(anth, "S"))
        self.assertEqual([f for f, _ in fields], ["user", "assistant", "tool", "system"])
        self.assertNotIn("AAAA", "".join(t for _, t in fields))
        resp = [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "q"}]},
                {"type": "function_call", "arguments": "{}"}, {"type": "function_call_output", "output": "o"}]
        self.assertEqual([f for f, _ in detect.iter_fields(resp)], ["user", "assistant", "tool"])

    def test_cache(self):
        sc = detect.Scanner(size=8)
        n = detect.Needles()
        msgs = [{"role": "user", "content": "x" * 1000 + " a@example.org"}]
        sc.scan_request(msgs, None, n, detect.DETECTORS)
        sc.scan_request(msgs, None, n, detect.DETECTORS)
        self.assertEqual(sc.hits, 1)
        for i in range(20):
            sc.scan_request([{"role": "user", "content": str(i)}], None, n, detect.DETECTORS)
        self.assertLessEqual(len(sc._cache), 8)


class VendorTests(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(vendors.classify("api.anthropic.com")["hq"], "US")
        self.assertEqual(vendors.classify("openrouter.ai")["kind"], "router")
        self.assertEqual(vendors.classify("api.deepseek.com")["hq"], "CN")
        self.assertTrue(vendors.classify("127.0.0.1")["local"])
        self.assertTrue(vendors.classify("100.101.102.103")["local"])
        self.assertTrue(vendors.classify("192.168.0.4")["local"])
        self.assertEqual(vendors.classify("llm.aihosting.mittwald.de")["hq"], "DE")
        self.assertEqual(vendors.classify("", "anthropic")["vendor"], "Anthropic")
        self.assertEqual(vendors.classify("weird.example")["hq"], "unknown")
        self.assertEqual(vendors.host_of("https://openrouter.ai/api/v1/"), "openrouter.ai")
        self.assertTrue(vendors.in_region("DE", "EU"))
        self.assertFalse(vendors.in_region("US", "EU,CH"))
        self.assertIsNone(vendors.in_region("US", ""))


class HookTests(unittest.TestCase):
    def setUp(self):
        reset_data()

    def test_main_and_aux_recorded_without_content(self):
        ctx = setup()
        c = store.add_canary()
        msgs = [{"role": "user", "content": f"Remind {c['name']} ({c['email']}), IBAN {c['iban']}"}]
        self.assertIsNone(ctx.hooks["pre_api_request"](**main_kwargs(msgs)))
        self.assertIsNone(ctx.hooks["pre_auxiliary_call"](
            aux_task="title_generation", provider="openrouter", model="google/gemini-3.7-flash",
            base_url="https://openrouter.ai/api/v1/", request_messages=msgs, system_prompt="Title it",
            session_id="s1", turn_id="t1"))
        recs = store.read_ledger()
        self.assertEqual([r["kind"] for r in recs], ["main", "aux"])
        main, aux = recs
        self.assertEqual(main["host"], "api.anthropic.com")
        self.assertEqual(main["hq"], "US")
        self.assertEqual(aux["aux_task"], "title_generation")
        self.assertEqual(aux["vendor"], "OpenRouter")
        self.assertEqual(main["canary"], [{"id": c["id"], "fields": ["user"]}])
        self.assertEqual(main["types"].get("email"), 1)
        self.assertEqual(main["types"].get("iban"), 1)
        raw = "".join(p.read_text() for p in store.ledger_paths() if p.exists())
        for v in c["match"]:
            self.assertNotIn(v.lower(), raw.lower(), "ledger must never contain content")
        self.assertNotIn("Remind", raw)

    def test_hooks_survive_garbage(self):
        ctx = setup()
        for kw in ({}, {"request_messages": "nope"}, {"request_messages": [None, 3, {"content": object()}]},
                   {"base_url": object(), "provider": 5}):
            self.assertIsNone(ctx.hooks["pre_api_request"](**kw))
            self.assertIsNone(ctx.hooks["pre_auxiliary_call"](**kw))

    def test_record_off(self):
        ctx = setup(record=False)
        ctx.hooks["pre_api_request"](**main_kwargs([{"role": "user", "content": "x"}]))
        self.assertEqual(store.read_ledger(), [])

    def test_rotation(self):
        for i in range(400):
            store.append_ledger({"ts": time.time(), "i": i, "pad": "x" * 200}, max_bytes=20000)
        cur, old = store.ledger_paths()
        self.assertTrue(old.exists())
        self.assertLessEqual(cur.stat().st_size, 20000)
        recs = store.read_ledger()
        self.assertEqual(recs[-1]["i"], 399)

    def test_watch_terms(self):
        ctx = setup(watch_terms=["Projekt Falke"])
        ctx.hooks["pre_api_request"](**main_kwargs([{"role": "user", "content": "about projekt falke"}]))
        self.assertEqual(store.read_ledger()[-1]["watch"], ["user"])


class GuardTests(unittest.TestCase):
    def setUp(self):
        reset_data()

    def test_guard_off_by_default(self):
        ctx = setup()
        store.add_canary()
        self.assertIsNone(ctx.middleware["llm_request"](request={"messages": [{"role": "user", "content": "x"}]}))

    def test_guard_masks_main_request_without_mutation(self):
        ctx = setup(guard=True, watch_terms=["Projekt Falke"])
        c = store.add_canary()
        original = {"model": "m", "system": f"Known: {c['email']}",
                    "messages": [{"role": "user", "content": [{"type": "text", "text": f"Pay {c['name']}, projekt falke"}]}]}
        snapshot = json.dumps(original)
        out = ctx.middleware["llm_request"](request=original, api_request_id="rq")
        self.assertEqual(json.dumps(original), snapshot, "original request must not be mutated")
        body = json.dumps(out["request"])
        self.assertNotIn(c["name"], body)
        self.assertNotIn(c["email"], body)
        self.assertNotIn("projekt falke", body.lower())
        self.assertIn("[masked by privacy-xray]", body)
        ctx.hooks["pre_api_request"](**main_kwargs(out["request"]["messages"], out["request"]["system"],
                                                   api_request_id="rq"))
        rec = store.read_ledger()[-1]
        self.assertEqual(rec["canary"], [])
        self.assertEqual(rec["masked"], 3)


BASE_CFG = """
model:
  provider: anthropic
  default: claude-opus-5-5
  base_url: https://api.anthropic.com
auxiliary:
  title_generation:
    provider: openrouter
    model: google/gemini-3.7-flash
  vision:
    provider: openrouter
    model: google/gemini-3.7-flash
  compression:
    provider: auto
sessions:
  auto_prune: false
"""


@unittest.skipUnless(HAVE_HERMES, "needs the Hermes Python")
class AuditTests(unittest.TestCase):
    def setUp(self):
        reset_data()
        write_config(BASE_CFG)
        (HOME / "gateway_state.json").unlink(missing_ok=True)
        shutil.rmtree(HOME / "sessions", ignore_errors=True)

    def find(self, res, fid):
        return next(f for f in res["findings"] if f["id"] == fid)

    def test_check_findings(self):
        res = audit.check()
        self.assertEqual(self.find(res, "main.model")["severity"], "green")
        t = self.find(res, "aux.title_generation")
        self.assertEqual(t["severity"], "red")
        self.assertEqual(audit.fix_commands(t), ["hermes config set auxiliary.title_generation.provider auto",
                                                 'hermes config set auxiliary.title_generation.model ""'])
        self.assertEqual(self.find(res, "aux.vision")["severity"], "amber")
        self.assertEqual(self.find(res, "aux.compression")["severity"], "green")
        self.assertEqual(self.find(res, "sessions.retention")["severity"], "amber")
        self.assertEqual(self.find(res, "dumps")["severity"], "green")
        ids = {f["id"] for f in res["findings"]}
        self.assertIn("aux.goal_judge", ids, "side tasks are discovered from Hermes defaults")

    def test_region(self):
        res = audit.check(region="EU")
        self.assertEqual(self.find(res, "main.model")["severity"], "amber")

    def test_dumps_and_gateways(self):
        (HOME / "sessions").mkdir(exist_ok=True)
        (HOME / "sessions" / "request_dump_x.json").write_text("{}")
        (HOME / "gateway_state.json").write_text(json.dumps(
            {"gateway_state": "running", "platforms": {"telegram": {"state": "connected"},
                                                        "discord": {"state": "disconnected"}}}))
        res = audit.check()
        self.assertEqual(self.find(res, "dumps")["severity"], "red")
        self.assertEqual(self.find(res, "gateway.telegram")["severity"], "amber")
        self.assertEqual(self.find(res, "privacy.redact_pii")["severity"], "amber")
        self.assertNotIn("gateway.discord", {f["id"] for f in res["findings"]})

    def test_fix_show_then_apply(self):
        setup()
        shown = px.command_handler("fix aux.title_generation")
        self.assertIn("hermes config set auxiliary.title_generation.provider auto", shown)
        self.assertIn("--yes", shown)
        self.assertIn("Note: The task then runs on your main model", shown, "fix_show names the consequence")
        self.assertIn("openrouter", (HOME / "config.yaml").read_text(), "showing a fix must not apply it")
        done = px.command_handler("fix aux.title_generation --yes", platform="cli")
        self.assertIn("now green", done)
        res = audit.check()
        self.assertEqual(self.find(res, "aux.title_generation")["severity"], "green")
        self.assertEqual(px.command_handler("fix aux.title_generation"), "'aux.title_generation' is already green. Nothing to fix.")
        self.assertIn("No finding", px.command_handler("fix nope.nope"))


def make_state_db(home: Path, rows: list[tuple[str, str, str]], title: str = "") -> None:
    """A real Hermes state.db (schema incl. full-text indexes) via hermes_state.SessionDB."""
    from hermes_state import SessionDB
    db = SessionDB(home / "state.db")
    for sid in sorted({r[0] for r in rows}):
        db.create_session(sid, "cli")
    for sid, role, content in rows:
        db.append_message(sid, role, content)
    if title:
        db.set_session_title(rows[0][0], title)
    try:
        db.close()
    except Exception:  # noqa: BLE001
        pass


class ScanTests(unittest.TestCase):
    def setUp(self):
        reset_data()
        for p in ("state.db", "state.db-wal", "state.db-shm"):
            (HOME / p).unlink(missing_ok=True)
        for d in ("logs", "memories", "sessions", "cron"):
            shutil.rmtree(HOME / d, ignore_errors=True)

    def test_plain_db_like_fallback(self):
        db = sqlite3.connect(HOME / "state.db")
        db.executescript("CREATE TABLE sessions(id TEXT, title TEXT); CREATE TABLE messages(id INTEGER PRIMARY KEY,"
                         " session_id TEXT, role TEXT, content TEXT, tool_calls TEXT, timestamp REAL);")
        db.execute("INSERT INTO sessions VALUES('a','Reminder for Ilse Vintrell')")
        db.execute("INSERT INTO messages VALUES(1,'a','user','Hi Ilse Vintrell, here',NULL,1)")
        db.execute("INSERT INTO messages VALUES(2,'a','assistant','nothing',NULL,2)")
        db.commit()
        db.close()
        res = scan.search_state_db(HOME, ["Ilse Vintrell"])
        self.assertEqual(res["places"]["messages"]["count"], 1)
        self.assertEqual(res["places"]["session_titles"]["count"], 1)

    @unittest.skipUnless(HAVE_HERMES, "needs hermes_state")
    def test_real_schema_and_files(self):
        c = store.add_canary()
        long_tool = "x" * 9000 + c["email"]
        make_state_db(HOME, [("s1", "user", f"Pay {c['name']} now"), ("s1", "assistant", f"Sure, {c['iban']}"),
                             ("s1", "tool", long_tool), ("s2", "user", "unrelated")], title=f"Reminder {c['name']}")
        (HOME / "logs").mkdir()
        (HOME / "logs" / "agent.log").write_text(("noise\n" * 300000) + f"debug {c['email']}\n")
        (HOME / "logs" / "agent.log.1").write_text(f"old {c['phone']}\n")
        (HOME / "memories").mkdir()
        (HOME / "memories" / "MEMORY.md").write_text("nothing relevant")
        (HOME / "sessions").mkdir()
        (HOME / "sessions" / "request_dump_1.json").write_text(json.dumps({"body": c["name"]}))
        quick = scan.search_all(HOME, c["match"], store.data_dir())
        self.assertEqual(quick["state_db"]["places"]["messages"]["count"], 2, "tool tail beyond 8 KB needs --deep")
        self.assertIn("tool_tail", quick["coverage"])
        self.assertFalse(quick["partial"], "an uncovered index tail is a coverage note, not a cut budget")
        res = scan.search_all(HOME, c["match"], store.data_dir(), deep=True)
        self.assertEqual(res["coverage"], [])
        msgs = res["state_db"]["places"]["messages"]
        self.assertEqual(msgs["count"], 3)
        self.assertEqual(msgs["by_role"], {"assistant": 1, "tool": 1, "user": 1})
        self.assertEqual(msgs["sessions"], 1)
        self.assertEqual(res["state_db"]["places"]["session_titles"]["count"], 1)
        places = {p["place"]: p for p in res["places"]}
        self.assertEqual(places["logs/agent.log"]["count"], 1)
        self.assertEqual(places["logs/agent.log.1"]["count"], 1)
        self.assertTrue(places["sessions/request_dump_1.json"]["request_dump"])
        self.assertNotIn("memories/MEMORY.md", places)
        self.assertFalse(any("privacy-xray" in p for p in places), "own plugin-data is excluded")

    @unittest.skipUnless(HAVE_HERMES, "needs hermes_state")
    def test_find_and_export(self):
        setup()
        make_state_db(HOME, [("s1", "user", "Please email jane.roe@example.com about the invoice, IBAN " + FAKE_IBAN)])
        out = px.command_handler('find "jane.roe@example.com" --export', platform="cli")
        self.assertIn("state.db messages", out)
        self.assertNotIn("jane.roe@example.com", out.split("Access report")[0].split("\n", 1)[1],
                         "snippets are masked")
        md = sorted(store.reports_dir().glob("access-*.md"))
        self.assertTrue(md)
        text = md[-1].read_text()
        self.assertNotIn("jane.roe@example.com", text)
        self.assertNotIn("3704 0044", text, "other personal data in snippets is masked too")
        self.assertIn("| state.db | messages | 1 |", text)
        self.assertIn("Usage", px.command_handler("find ab", platform="cli"))


@unittest.skipUnless(HAVE_HERMES, "needs the Hermes Python")
class EndToEndTests(unittest.TestCase):
    def setUp(self):
        reset_data()
        write_config(BASE_CFG)
        for p in ("state.db", "state.db-wal", "state.db-shm"):
            (HOME / p).unlink(missing_ok=True)
        shutil.rmtree(HOME / "sessions", ignore_errors=True)
        shutil.rmtree(HOME / "logs", ignore_errors=True)

    def test_canary_trace_map_report_tool(self):
        ctx = setup()
        out = px.command_handler("canary")
        self.assertIn("example.org", out)
        c = store.latest_canary()
        trace0 = px.command_handler("trace")
        self.assertIn("not found anywhere yet", trace0)
        msgs = [{"role": "user", "content": f"Write to {c['name']} <{c['email']}>"}]
        ctx.hooks["pre_api_request"](**main_kwargs(msgs))
        ctx.hooks["pre_api_request"](**main_kwargs(msgs + [{"role": "assistant", "content": "ok"}], turn_id="t2"))
        ctx.hooks["pre_auxiliary_call"](aux_task="title_generation", provider="openrouter", model="g",
                                        base_url="https://openrouter.ai/api/v1", request_messages=msgs,
                                        session_id="s1", turn_id="t1")
        ctx.hooks["pre_auxiliary_call"](aux_task="compression", provider="anthropic", model="claude",
                                        base_url="https://api.anthropic.com", request_messages=msgs,
                                        session_id="", turn_id="")
        make_state_db(HOME, [("s1", "user", msgs[0]["content"])], title=f"Mail to {c['name']}")
        tr = px.command_handler("trace")
        self.assertIn("found in 5 places", tr)
        self.assertIn("side request: title_generation", tr)
        self.assertRegex(tr, r"\U0001F534 side request: title_generation")
        self.assertRegex(tr, r"\U0001F7E2 main request")
        mp = px.command_handler("map")
        self.assertIn("openrouter.ai", mp)
        self.assertIn("canary", mp)
        self.assertIn("4 requests", mp)
        self.assertIn("this chat", px.command_handler("map --session", session_id="s1"))
        rep = px.command_handler("report")
        path = Path(rep.split(": ", 1)[1].split("\n")[0])
        page = path.read_text()
        self.assertIn("<svg", page)
        self.assertNotIn("<script", page.lower())
        self.assertIsNone(re.search(r"(src|href)=\"https?:", page), "no external assets")
        self.assertIn("Canary", page)
        self.assertNotIn(c["iban"], page)
        schema, handler = ctx.tools["privacy_xray"]
        for action in ("map", "check", "trace"):
            res = json.loads(handler({"action": action}, session_id="s1"))
            self.assertTrue(res["ok"], res)
        res = json.loads(handler({"action": "find", "query": c["name"]}))
        self.assertTrue(res["ok"])
        self.assertFalse(json.loads(handler({"action": "find", "query": "x"}))["ok"])
        self.assertFalse(json.loads(handler({"action": "fix"}))["ok"])
        status = px.command_handler("")
        self.assertIn("Active canary", status)
        self.assertIn("/xray check", px.command_handler("help"))


def _send_canary(ctx, c, title_url="https://openrouter.ai/api/v1", sid="s1"):
    """One main request and one title side request that both carry canary c."""
    msgs = [{"role": "user", "content": f"Write to {c['name']} <{c['email']}>"}]
    ctx.hooks["pre_api_request"](**main_kwargs(msgs, session_id=sid, turn_id=sid + "t"))
    ctx.hooks["pre_auxiliary_call"](aux_task="title_generation", provider="x", model="google/gemini-3.7-flash",
                                    base_url=title_url, request_messages=msgs, session_id=sid, turn_id=sid + "t")


class ReportTests(unittest.TestCase):
    """The HTML leak map: self-contained, verdict, Sankey, before/after view, escaping."""

    def setUp(self):
        reset_data()
        write_config(BASE_CFG)
        for p in ("state.db", "state.db-wal", "state.db-shm"):
            (HOME / p).unlink(missing_ok=True)

    def assert_self_contained(self, page):
        low = page.lower()
        for bad in ("<script", "<link", "@import", "http://", "https://", "<iframe", "<img", "javascript:"):
            self.assertNotIn(bad, low, bad)
        self.assertIn("@keyframes flow", page)
        self.assertIn("prefers-reduced-motion", page)

    def test_before_after_view(self):
        ctx = setup()
        before = store.add_canary()
        _send_canary(ctx, before)  # side request goes to OpenRouter: extra recipient
        time.sleep(1.1)
        after = store.add_canary()
        _send_canary(ctx, after, title_url="https://api.anthropic.com", sid="s2")  # after the fix
        cmp = report.compare_data(store.load_canaries(), store.read_ledger())
        self.assertEqual(cmp["before"]["id"], before["id"])
        self.assertEqual(cmp["after"]["id"], after["id"])
        self.assertNotIn("iban", cmp["before"])
        px.command_handler("trace " + before["id"])
        page = px.build_report_page("en")
        self.assert_self_contained(page)
        self.assertIn('id="compare"', page)
        self.assertIn("Gone after the change: OpenRouter → Google model (US→US).", page)
        self.assertIn(before["name"], page)
        self.assertIn(after["name"], page)
        self.assertNotIn(before["iban"], page)
        self.assertNotIn(after["iban"], page)
        self.assertIn("Your canary reached <b>2 vendors</b> in <b>1 country</b> (US).", page)
        self.assertIn("<b>OpenRouter → Google model</b> got it although it is not your model vendor.", page)
        self.assertIn('class="aura"', page)  # pulsing hazard on the extra recipient
        de = px.build_report_page("de")
        self.assert_self_contained(de)
        self.assertIn("Nach der Änderung weg: OpenRouter → Google Modell (US→US).", de)
        self.assertIn("Deine Testperson hat <b>2 Anbieter</b> in <b>1 Land</b> (US) erreicht.", de)
        self.assertIsNone(re.search("[\u2013\u2014]", de))

    def test_single_canary_no_compare_and_green_verdict(self):
        ctx = setup()
        c = store.add_canary()
        _send_canary(ctx, c, title_url="https://api.anthropic.com")
        self.assertIsNone(report.compare_data(store.load_canaries(), store.read_ledger()))
        px.command_handler("trace")
        page = px.build_report_page("en")
        self.assert_self_contained(page)
        self.assertNotIn('id="compare"', page)
        self.assertIn("Every copy went to your model vendor <b>Anthropic</b>.", page)
        self.assertNotIn('class="aura"', page)
        self.assertIn("Contained", page)

    @staticmethod
    def _section(page, sid):
        start = page.index(f'id="{sid}"')
        return page[start:page.index("</section>", start)]

    @staticmethod
    def _hero(page):
        start = page.index('<section class="hero"')
        return page[start:page.index("</section>", start)]

    def _pair(self, trace_latest=True):
        ctx = setup()
        before = store.add_canary()
        _send_canary(ctx, before)  # title side request to OpenRouter: extra recipient
        time.sleep(1.1)
        after = store.add_canary()
        _send_canary(ctx, after, title_url="https://api.anthropic.com", sid="s2")
        px.command_handler("trace" if trace_latest else "trace " + before["id"])
        return before, after

    def test_flow_since_helper(self):
        c1, c2 = {"id": "a", "created": 100.0}, {"id": "b", "created": 200.0}
        cmp = {"before": {"id": "a"}, "after": {"id": "b"}}
        self.assertEqual(report.canary_flow_since(c2, cmp), 200.0)
        self.assertIsNone(report.canary_flow_since(c1, cmp))  # traced canary is not the 'after' side
        self.assertIsNone(report.canary_flow_since(c2, None))  # no before/after pair
        self.assertIsNone(report.canary_flow_since(None, cmp))
        self.assertIsNone(report.canary_flow_since({"id": "b", "created": "x"}, cmp))

    def test_scopes_after_fix_tell_one_story(self):
        before, after = self._pair()
        for lang, latest, since, carried, vendor1 in (
                ("en", "Latest canary only", "since ", "2 requests carried it", "<b>1</b>vendor<"),
                ("de", "Nur die neueste Testperson", "seit ", "2 Anfragen trugen sie", "<b>1</b>Anbieter<")):
            page = px.build_report_page(lang)
            self.assert_self_contained(page)
            hero, flow, cmp = self._hero(page), self._section(page, "flow"), self._section(page, "compare")
            # hero: the latest canary only, chips agree with the headline
            self.assertIn(latest, hero)
            self.assertIn(carried, hero.replace("<b>", "").replace("</b>", " "))
            self.assertIn(vendor1, hero)
            self.assertNotIn("OpenRouter", hero)
            self.assertNotIn("CN", hero)
            # flow: since the latest canary, no pre-fix route, canary name on the Hermes node, green legend only
            self.assertIn(since, flow)
            self.assertNotIn("OpenRouter", flow)
            self.assertIn(after["name"], flow)
            self.assertNotIn(before["name"], flow)
            self.assertNotIn('class="aura"', flow)
            self.assertNotIn(report.COL["red"] + '"></i>', flow)
            # the before/after card still shows the red pre-fix route
            self.assertIn("OpenRouter", cmp)
            self.assertIn('class="aura"', cmp)
            self.assertIsNone(re.search("[\u2013\u2014]", page))
        self.assertIn(".bar>div{height:100%;background:#8b8cff}", page)  # one colour, no gradient

    def test_window_flow_without_pair_has_no_canary_label(self):
        before, after = self._pair(trace_latest=False)  # traced canary is not the latest one
        page = px.build_report_page("en")
        flow = self._section(page, "flow")
        self.assertIn("last 20 turns, all requests", flow)
        self.assertIn("OpenRouter", flow)  # window-wide flow includes the pre-fix route
        self.assertNotIn(before["name"], flow)  # no canary name on a window-wide diagram
        self.assertNotIn(after["name"], flow)
        self.assertIn("Latest canary only", self._hero(page))

    def test_hero_without_canary_uses_window_chips(self):
        ctx = setup()
        msgs = [{"role": "user", "content": "hello"}]
        ctx.hooks["pre_api_request"](**main_kwargs(msgs, session_id="s1", turn_id="t1"))
        page = px.build_report_page("en")
        hero = self._hero(page)
        self.assertIn("last 20 turns, all requests", hero)
        self.assertIn("<b>1</b>request<", hero)
        self.assertIn("<b>1</b>vendor<", hero)
        self.assertNotIn("Latest canary only", hero)
        self.assertIn('id="check"', page)

    def test_empty_ledger_and_escaping(self):
        setup()
        page = px.build_report_page("en")
        self.assert_self_contained(page)
        self.assertIn("No outgoing requests recorded yet.", page)
        agg = {"requests": 1, "side_requests": 1, "types": {"email": 1}, "countries": ["unknown"],
               "destinations": [{"host": "<b>evil.example", "vendor": "<script>x</script>", "hq": "unknown",
                                 "local": False, "main": 0, "side": {"<i>task": 1}, "types": {"email": 1},
                                 "canary": [], "status": "red", "baseline": False, "watch": 0}]}
        page = report.build_html(lang="en", agg=agg, scope="s", check=None, trace=None, canary=None)
        self.assertNotIn("<script>x", page)
        self.assertNotIn("<b>evil", page)
        self.assertNotIn("<i>task", page)
        self.assertIn("&lt;script&gt;", page)

    def test_sankey_band_widths_follow_volume(self):
        flows = [{"task": "main", "host": "a", "n": 9, "canary": True},
                 {"task": "title_generation", "host": "b", "n": 1, "canary": False}]
        nodes = [{"host": "a", "vendor": "A", "hq": "US", "status": "green", "baseline": True, "types": {},
                  "canary": True},
                 {"host": "b", "vendor": "B", "hq": "CN", "status": "red", "baseline": False,
                  "types": {"email": 2}, "canary": False}]
        svg = report.sankey(flows, nodes, "en", uid="t")
        heights = [float(m) - float(n) for n, m in re.findall(
            r'd="M[\d.]+,([\d.]+) C[^"]*? L[\d.]+,[\d.]+ C[^"]*? [\d.]+,([\d.]+) Z"', svg)]
        self.assertEqual(len(heights), 4)  # two segments per flow
        self.assertGreater(max(heights), 5 * min(heights))
        self.assertIn("China", svg)
        self.assertEqual(svg.count('class="aura"'), 1)
        self.assertIn(report.COL["canary"], svg)


class DashboardTests(unittest.TestCase):
    """The dashboard tab: manifest, bundle and the backend route."""

    DASH = ROOT / "dashboard"

    def test_manifest_and_bundle(self):
        man = json.loads((self.DASH / "manifest.json").read_text())
        self.assertEqual(man["name"], "privacy-xray")
        self.assertTrue((self.DASH / man["entry"]).is_file())
        self.assertTrue((self.DASH / man["api"]).is_file())
        js = (self.DASH / man["entry"]).read_text()
        self.assertIn('REG.register("privacy-xray"', js)
        self.assertIn("/api/plugins/privacy-xray/report", js)
        self.assertIn('sandbox: ""', js)  # report runs without scripts, without same origin
        self.assertNotRegex(js, r"https?://")

    def test_backend_route(self):
        try:
            import fastapi  # noqa: F401
        except Exception:  # noqa: BLE001
            self.skipTest("fastapi not available")
        reset_data()
        write_config(BASE_CFG + "\nplugins:\n  entries:\n    privacy-xray:\n      settings:\n        language: de\n")
        spec = importlib.util.spec_from_file_location("px_dash_api_test", self.DASH / "plugin_api.py")
        assert spec is not None and spec.loader is not None
        api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api)
        try:
            self.assertTrue(any(getattr(r, "path", "") == "/report" for r in api.router.routes))
            res = api.render("")
            self.assertTrue(res["ok"])
            self.assertEqual(res["lang"], "de")  # read from the saved plugin settings, no plugin context
            self.assertIn("Datenfluss", res["html"])
            self.assertEqual(res["sig"], api.render("de")["sig"])
            self.assertEqual(api.render("en")["lang"], "en")
        finally:
            for k in [k for k in sys.modules if k.startswith(api._NAME)]:
                sys.modules.pop(k, None)


class TextTests(unittest.TestCase):
    def test_tool_first_sentence(self):
        desc = px.TOOL_SCHEMA["description"]
        try:
            from tools.tool_search_catalog import _short_desc
            short = _short_desc(desc)
        except Exception:  # noqa: BLE001
            short = desc.split(". ")[0] + "."
        self.assertLessEqual(len(short), 60, short)
        self.assertFalse(short.endswith("\u2026"), short)

    def test_no_dashes_in_german(self):
        bad = re.compile("[\u2013\u2014]")
        for key, entry in views.T.items():
            self.assertIsNone(bad.search(entry.get("de", "")), key)
        for entry in report.L10N["de"].values():
            self.assertIsNone(bad.search(entry))
        src = (ROOT / "audit.py").read_text()
        self.assertIsNone(bad.search(src))

    def test_german_output(self):
        setup(language="de")
        self.assertIn("Testperson", px.command_handler("canary"))
        self.assertIn("/xray check", px.command_handler("help"))

    def test_command_never_raises(self):
        setup()
        for arg in ("", "bogus", "map --turns", "map --turns x", "fix", "find", 'find "unterminated', "trace nope"):
            self.assertIsInstance(px.command_handler(arg, platform="cli"), str)

    def test_wrap_at_word_boundaries(self):
        bt = "\x60"
        line = ("\U0001F7E1 sessions.retention: If you want old chats deleted automatically, run it yourself: "
                f"{bt}hermes config set sessions.auto_prune true{bt}. Then Hermes deletes every chat older than 90 days.")
        out = views.wrap_text(line + "\n  short line", 60)
        rows = out.split("\n")
        self.assertGreater(len(rows), 2)
        for r in rows:
            self.assertLessEqual(views._cols(r), 60, r)
        self.assertEqual(" ".join(r.strip() for r in rows[:-1]), line)  # nothing lost, no word split
        self.assertIn(f"{bt}hermes config set sessions.auto_prune true{bt}", out)  # command kept whole
        self.assertTrue(rows[1].startswith("   ") and not rows[1].startswith("    "))  # hang under the dot
        second = views.wrap_text("     If this sentence is long enough it wraps here", 30).split("\n")[1]
        self.assertEqual(len(second) - len(second.lstrip()), 7)  # a short word is not mistaken for a marker
        self.assertEqual(rows[-1], "  short line")

    @unittest.skipUnless(HAVE_HERMES, "needs the Hermes config loader")
    def test_wrap_only_in_terminals(self):
        write_config("auxiliary:\n  title_generation:\n    provider: openrouter\n    model: deepseek/deepseek-v4.1-flash\n")
        setup(wrap_width=50)
        longest = lambda s: max(views._cols(r) for r in s.split("\n"))  # noqa: E731
        for surface in ("cli", "tui", "local"):
            out = px.command_handler("check", platform=surface)
            # command lines and backtick commands are never split (copy whole); everything else fits
            prose = "\n".join(r for r in out.split("\n")
                               if not r.lstrip().startswith(("fix: ", "hermes ", "\x60hermes ")))
            self.assertLessEqual(longest(prose), 50, [r for r in prose.split("\n") if views._cols(r) > 50])
            self.assertIn("fix: hermes config set", out)  # commands stay on one line
        self.assertGreater(longest(px.command_handler("check", platform="telegram")), 50)
        self.assertGreater(longest(px.command_handler("check", platform="desktop")), 50)
        write_config("{}\n")
        setup()


class PerformanceTests(unittest.TestCase):
    """Every regex and the whole request scan stay fast on hostile input at the size limit."""

    N = 1_000_000
    LIMIT = 1.0

    def inputs(self):
        n = self.N
        return {
            "digits": "1" * n, "spaced_digits": "1 " * (n // 2), "dashed_digits": "1-" * (n // 2),
            "letters": "a" * n, "upper": "A" * n, "at": "@" * n, "a_at": "a@" * (n // 2),
            "dots": "a." * (n // 2), "plus": "+1" * (n // 2), "plus_space": "+1 " * (n // 3),
            "de": "DE" * (n // 2), "de_digits": "DE12 " * (n // 5), "ip": "1." * (n // 2),
            "ip2": "255.255." * (n // 8), "mail_like": "a.b@c." * (n // 6), "spaces": " " * n,
            "newlines": "\n" * n, "mixed": "x@y.z 4111 +44 DE89 10.0.0.1 " * (n // 30),
        }

    def test_each_regex(self):
        for name, text in self.inputs().items():
            for det, rx, _ in detect._CHECKS:
                t0 = time.perf_counter()
                for _m in rx.finditer(text):
                    pass
                dt = time.perf_counter() - t0
                self.assertLess(dt, self.LIMIT, f"{det} on {name}: {dt:.2f}s")

    def test_detect_and_mask(self):
        for name, text in self.inputs().items():
            t0 = time.perf_counter()
            detect.detect(text, limit=self.N)
            detect.masked_snippet(text, 10, 20)
            dt = time.perf_counter() - t0
            self.assertLess(dt, self.LIMIT * 3, f"detect on {name}: {dt:.2f}s")

    def test_scan_request_history(self):
        sc = detect.Scanner()
        needles = detect.Needles([store.make_canary()], ["Projekt Falke"])
        hist = [{"role": "user" if i % 2 else "assistant", "content": f"message {i} " + "lorem ipsum " * 400}
                for i in range(300)]
        t0 = time.perf_counter()
        sc.scan_request(hist, "S" * 50000, needles, detect.DETECTORS)
        first = time.perf_counter() - t0
        t0 = time.perf_counter()
        sc.scan_request(hist + [{"role": "user", "content": "new"}], "S" * 50000, needles, detect.DETECTORS)
        second = time.perf_counter() - t0
        self.assertLess(first, 2.0)
        self.assertLess(second, first / 3 + 0.05, f"cache must make re-sends cheap ({first:.3f}s vs {second:.3f}s)")

    def test_guard_mask_speed(self):
        rx = detect.compile_masker(detect.Needles([store.make_canary()], ["a" * 5]).all_values())
        t0 = time.perf_counter()
        px.mask_request({"messages": [{"role": "user", "content": "a" * self.N}]}, rx)
        self.assertLess(time.perf_counter() - t0, self.LIMIT)


# --------------------------------------------------------------------------- review 1 fixes


class BudgetTests(unittest.TestCase):
    """P0.1: long histories. Newest message first, no cached truncated result, incomplete flag."""

    def setUp(self):
        reset_data()

    def test_newest_message_is_scanned_and_not_poisoned(self):
        sc = detect.Scanner()
        n = detect.Needles()
        clean = "lorem ipsum dolor sit amet " * 37000  # about 1 MB per message
        hist = [{"role": ["user", "assistant"][i % 2], "content": clean + str(i)} for i in range(4)]
        new = {"role": "user", "content": "Please mail john.doe@acme-corp.com, IBAN " + FAKE_IBAN}
        r1 = sc.scan_request(hist + [new], None, n, detect.DETECTORS)
        self.assertEqual(r1["types"].get("email"), 1, "the newest message gets the budget first")
        self.assertEqual(r1["types"].get("iban"), 1)
        self.assertTrue(r1["truncated"], "older history did not fit and is reported")
        # The cut old messages must not be cached as 'empty': alone they are scanned again, fully.
        old = {"role": "user", "content": clean + "3 reach me at old.mail@acme-corp.com"}
        r2 = sc.scan_request(hist[:2] + [old, new], None, n, detect.DETECTORS)
        r3 = sc.scan_request([old], None, n, detect.DETECTORS)
        self.assertEqual(r3["types"].get("email"), 1)
        self.assertFalse(r3["truncated"])
        self.assertIsInstance(r2["truncated"], bool)

    def test_incomplete_flag_reaches_ledger_map_and_report(self):
        ctx = setup()
        big = "lorem ipsum " * 120000  # 1.44 MB in one message: over the per-message cap
        ctx.hooks["pre_api_request"](**main_kwargs([{"role": "user", "content": big + " a@acme-corp.com"}]))
        rec = store.read_ledger()[-1]
        self.assertTrue(rec.get("incomplete"))
        self.assertIn("Count incomplete: 1 request", px.command_handler("map"))
        self.assertIn("Count incomplete", px.build_report_page("en"))
        self.assertIn("Zählung unvollständig", px.build_report_page("de"))


@unittest.skipUnless(HAVE_HERMES, "needs the Hermes Python")
class RetentionTests(unittest.TestCase):
    """P0.2: the retention advice is never applied by the plugin."""

    def setUp(self):
        reset_data()
        write_config(BASE_CFG)

    def test_retention_never_applied(self):
        setup()
        before = (HOME / "config.yaml").read_bytes()
        for args in ("fix sessions.retention", "fix sessions.retention --yes", "fix sessions.retention -y"):
            out = px.command_handler(args, platform="cli")
            self.assertIn("no automatic fix", out)
            self.assertIn("hermes config set sessions.auto_prune true", out)
            self.assertIn("DELETES every chat older than 90 days", out)
            self.assertNotIn("Applied", out)
        self.assertEqual((HOME / "config.yaml").read_bytes(), before, "config must stay byte-identical")
        f = next(x for x in audit.check()["findings"] if x["id"] == "sessions.retention")
        self.assertEqual(f["fix"]["sets"], [])
        de = px.command_handler("fix sessions.retention --yes", platform="cli")
        self.assertNotIn("Applied", de)

    def test_readme_does_not_claim_nothing_is_deleted(self):
        readme = (ROOT / "README.md").read_text()
        self.assertNotIn("nothing is ever deleted", readme)
        self.assertIn("never applied by the plugin", readme)


AGG_CFG = """
model:
  provider: openrouter
  default: anthropic/claude-sonnet-5
auxiliary:
  title_generation:
    provider: openrouter
    model: deepseek/deepseek-v4-flash
  compression:
    provider: openrouter
    model: anthropic/claude-haiku-5
  vision:
    provider: auto
sessions:
  auto_prune: false
"""


@unittest.skipUnless(HAVE_HERMES, "needs the Hermes Python")
class AggregatorTests(unittest.TestCase):
    """P0.3: behind an aggregator the model vendor decides whether a side request is extra."""

    def setUp(self):
        reset_data()
        write_config(AGG_CFG)

    def find(self, res, fid):
        return next(f for f in res["findings"] if f["id"] == fid)

    def test_model_vendor(self):
        self.assertEqual(vendors.model_vendor("deepseek/deepseek-v4-flash"), ("DeepSeek", "CN"))
        self.assertEqual(vendors.model_vendor("anthropic/claude-sonnet-5:beta"), ("Anthropic", "US"))
        self.assertEqual(vendors.model_vendor("claude-sonnet-5"), ("Anthropic", "US"))
        self.assertEqual(vendors.model_vendor("openrouter/auto"), ("", ""))
        self.assertEqual(vendors.model_vendor("sao10k/l3-euryale"), ("sao10k", "unknown"))
        for host in ("openrouter.ai", "ai-gateway.vercel.sh", "router.huggingface.co", "api.novita.ai"):
            self.assertEqual(vendors.classify(host)["kind"], "router", host)

    def test_audit(self):
        res = audit.check()
        t = self.find(res, "aux.title_generation")
        self.assertEqual(t["severity"], "red", "OpenRouter with a DeepSeek model is an extra recipient")
        self.assertIn("OpenRouter → DeepSeek model", t["why"]["en"])
        self.assertIn("not visible to privacy-xray", t["why"]["en"])
        self.assertEqual(self.find(res, "aux.compression")["severity"], "green", "same aggregator, same model vendor")
        self.assertEqual(self.find(res, "aux.vision")["severity"], "green")
        self.assertIn("OpenRouter → Anthropic model", self.find(res, "main.model")["why"]["en"])

    def test_prefer_fast_model_is_amber(self):
        write_config(AGG_CFG.replace("  vision:\n    provider: auto",
                                     "  vision:\n    provider: auto").replace(
            "  title_generation:\n    provider: openrouter\n    model: deepseek/deepseek-v4-flash",
            "  title_generation:\n    provider: auto\n    prefer_fast_model: true"))
        t = self.find(audit.check(), "aux.title_generation")
        self.assertEqual(t["severity"], "amber")
        self.assertEqual(audit.fix_commands(t), ["hermes config set auxiliary.title_generation.prefer_fast_model false"])

    def test_map_trace_report(self):
        ctx = setup()
        c = store.add_canary()
        msgs = [{"role": "user", "content": f"Write to {c['name']} <{c['email']}>"}]
        url = "https://openrouter.ai/api/v1"
        ctx.hooks["pre_api_request"](**main_kwargs(msgs, provider="openrouter", model="anthropic/claude-sonnet-5",
                                                   base_url=url))
        ctx.hooks["pre_auxiliary_call"](aux_task="title_generation", provider="openrouter",
                                        model="deepseek/deepseek-v4-flash", base_url=url, request_messages=msgs,
                                        session_id="s1", turn_id="t1")
        ctx.hooks["pre_auxiliary_call"](aux_task="compression", provider="openrouter",
                                        model="anthropic/claude-haiku-5", base_url=url, request_messages=msgs,
                                        session_id="s1", turn_id="t1")
        recs = store.read_ledger()
        self.assertEqual(recs[1]["mvendor"], "DeepSeek")
        self.assertEqual(recs[1]["mhq"], "CN")
        mp = px.command_handler("map")
        self.assertRegex(mp, "\U0001F534 openrouter.ai  OpenRouter → DeepSeek model \\[US / CN\\]")
        self.assertRegex(mp, "\U0001F7E2 openrouter.ai  OpenRouter → Anthropic model \\[US / US\\]")
        tr = px.command_handler("trace")
        self.assertRegex(tr, "\U0001F534 side request: title_generation → openrouter.ai · OpenRouter → DeepSeek model")
        self.assertRegex(tr, "\U0001F7E2 side request: compression → openrouter.ai · OpenRouter → Anthropic model")
        self.assertRegex(tr, "\U0001F7E2 main request")
        page = px.build_report_page("en")
        self.assertIn("<b>OpenRouter → DeepSeek model</b> got it although it is not your model vendor.", page)
        self.assertIn("(CN, US)", page, "model vendor countries count")


class GuardShapeTests(unittest.TestCase):
    """Guard: only human-readable text is masked, as whole words; structure stays byte-identical."""

    def setUp(self):
        reset_data()
        self.ctx = setup(guard=True, watch_terms=["Tim", "web", "user"])
        self.c = store.add_canary()
        self.mw = self.ctx.middleware["llm_request"]

    def run_mw(self, req):
        import copy
        orig = copy.deepcopy(req)
        out = self.mw(request=req, api_request_id="rq")
        self.assertEqual(req, orig, "original request must not be mutated")
        return out["request"] if out else req

    def test_chat_completions_tool_calls(self):
        c = self.c
        req = {"model": "m", "messages": [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": f"Remind {c['name']} please, Tim knows. timestamp, optimized, webhook."},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "call_web1", "type": "function",
                "function": {"name": "web_search", "arguments": json.dumps({"query": c["email"]})}}]},
            {"role": "tool", "tool_call_id": "call_web1", "name": "web_search", "content": f"found {c['email']} on the web"}],
            "tools": [{"type": "function", "function": {"name": "web_search", "parameters": {}}}]}
        new = self.run_mw(req)
        m = new["messages"]
        self.assertEqual(m[0], req["messages"][0])
        self.assertNotIn(c["name"], m[1]["content"])
        self.assertIn("timestamp, optimized, webhook", m[1]["content"], "no partial words")
        self.assertIn("[masked by privacy-xray] knows", m[1]["content"])
        self.assertEqual(m[2], req["messages"][2], "tool_calls: names, ids and arguments untouched")
        self.assertEqual(m[3]["tool_call_id"], "call_web1")
        self.assertEqual(m[3]["name"], "web_search")
        self.assertEqual(m[3]["content"], "found [masked by privacy-xray] on the [masked by privacy-xray]")
        self.assertEqual(new["tools"], req["tools"])
        self.assertEqual([x["role"] for x in m], ["system", "user", "assistant", "tool"], "role 'user' never masked")

    def test_anthropic_thinking_and_tool_use(self):
        c = self.c
        req = {"model": "claude", "system": [{"type": "text", "text": f"Known: {c['email']}",
                                              "cache_control": {"type": "ephemeral"}}],
               "messages": [
                   {"role": "user", "content": [{"type": "text", "text": f"Mail {c['email']}"}]},
                   {"role": "assistant", "content": [
                       {"type": "thinking", "thinking": f"The user wants to mail {c['name']}.", "signature": "EqQBCkgIARAB"},
                       {"type": "redacted_thinking", "data": "abc"},
                       {"type": "text", "text": f"Sure, {c['name']}."},
                       {"type": "tool_use", "id": "toolu_01", "name": "web_search", "input": {"query": c["name"]}}]},
                   {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_01",
                                                 "content": [{"type": "text", "text": f"{c['name']} found"}]},
                                                {"type": "image", "source": {"type": "base64", "data": c["name"]}}]}]}
        new = self.run_mw(req)
        a = new["messages"][1]["content"]
        self.assertEqual(a[0], req["messages"][1]["content"][0], "signed thinking block untouched")
        self.assertEqual(a[1], req["messages"][1]["content"][1])
        self.assertEqual(a[2]["text"], "Sure, [masked by privacy-xray].")
        self.assertEqual(a[3], req["messages"][1]["content"][3], "tool_use untouched")
        tr = new["messages"][2]["content"]
        self.assertEqual(tr[0]["tool_use_id"], "toolu_01")
        self.assertEqual(tr[0]["content"][0]["text"], "[masked by privacy-xray] found")
        self.assertEqual(tr[1], req["messages"][2]["content"][1], "images untouched")
        self.assertEqual(new["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertNotIn(c["email"], new["system"][0]["text"])

    def test_responses_input(self):
        c = self.c
        req = {"model": "gpt", "instructions": f"Known user: {c['name']}", "input": [
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": f"Pay {c['name']}"}]},
            {"type": "reasoning", "id": "rs_1", "encrypted_content": "xyz", "summary": [{"type": "summary_text",
                                                                                      "text": c["name"]}]},
            {"type": "function_call", "call_id": "call_1", "name": "web_search", "arguments": json.dumps({"q": c["name"]})},
            {"type": "function_call_output", "call_id": "call_1", "output": f"{c['name']} lives here"}]}
        new = self.run_mw(req)
        i = new["input"]
        self.assertNotIn(c["name"], new["instructions"])
        self.assertEqual(i[0]["content"][0]["text"], "Pay [masked by privacy-xray]")
        self.assertEqual(i[1], req["input"][1], "reasoning with encrypted content untouched")
        self.assertEqual(i[2], req["input"][2], "function_call untouched")
        self.assertEqual(i[3]["call_id"], "call_1")
        self.assertEqual(i[3]["output"], "[masked by privacy-xray] lives here")

    def test_word_boundaries_in_counting(self):
        n = detect.Needles([], ["Tim"])
        sc = detect.Scanner()
        self.assertFalse(sc.scan_request([{"role": "user", "content": "timestamp optimized"}], None, n,
                                         detect.DETECTORS)["watch_fields"])
        self.assertEqual(sc.scan_request([{"role": "user", "content": "ask Tim."}], None, n,
                                         detect.DETECTORS)["watch_fields"], ["user"])
        self.assertTrue(detect.contains_word("mail +44 7700 900123.", "+44 7700 900123"))
        self.assertFalse(detect.contains_word("xholtingham", "holtingham"))


@unittest.skipUnless(HAVE_HERMES, "needs the Hermes Python")
class WebAuditTests(unittest.TestCase):
    """Web search: fallback backends (keyless rescue) and web.extract_backend."""

    def setUp(self):
        reset_data()
        os.environ["SEARXNG_URL"] = "http://127.0.0.1:8080"

    def tearDown(self):
        os.environ.pop("SEARXNG_URL", None)

    def findings(self, web_yaml):
        write_config(BASE_CFG + "web:\n" + web_yaml)
        return {f["id"]: f for f in audit.check()["findings"]}

    def test_searxng_green_only_without_rescue(self):
        f = self.findings("  search_backend: searxng\n  extract_backend: firecrawl\n")
        self.assertEqual(f["web.search"]["severity"], "amber", "keyless rescue is on by default")
        self.assertIn("Exa", f["web.search"]["why"]["en"])
        self.assertEqual(audit.fix_commands(f["web.rescue"]), ["hermes config set web.keyless_rescue false"])
        self.assertIn("Firecrawl (US)", f["web.extract"]["why"]["en"])
        f = self.findings("  search_backend: searxng\n  keyless_rescue: false\n")
        self.assertEqual(f["web.search"]["severity"], "green")
        self.assertNotIn("web.rescue", f)
        f = self.findings("  search_backend: searxng\n  keyless_fallback: false\n")
        self.assertEqual(f["web.search"]["severity"], "green", "rescue is off when the keyless tier is off")

    def test_ddgs_and_defaults(self):
        f = self.findings("  backend: ddgs\n")
        self.assertIn("meta search: DuckDuckGo, Bing, Brave", f["web.search"]["why"]["en"])
        self.assertIn("web.rescue", f)
        f = self.findings("  backend: ''\n")
        self.assertIn("keyless free tier", f["web.search"]["why"]["en"])
        self.assertIn("keyless free tier", f["web.extract"]["why"]["en"])


@unittest.skipUnless(HAVE_HERMES, "needs hermes_state")
class StoreSearchTests(unittest.TestCase):
    """FTS candidates + LIKE confirmation; a missing term is complete, not 'incomplete'."""

    def setUp(self):
        reset_data()
        for p in ("state.db", "state.db-wal", "state.db-shm"):
            (HOME / p).unlink(missing_ok=True)
        for d in ("logs", "sessions"):
            shutil.rmtree(HOME / d, ignore_errors=True)

    def test_missing_term_is_complete_and_fast(self):
        rows = [("s1", "user", f"message {i} about invoices") for i in range(300)]
        rows += [("s1", "tool", "y" * 20000 + f" tail {i}") for i in range(50)]
        make_state_db(HOME, rows)
        t0 = time.perf_counter()
        res = scan.search_all(HOME, ["Zorbulax Quentavio"], store.data_dir(), seconds=10)
        self.assertLess(time.perf_counter() - t0, 3.0)
        self.assertFalse(res["partial"], res.get("partial_reasons"))
        self.assertEqual(res["places"], [])
        self.assertIn("tool_tail", res["coverage"])
        deep = scan.search_all(HOME, ["tail 7"], store.data_dir(), seconds=10, deep=True)
        self.assertEqual(deep["state_db"]["places"]["messages"]["count"], 1)
        self.assertFalse(deep["partial"])

    def test_large_file_partial_listed_and_access_report(self):
        setup()
        (HOME / "logs").mkdir()
        with open(HOME / "logs" / "big.log", "wb") as fh:
            fh.write(b"a" * (3 << 20))
            fh.write(b"NEEDLEZ at the end\n")
        files = scan.search_files(HOME, ["NEEDLEZ"], store.data_dir(), max_file_bytes=1 << 20)
        logs = next(e for e in files if e["store"] == "logs")
        self.assertEqual(logs["count"], 1, "the newest part (end) of a large file is read")
        self.assertTrue(logs["partial"])
        self.assertEqual(logs["partial_files"], [{"path": "logs/big.log", "reason": "size"}])
        orig = scan.search_files
        try:
            scan.search_files = lambda *a, **k: orig(*a, **{**k, "max_file_bytes": 1 << 20})
            out = px.command_handler('find "NEEDLEZ" --export', platform="cli")
        finally:
            scan.search_files = orig
        self.assertIn("Search incomplete", out)
        self.assertIn("logs/big.log", out)
        md = sorted(store.reports_dir().glob("access-*.md"))[-1].read_text()
        self.assertIn("- Search complete: no (only partly read: logs/big.log", md)
        js = json.loads(sorted(store.reports_dir().glob("access-*.json"))[-1].read_text())
        self.assertFalse(js["complete"])
        self.assertEqual(js["partial_files"][0]["path"], "logs/big.log")

    def test_uri_special_characters_stay_read_only(self):
        for name in ("we#ird", "q?mode=rwc&x"):
            h = HOME / "uri" / name
            h.mkdir(parents=True, exist_ok=True)
            c = sqlite3.connect(h / "state.db")
            c.execute("create table messages(id integer primary key, role, session_id, content, tool_calls, timestamp)")
            c.execute("create table sessions(id, title)")
            c.commit()
            c.close()
            before = sorted(os.listdir(HOME / "uri"))
            r = scan.search_state_db(h, ["abc"], seconds=2)
            self.assertNotIn("error", r)
            self.assertEqual(sorted(os.listdir(HOME / "uri")), before, "no new database file next to it")
        shutil.rmtree(HOME / "uri", ignore_errors=True)


class CardPhoneIpTests(unittest.TestCase):
    def test_german_mobiles_are_never_cards(self):
        import random
        rnd = random.Random(49)
        formats = ("+49 {p} {r}", "+49{p}{r}", "+49 {p}-{r}", "+49 ({p}) {r}", "+49-{p}-{r}", "+49 {p} {r1} {r2}")
        texts = []
        for _ in range(1000):
            p = rnd.choice(["151", "152", "157", "159", "160", "162", "163", "170", "171", "172", "173", "174",
                            "175", "176", "177", "178", "179", "1511", "1520", "1590"])
            r = "".join(str(rnd.randrange(10)) for _ in range(rnd.choice((7, 8))))
            texts.append(rnd.choice(formats).format(p=p, r=r, r1=r[:4], r2=r[4:]))
        cards = sum(detect.detect(t).get("card", 0) for t in texts)
        phones = sum(detect.detect(t).get("phone", 0) for t in texts)
        self.assertEqual(cards, 0)
        self.assertGreater(phones, 700, "most formats are phone numbers (the bracket form is not matched)")

    def test_cards_still_found(self):
        for num in ("4111 1111 1111 1111", "5500-0000-0000-0004", "2223 0000 4841 0010", "3782 822463 10005",
                    "6011 1111 1111 1117", "3530 1113 3330 0000"):
            self.assertEqual(detect.detect(f"card {num} exp").get("card"), 1, num)
        for num in ("1234 5678 9012 3456", "9999 9999 9999 9995", "4111 1111 1111 1112"):
            self.assertNotIn("card", detect.detect(f"card {num}"), num)

    def test_ipv4_public_only(self):
        for ip in ("127.0.0.1", "10.0.0.1", "192.168.1.1", "172.16.5.4", "169.254.1.1", "100.64.0.1",
                   "100.127.255.254", "224.0.0.251", "240.0.0.1", "0.0.0.0", "255.255.255.255", "192.0.2.10",
                   "198.51.100.7", "203.0.113.9"):
            self.assertNotIn("ipv4", detect.detect(f"host {ip} up"), ip)
        for text in ("chromium v1.2.3.4", "x1.2.3.4", "1.2.3.4.5", "OID 1.3.6.1.4.1.311", ".8.8.8.8"):
            self.assertNotIn("ipv4", detect.detect(text), text)
        for text in ("dns 8.8.8.8", "ssh root@9.9.9.9", "(1.1.1.1)", "ip=93.184.216.34,"):
            self.assertEqual(detect.detect(text).get("ipv4"), 1, text)

    def test_role_mailboxes(self):
        self.assertNotIn("email", detect.detect("git@github.com and noreply@example.com"))
        self.assertEqual(detect.detect("jane@acme-corp.com").get("email"), 1)


class PermissionTests(unittest.TestCase):
    def setUp(self):
        reset_data()

    def mode(self, p):
        return oct(p.stat().st_mode & 0o777)

    def test_dirs_700_files_600(self):
        old = os.umask(0o022)
        try:
            ctx = setup()
            store.add_canary()
            ctx.hooks["pre_api_request"](**main_kwargs([{"role": "user", "content": "x"}]))
            px.command_handler("check")
            for i in range(60):
                store.append_ledger({"ts": time.time(), "pad": "x" * 200}, max_bytes=5000)
            write_config(BASE_CFG)
            px.command_handler("report")
            px.command_handler('find "nothing-here" --export', platform="cli")
        finally:
            os.umask(old)
        d = store.data_dir()
        self.assertEqual(self.mode(d), "0o700")
        self.assertEqual(self.mode(store.reports_dir()), "0o700")
        files = [p for p in d.rglob("*") if p.is_file()]
        names = {p.name for p in files}
        self.assertIn("ledger.1.jsonl", names)
        self.assertIn("canaries.json", names)
        self.assertTrue(any(n.startswith("leak-map-") for n in names))
        self.assertTrue(any(n.startswith("access-") and n.endswith(".md") for n in names))
        for p in files:
            self.assertEqual(self.mode(p), "0o600", p.name)

    def test_existing_wide_dir_is_narrowed(self):
        d = store.data_dir()
        os.chmod(d, 0o755)
        self.assertEqual(self.mode(store.data_dir()), "0o700")


class ArgumentTests(unittest.TestCase):
    def setUp(self):
        reset_data()

    def test_friendly_usage_messages(self):
        setup()
        bad = {"map --turns": "--turns needs a whole number", "map --turns abc": "--turns needs a whole number",
               "map --turns -5": "--turns needs a whole number", "map --turns 0": "--turns needs a whole number",
               "map --hours x": "--hours needs a number", "map --hours 1e308": "--hours needs a number",
               "map --hours -1": "--hours needs a number", "map --hours nan": "--hours needs a number",
               "map --turns 2 --hours 3": "Use one of", "map --bogus": "Unknown option '--bogus'",
               "check --nope": "Unknown option", "bogus": "Unknown command 'bogus'"}
        for args, want in bad.items():
            out = px.command_handler(args, platform="cli")
            self.assertIn(want, out, args)
            for raw in ("Error:", "Traceback", "ValueError", "IndexError", "did not work"):
                self.assertNotIn(raw, out, args)
        setup(language="de")
        self.assertIn("--turns braucht eine ganze Zahl", px.command_handler("map --turns abc"))
        self.assertIn("--hours braucht eine Stundenzahl", px.command_handler("map --hours x"))
        self.assertIn("Unbekannter Befehl 'bogus'", px.command_handler("bogus"))

    def test_trace_unknown_id_lists_ids(self):
        setup()
        a, b = store.add_canary(), store.add_canary()
        out = px.command_handler("trace cnope")
        self.assertIn("No canary with the id 'cnope'", out)
        self.assertIn(a["id"], out)
        self.assertIn(b["id"], out)

    def test_help_and_quotes(self):
        setup()
        h = px.command_handler("help")
        for part in ("trace [canary-id]", "check [--all]", "report [--session]", "--deep"):
            self.assertIn(part, h)
        self.assertEqual(px.do_find("en", '"ab')[1].get("error"), "query too short")

    def test_retry_count_garbage_still_records(self):
        ctx = setup()
        ctx.hooks["pre_api_request"](**main_kwargs([{"role": "user", "content": "x"}], retry_count="two"))
        self.assertEqual(store.read_ledger()[-1]["retry"], 0)


@unittest.skipUnless(HAVE_HERMES, "needs the Hermes Python")
class GatewayAccessTests(unittest.TestCase):
    """fix --yes and find: local surfaces only, unless allow_sensitive_on_gateways."""

    def setUp(self):
        reset_data()
        write_config(BASE_CFG)

    def invoke(self, args, **context):
        from hermes_cli.plugin_command_dispatch import invoke_plugin_command
        ctx_kw = {"source": None, "session_id": "s1", "session_key": "k"}
        ctx_kw.update(context)
        return invoke_plugin_command(px.command_handler, args, **ctx_kw)

    def test_refused_on_messaging_and_unknown(self):
        setup()
        for plat in ("telegram", "discord", "slack", "whatsapp", "signal", "api_server", "", None):
            before = (HOME / "config.yaml").read_bytes()
            out = self.invoke("fix aux.title_generation --yes", platform=plat)
            self.assertIn("runs only on this machine", out, plat)
            self.assertEqual((HOME / "config.yaml").read_bytes(), before, plat)
            self.assertIn("runs only on this machine", self.invoke('find "Ilse Vintrell"', platform=plat), plat)
            self.assertIn("This runs:", self.invoke("fix aux.title_generation", platform=plat), "showing is fine")
        self.assertIn("runs only on this machine", px.command_handler("find someone"), "no platform: refuse")

    def test_allowed_locally_and_by_setting(self):
        setup()
        for plat in ("cli", "tui", "desktop", "dashboard", "local"):
            self.assertNotIn("runs only on this machine", self.invoke('find "nobody here"', platform=plat), plat)
        self.assertIn("now green", self.invoke("fix aux.title_generation --yes", platform="cli"))
        write_config(BASE_CFG)
        setup(allow_sensitive_on_gateways=True)
        self.assertIn("now green", self.invoke("fix aux.title_generation --yes", platform="telegram"))

    def test_tool_find_follows_the_surface(self):
        schema, handler = setup(surface="telegram").tools["privacy_xray"]
        res = json.loads(handler({"action": "find", "query": "Ilse Vintrell"}))
        self.assertFalse(res["ok"])
        self.assertEqual(res["error_type"], "not_allowed_here")
        schema, handler = setup(surface="cli").tools["privacy_xray"]
        self.assertTrue(json.loads(handler({"action": "find", "query": "Ilse Vintrell"}))["ok"])


@unittest.skipUnless(HAVE_HERMES, "needs the Hermes Python")
class SmallFixTests(unittest.TestCase):
    """P2 items that were cheap: vendor names, fallback chains, rollback, canary names."""

    def setUp(self):
        reset_data()

    def test_vendor_names(self):
        for host, vendor, hq in (("api.kimi.com", "Moonshot AI", "CN"), ("api.stepfun.ai", "StepFun", "CN"),
                                 ("integrate.api.nvidia.com", "NVIDIA", "US"), ("ollama.com", "Ollama", "US"),
                                 ("api.upstage.ai", "Upstage", "KR"), ("portal.qwen.ai", "Alibaba Cloud (Qwen)", "CN")):
            info = vendors.classify(host)
            self.assertEqual((info["vendor"], info["hq"]), (vendor, hq), host)
        write_config(BASE_CFG + "tts:\n  provider: edge\nstt:\n  provider: elevenlabs\n")
        f = {x["id"]: x for x in audit.check()["findings"]}
        self.assertIn("Microsoft (Edge TTS, US)", f["voice.tts"]["why"]["en"])
        self.assertIn("ElevenLabs (US)", f["voice.stt"]["why"]["en"])
        self.assertIn("faster-whisper", f["voice.stt"]["fix"]["consequence"]["en"])

    def test_aux_fallback_chain(self):
        write_config(BASE_CFG.replace("  compression:\n    provider: auto",
                                      "  compression:\n    provider: auto\n    fallback_chain:\n"
                                      "      - provider: deepseek\n        model: deepseek-v4-flash"))
        f = {x["id"]: x for x in audit.check()["findings"]}
        self.assertEqual(f["aux.compression.fallback.0"]["severity"], "amber")
        self.assertIn("DeepSeek", f["aux.compression.fallback.0"]["why"]["en"])

    def test_apply_sets_rolls_back(self):
        write_config(BASE_CFG)
        import hermes_cli.config as hc
        real = hc.set_config_value
        calls = []

        def flaky(key, value):
            calls.append((key, value))
            if key == "auxiliary.title_generation.model" and value == "":
                raise SystemExit(1)
            return real(key, value)
        hc.set_config_value = flaky
        try:
            ok, log = audit.apply_sets([["auxiliary.title_generation.provider", "auto"],
                                        ["auxiliary.title_generation.model", ""]])
        finally:
            hc.set_config_value = real
        self.assertFalse(ok)
        self.assertIn("Rolled back", log)
        self.assertEqual(calls[-1], ("auxiliary.title_generation.provider", "openrouter"))
        self.assertIn("provider: openrouter", (HOME / "config.yaml").read_text())

    def test_canary_surnames_are_not_real_names(self):
        for _ in range(400):
            c = store.make_canary()
            self.assertNotIn(c["name"].split(" ")[1].lower(), store._REAL_SURNAMES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
