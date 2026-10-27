"""Offline tests for writing-guard. No network, no model.

Run:  python -m unittest discover -s tests -v      (from the plugin folder; Python 3.11+)
"""
from __future__ import annotations

import atexit
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path(tempfile.mkdtemp(prefix="writing-guard-test-"))
atexit.register(shutil.rmtree, HOME, True)
os.environ["HERMES_HOME"] = str(HOME)

_spec = importlib.util.spec_from_file_location("writing_guard_plugin", ROOT / "__init__.py",
                                               submodule_search_locations=[str(ROOT)])
wg = importlib.util.module_from_spec(_spec)
sys.modules["writing_guard_plugin"] = wg
_spec.loader.exec_module(wg)
from writing_guard_plugin import guard  # noqa: E402

DASH = "\u2013"   # en dash
EM = "\u2014"     # em dash


class FakeCtx:
    def __init__(self, settings=None):
        self.settings = dict(settings or {})
        self.hooks, self.tools, self.commands, self.skills = {}, {}, {}, {}

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_hook(self, name, fn):
        self.hooks[name] = fn

    def register_tool(self, name, toolset, schema, handler, **kw):
        self.tools[name] = (schema, handler)

    def register_command(self, name, handler, description="", args_hint=""):
        self.commands[name] = handler

    def register_skill(self, name, path, description=""):
        self.skills[name] = (Path(path), description)


def setup(**settings) -> FakeCtx:
    ctx = FakeCtx(settings)
    wg.register(ctx)
    return ctx


def run_hook(ctx, text, session_id="s1", platform="cli"):
    return ctx.hooks["transform_llm_output"](response_text=text, session_id=session_id,
                                             model="m", platform=platform, turn_id="t")


def fixed(text, style="comma"):
    return guard.check(text, fix=True, dash_style=style).text


class DashRules(unittest.TestCase):
    def test_spaced_dash_between_words(self):
        self.assertEqual(fixed(f"Das Plugin {DASH} gebaut an einem Tag {DASH} läuft."),
                         "Das Plugin, gebaut an einem Tag, läuft.")

    def test_unspaced_em_dash(self):
        self.assertEqual(fixed(f"The plugin{EM}built in a day{EM}works."),
                         "The plugin, built in a day, works.")

    def test_ranges_become_hyphens(self):
        self.assertEqual(fixed(f"Mo{DASH}Fr 9{DASH}17 Uhr, Seiten 12 {DASH} 14, Berlin{DASH}Hamburg"),
                         "Mo-Fr 9-17 Uhr, Seiten 12-14, Berlin-Hamburg")

    def test_bullets_and_table_cells(self):
        self.assertEqual(fixed(f"{DASH} eins\n  {EM} zwei\n| A | {DASH} |"),
                         "- eins\n  - zwei\n| A | - |")

    def test_line_end_punctuation_and_parenthesis(self):
        self.assertEqual(fixed(f"Wir haben {DASH} wie besprochen {DASH}, das gemacht. ({DASH} Notiz)\nEnde {DASH}"),
                         "Wir haben, wie besprochen, das gemacht. (Notiz)\nEnde")

    def test_dash_after_punctuation_is_dropped(self):
        self.assertEqual(fixed(f"Fertig. {DASH} Weiter geht es."), "Fertig. Weiter geht es.")

    def test_hyphen_style(self):
        self.assertEqual(fixed(f"Gut {DASH} sehr gut.", style="hyphen"), "Gut - sehr gut.")

    def test_all_dash_characters(self):
        for ch in guard.DASHES:
            out = fixed(f"a {ch} b")
            self.assertEqual(guard.count_dashes(out), 0, ch)

    def test_no_dash_no_change(self):
        rep = guard.check("Ganz normaler Satz - mit Bindestrich.", fix=True)
        self.assertIsNone(rep.text)
        self.assertEqual(rep.dashes_fixed, 0)


class Protected(unittest.TestCase):
    TEXT = (f"Hier `a {DASH} b` und https://x.de/a{DASH}b sowie [Link](docs/a{DASH}b.md)\n"
            f"```\necho 'x {EM} y'\n```\n"
            f"> Zitat {DASH} bleibt\nMEDIA:/tmp/a{DASH}b.png\nText {DASH} weg")

    def test_protected_spans_untouched(self):
        out = fixed(self.TEXT)
        for keep in (f"`a {DASH} b`", f"https://x.de/a{DASH}b", f"(docs/a{DASH}b.md)", f"echo 'x {EM} y'",
                     f"> Zitat {DASH} bleibt", f"MEDIA:/tmp/a{DASH}b.png"):
            self.assertIn(keep, out)
        self.assertIn("Text, weg", out)

    def test_protected_spans_not_counted(self):
        self.assertEqual(guard.check(self.TEXT).dashes, 1)

    def test_quotes_counted_when_not_skipped(self):
        self.assertEqual(guard.check(self.TEXT, skip_quotes=False).dashes, 2)

    def test_unclosed_fence_protects_rest(self):
        self.assertEqual(guard.check(f"```\na {DASH} b\nc {DASH} d").dashes, 0)

    def test_tilde_fence(self):
        self.assertEqual(guard.check(f"~~~\na {DASH} b\n~~~\nc {DASH} d").dashes, 1)


class Phrases(unittest.TestCase):
    def ids(self, text, **kw):
        return {p.id for p in guard.find_phrases(text, **kw)}

    def test_german(self):
        ids = self.ids("Es ist wichtig zu beachten, dass das nahtlos läuft. Ich hoffe, das hilft!")
        self.assertTrue({"de.wichtig_zu_beachten", "de.nahtlos", "de.hoffe_hilft"} <= ids)

    def test_english(self):
        ids = self.ids("Great question! Let's dive in. It's important to note that we delve into it.")
        self.assertTrue({"en.great_question", "en.dive_in", "en.important_to_note", "en.delve"} <= ids)

    def test_counts_repeats(self):
        hits = guard.find_phrases("seamless here, seamless there")
        self.assertEqual(hits[0].count, 2)

    def test_ignore_by_id_and_text(self):
        self.assertEqual(self.ids("This is seamless.", ignore=["en.seamless"]), set())
        self.assertEqual(self.ids("This is seamless.", ignore=["Seamless"]), set())

    def test_extra_phrase(self):
        self.assertEqual(self.ids("Das ist ein Quantensprung.", extra=["quantensprung"]), {"custom.1"})

    def test_clean_texts_have_no_findings(self):
        clean = [
            "Ich habe die Datei angelegt und die Tests laufen. Es fehlt noch der Banner, den mache ich morgen.",
            "Der Server startet um 04:00 Uhr neu. Container ohne Restart-Policy bleiben danach liegen.",
            "Die Rechnung ist bezahlt. Bitte prüfe, ob die Summe stimmt, und sag mir dann Bescheid.",
            "The tests pass and the plugin is installed. The banner is still missing; I will add it tomorrow.",
            "Run the command, then open the settings page and set the mode to fix.",
        ]
        for text in clean:
            rep = guard.check(text)
            self.assertFalse(rep.has_findings, (text, rep.as_dict()))


class Address(unittest.TestCase):
    def test_mixed_in_one_paragraph(self):
        rep = guard.check("Du kannst das machen. Können Sie mir sagen, ob Ihnen das passt?")
        self.assertEqual(rep.form, "mixed")
        self.assertEqual(rep.mixed, [(1, 2)])
        self.assertIn("du und Sie im selben Absatz", guard.footer(rep, "de"))

    def test_separate_paragraphs_are_not_mixed(self):
        rep = guard.check("Hier ist der Entwurf für dich.\n\nSehr geehrter Herr Meier, gerne sende ich Ihnen das Angebot.")
        self.assertEqual(rep.mixed, [])
        self.assertEqual(rep.form, "mixed")
        self.assertFalse(rep.has_findings)

    def test_sentence_start_sie_is_ambiguous(self):
        self.assertEqual(guard.address_counts("Die Äpfel liegen dort. Sie sind rot.\nSie sind grün."), (0, 0))
        self.assertEqual(guard.address_counts("1. Sie öffnen das Menü.\n- Ihre Datei"), (0, 0))

    def test_mid_sentence_formal_counts(self):
        self.assertEqual(guard.address_counts("Dann klicken Sie auf Speichern und senden Ihre Datei."), (0, 2))

    def test_talking_about_the_forms_is_not_using_them(self):
        for text in ("Das Plugin prüft die Anrede (du / Sie) in jeder Antwort.",
                     "Soll ich du oder Sie verwenden? Die Sie-Form wirkt förmlich.",
                     "Im Text steht „Sie“ statt „du“, prüfe die Du-Form.",
                     "Zwei Entwürfe, einer per Sie, einer per Du. Wir bieten das Du an."):
            du, sie = guard.address_counts(text)
            self.assertFalse(du and sie, text)
        # seen live: a model answer that explains the plugin
        rep = guard.check("Es prüft inkonsistente oder falsche Anrede (du / Sie). Füge einfach den Text ein, den du prüfen möchtest.")
        self.assertEqual(rep.mixed, [])

    def test_table_cell_start_and_quotations(self):
        self.assertEqual(guard.address_counts("| 24.10. | Sie fragte nach dem Termin |"), (0, 0))
        self.assertEqual(guard.address_counts('Du sagst ihm: „Ich wachse nur mit, wenn Sie wachsen.“ Und "für Sie da" auch.'), (1, 0))

    def test_lowercase_sie_is_not_formal(self):
        self.assertEqual(guard.address_counts("Die Kunden sagen, dass sie warten."), (0, 0))

    def test_expected_form(self):
        rep = guard.check("Bitte senden Sie uns die Unterlagen bis Freitag.", address="du")
        self.assertEqual(rep.wrong_form, 1)
        self.assertIn("1x Sie statt du", guard.footer(rep, "de"))

    def test_switch_against_previous_answer(self):
        rep = guard.check("Wie geht es dir heute?", previous_form="sie")
        self.assertEqual(rep.previous_form, "sie")
        self.assertIn("vorher Sie, jetzt du", guard.footer(rep, "de"))

    def test_switch_tracking_off(self):
        self.assertIsNone(guard.check("Wie geht es dir heute?", previous_form="sie", track_switches=False).previous_form)

    def test_english_text_has_no_address_check(self):
        rep = guard.check("You can say du or Sie in German, it depends.")
        self.assertIsNone(rep.form)


class Language(unittest.TestCase):
    def test_detect(self):
        self.assertEqual(guard.detect_language(f"Das Plugin {DASH} gebaut an einem Tag {DASH} läuft."), "de")
        self.assertEqual(guard.detect_language("Öffnungszeiten Mo bis Fr"), "de")
        self.assertEqual(guard.detect_language("The plugin was built in a day and it works."), "en")


class Hook(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(HOME / "plugin-data", ignore_errors=True)

    def test_report_is_pure_append(self):
        ctx = setup()
        text = f"Das Plugin {DASH} gebaut an einem Tag {DASH} läuft."
        out = run_hook(ctx, text)
        self.assertTrue(out.startswith(text))
        self.assertEqual(out[len(text):], "\n\n*writing-guard: 2 Gedankenstriche.*")

    def test_trailing_newline_keeps_prefix(self):
        out = run_hook(setup(), f"Text {DASH} hier.\n")
        self.assertTrue(out.startswith(f"Text {DASH} hier.\n"))
        self.assertFalse(out.startswith(f"Text {DASH} hier.\n\n\n"))

    def test_clean_answer_unchanged(self):
        self.assertIsNone(run_hook(setup(), "Alles erledigt, die Tests laufen."))

    def test_fix_mode(self):
        out = run_hook(setup(mode="fix"), f"Gut {DASH} sehr gut. `a {DASH} b`")
        self.assertEqual(out, f"Gut, sehr gut. `a {DASH} b`\n\n*writing-guard: 1 dash replaced.*")

    def test_fix_mode_without_footer(self):
        self.assertEqual(run_hook(setup(mode="fix", footer=False), f"Gut {DASH} sehr gut."), "Gut, sehr gut.")

    def test_report_without_footer_never_changes_text(self):
        ctx = setup(footer=False)
        self.assertIsNone(run_hook(ctx, f"Gut {DASH} sehr gut. Ich hoffe, das hilft!"))
        self.assertIn("1 Gedankenstrich", ctx.commands["writing-guard"](""))

    def test_mode_off(self):
        self.assertIsNone(run_hook(setup(mode="off"), f"a {DASH} b"))

    def test_disabled_platform(self):
        self.assertIsNone(run_hook(setup(), f"a {DASH} b", platform="cron"))
        self.assertIsNotNone(run_hook(setup(disabled_platforms=[]), f"a {DASH} b", platform="cron"))

    def test_language_setting(self):
        out = run_hook(setup(language="en"), f"Das Plugin {DASH} gebaut an einem Tag {DASH} läuft.")
        self.assertTrue(out.endswith("*writing-guard: 2 dashes.*"))

    def test_string_settings_from_config(self):
        self.assertIsNone(run_hook(setup(footer="false"), f"a {DASH} b"))
        self.assertIsNotNone(run_hook(setup(check_dashes="true", extra_phrases="foo, bar"), "this is foo"))

    def test_switch_between_turns_and_store_content(self):
        ctx = setup()
        self.assertIsNone(run_hook(ctx, "Können Sie mir die Datei schicken? Danke.", session_id="A"))
        out = run_hook(ctx, "Klar, ich schicke dir die Datei gleich.", session_id="A")
        self.assertIn("Anrede gewechselt: vorher Sie, jetzt du", out)
        self.assertIsNone(run_hook(ctx, "Klar, ich schicke dir die Datei gleich.", session_id="B"))
        data = json.loads((HOME / "plugin-data" / "writing-guard" / "sessions.json").read_text())
        self.assertEqual(set(data["sessions"]), {"A", "B"})
        for entry in data["sessions"].values():
            self.assertEqual(set(entry), {"form", "ts"})

    def test_old_sessions_expire(self):
        ctx = setup()
        run_hook(ctx, "Wie geht es dir heute?", session_id="old")
        path = HOME / "plugin-data" / "writing-guard" / "sessions.json"
        data = json.loads(path.read_text())
        data["sessions"]["old"]["ts"] = int(time.time()) - 40 * 86400
        path.write_text(json.dumps(data))
        run_hook(ctx, "Wie geht es dir heute?", session_id="new")
        self.assertNotIn("old", json.loads(path.read_text())["sessions"])

    def test_errors_never_break_the_turn(self):
        ctx = setup()
        self.assertIsNone(ctx.hooks["transform_llm_output"](response_text=None))
        self.assertIsNone(ctx.hooks["transform_llm_output"](response_text=["x"], platform=None))
        original = guard.check
        guard.check = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            self.assertIsNone(run_hook(ctx, f"a {DASH} b"))
        finally:
            guard.check = original

    def test_too_long_is_skipped(self):
        self.assertTrue(run_hook(setup(), f"a {DASH} b " * 40_000) is None)

    def test_speed(self):
        text = (f"Das ist ein Satz {DASH} mit Strich, und du liest ihn. Es ist wichtig zu beachten. " * 120)[:10_000]
        start = time.perf_counter()
        for _ in range(10):
            guard.check(text, fix=True)
        self.assertLess((time.perf_counter() - start) / 10, 0.05)


class ToolAndCommand(unittest.TestCase):
    def test_tool(self):
        schema, handler = setup().tools["writing_guard_check"]
        out = json.loads(handler({"text": f"Gut {DASH} sehr gut. Ich hoffe, das hilft!", "fix": True}))
        self.assertTrue(out["ok"])
        self.assertEqual(out["fixed_text"], "Gut, sehr gut. Ich hoffe, das hilft!")
        self.assertFalse(out["clean"])
        self.assertIn("next_step", out)
        clean = json.loads(handler({"text": f"Gut {DASH} sehr gut.", "fix": True}))
        self.assertTrue(clean["clean"])

    def test_tool_address_argument(self):
        _, handler = setup().tools["writing_guard_check"]
        out = json.loads(handler({"text": "Bitte senden Sie uns die Unterlagen.", "address": "du"}))
        self.assertEqual(out["report"]["address"]["wrong_form"], 1)

    def test_tool_errors(self):
        _, handler = setup().tools["writing_guard_check"]
        self.assertEqual(json.loads(handler({}))["error_type"], "invalid_argument")
        self.assertEqual(json.loads(handler("nonsense"))["error_type"], "invalid_argument")

    def test_tool_first_sentence_fits_tool_search(self):
        desc = setup().tools["writing_guard_check"][0]["description"]
        first = desc.split(". ")[0]
        self.assertLessEqual(len(first), 60, first)

    def test_command(self):
        cmd = setup().commands["writing-guard"]
        self.assertIn("mode report", cmd(""))
        self.assertIn("2 Gedankenstriche", cmd(f"check Das {DASH} ist {DASH} gut, sagt man."))
        self.assertEqual(cmd("check Alles gut hier, danke."), "writing-guard: no findings.")
        self.assertIn("Usage", cmd("check"))

    def test_skill_file_exists(self):
        path, desc = setup().skills["check-draft"]
        self.assertTrue(path.is_file())
        self.assertIn("writing_guard_check", desc)


class Manifest(unittest.TestCase):
    def test_manifest_matches_registrations(self):
        text = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
        ctx = setup()
        for hook in ctx.hooks:
            self.assertIn(f"  - {hook}", text)
        for tool in ctx.tools:
            self.assertIn(f"  - {tool}", text)
        for key in wg.DEFAULTS:
            self.assertIn(f"  {key}:", text)

    def test_no_dashes_in_shipped_text(self):
        for path in ROOT.rglob("*"):
            if path.suffix in (".md", ".yaml") and "tests" not in path.parts:
                self.assertEqual(guard.count_dashes(path.read_text(encoding="utf-8")), 0, path)
        for line in (guard.footer(guard.check(f"a {DASH} b. Ich hoffe, das hilft!", fix=True), lang)
                     for lang in ("de", "en")):
            self.assertEqual(guard.count_dashes(line), 0)


if __name__ == "__main__":
    unittest.main()
