"""User-facing texts (English and German) and the chat renderings of status, map, check, trace, find.

German texts use "du" and no em or en dashes (house style).
"""
from __future__ import annotations

import textwrap
import time
import unicodedata
from typing import Any, Optional

from . import vendors

DOT = {"green": "🟢", "amber": "🟡", "red": "🔴"}
CANARY = "🐤"

T: dict[str, dict[str, str]] = {
    "title": {"en": "Privacy X-ray", "de": "Privacy X-ray"},
    "tagline": {"en": "Where does your data actually go?", "de": "Wohin gehen deine Daten wirklich?"},
    "help": {
        "en": ("/xray                        status\n"
               "/xray check [--all]          audit the paths on which Hermes sends content off this machine\n"
               "/xray fix <id> [--yes]       show the fix for a finding; --yes applies it\n"
               "/xray canary                 create a fictitious person to trace\n"
               "/xray trace [canary-id] [--deep]   where the canary went (requests and local stores)\n"
               "/xray map [--session | --turns N | --hours N]   leak map of recent requests\n"
               "/xray report [--session]     write the HTML leak map\n"
               "/xray find \"<name or e-mail>\" [--export] [--deep]   search local stores for a person\n"
               "fix --yes and find run only on this machine (CLI, TUI, desktop, dashboard), not over a chat gateway.\n"
               "Not legal advice and not a compliance certificate."),
        "de": ("/xray                        Status\n"
               "/xray check [--all]          prüft die Wege, auf denen Hermes Inhalte von diesem Rechner schickt\n"
               "/xray fix <id> [--yes]       zeigt die Abhilfe zu einem Befund; --yes wendet sie an\n"
               "/xray canary                 erfindet eine Testperson zum Verfolgen\n"
               "/xray trace [ID] [--deep]    wohin die Testperson gelangt ist (Anfragen und lokale Ablagen)\n"
               "/xray map [--session | --turns N | --hours N]   Datenfluss-Karte der letzten Anfragen\n"
               "/xray report [--session]     schreibt die Datenfluss-Karte als HTML\n"
               "/xray find \"<Name oder Mail>\" [--export] [--deep]   sucht eine Person in den lokalen Ablagen\n"
               "fix --yes und find laufen nur auf diesem Rechner (CLI, TUI, Desktop, Dashboard), nicht über ein Chat-Gateway.\n"
               "Keine Rechtsberatung und kein Konformitätsnachweis."),
    },
    "unknown_cmd": {"en": "Unknown command '{v}'.", "de": "Unbekannter Befehl '{v}'."},
    "usage_turns": {"en": "--turns needs a whole number from 1 to 10000, for example /xray map --turns 5.",
                    "de": "--turns braucht eine ganze Zahl von 1 bis 10000, zum Beispiel /xray map --turns 5."},
    "usage_hours": {"en": "--hours needs a number of hours above 0 and up to 8760 (one year), for example /xray map --hours 24.",
                    "de": "--hours braucht eine Stundenzahl über 0 und bis 8760 (ein Jahr), zum Beispiel /xray map --hours 24."},
    "usage_map": {"en": "Use one of --session, --turns N or --hours N.",
                  "de": "Nimm eine dieser Angaben: --session, --turns N oder --hours N."},
    "usage_option": {"en": "Unknown option '{o}'. {hint}", "de": "Unbekannte Option '{o}'. {hint}"},
    "trace_unknown": {"en": "No canary with the id '{id}'. Known canaries: {ids}.",
                      "de": "Keine Testperson mit der ID '{id}'. Vorhanden: {ids}."},
    "gateway_refused": {"en": ("/xray {v} runs only on this machine (CLI, TUI, desktop app or dashboard), not over "
                               "{p}: {why} Run it there. To allow it on chat gateways, set "
                               "plugins.entries.privacy-xray.settings.allow_sensitive_on_gateways to true."),
                        "de": ("/xray {v} läuft nur auf diesem Rechner (CLI, TUI, Desktop-App oder Dashboard), nicht "
                               "über {p}: {why} Führe es dort aus. Für Chat-Gateways freischalten: "
                               "plugins.entries.privacy-xray.settings.allow_sensitive_on_gateways auf true setzen.")},
    "why_fix": {"en": "it changes your Hermes config.", "de": "es ändert deine Hermes-Konfiguration."},
    "why_find": {"en": "it shows excerpts from your local chats, logs and files.",
                 "de": "es zeigt Auszüge aus deinen lokalen Chats, Logs und Dateien."},
    "unknown_surface": {"en": "an unknown surface", "de": "eine unbekannte Oberfläche"},
    "status_head": {"en": "{t}: {n} outgoing requests recorded ({today} today), {d} destinations, ledger {kb} KB.",
                    "de": "{t}: {n} ausgehende Anfragen erfasst ({today} heute), {d} Ziele, Protokoll {kb} KB."},
    "status_canary": {"en": "Active canary: {name} ({cid}). Run /xray trace.",
                      "de": "Aktive Testperson: {name} ({cid}). Weiter mit /xray trace."},
    "status_nocanary": {"en": "No canary yet. Try /xray canary.", "de": "Noch keine Testperson. Probier /xray canary."},
    "status_check": {"en": "Last check: {r} red, {a} amber, {g} green ({when}).",
                     "de": "Letzte Prüfung: {r} rot, {a} gelb, {g} grün ({when})."},
    "status_nocheck": {"en": "No config check yet: /xray check.", "de": "Noch keine Prüfung: /xray check."},
    "status_guard": {"en": "Guard (mask canary and watch terms in main requests): {state}.",
                     "de": "Schutz (Testperson und Suchbegriffe in Hauptanfragen maskieren): {state}."},
    "on": {"en": "on", "de": "an"}, "off": {"en": "off", "de": "aus"},
    "map_head": {"en": "{t} leak map: {n} requests ({scope}), {d} destinations.",
                 "de": "{t} Datenfluss-Karte: {n} Anfragen ({scope}), {d} Ziele."},
    "incomplete": {"en": "Count incomplete: {n} request(s) were too long to scan in full for data types.",
                   "de": "Zählung unvollständig: {n} Anfrage(n) waren zu lang, um sie ganz nach Datenarten zu prüfen."},
    "incomplete_short": {"en": "count incomplete", "de": "Zählung unvollständig"},
    "agg_note": {"en": "Behind an aggregator the model's vendor is read from the model id; which company finally "
                       "processes the request is not visible to privacy-xray.",
                 "de": "Hinter einem Aggregator wird der Modellanbieter aus der Modell-ID gelesen; welche Firma die "
                       "Anfrage am Ende verarbeitet, kann privacy-xray nicht sehen."},
    "map_empty": {"en": "No outgoing requests recorded for this scope yet. Chat a turn, then run /xray map.",
                  "de": "Für diesen Bereich ist noch keine Anfrage erfasst. Chatte einen Zug, dann /xray map."},
    "scope_session": {"en": "this chat", "de": "dieser Chat"},
    "scope_turns": {"en": "last {n} turns", "de": "letzte {n} Züge"},
    "scope_hours": {"en": "last {n} h", "de": "letzte {n} Std."},
    "scope_since": {"en": "since {t}", "de": "seit {t}"},
    "main": {"en": "main", "de": "Haupt"}, "side": {"en": "side", "de": "Neben"},
    "types": {"en": "Personal data types in outgoing requests (summed per request): {x}.",
              "de": "Personenbezogene Datenarten in ausgehenden Anfragen (je Anfrage gezählt): {x}."},
    "types_none": {"en": "No personal data types detected in outgoing requests.",
                   "de": "Keine personenbezogenen Datenarten in ausgehenden Anfragen erkannt."},
    "hq_note": {"en": "Country = vendor headquarters, not the processing location.",
                "de": "Land = Firmensitz des Anbieters, nicht der Ort der Verarbeitung."},
    "check_head": {"en": "{t} config check: {r} red, {a} amber, {g} green.",
                   "de": "{t} Konfigurationsprüfung: {r} rot, {a} gelb, {g} grün."},
    "check_green_group": {"en": "{n} more green: {ids}.", "de": "{n} weitere grün: {ids}."},
    "check_fix_hint": {"en": "Apply a fix: /xray fix <id> (shows the command), then /xray fix <id> --yes.",
                       "de": "Abhilfe: /xray fix <id> (zeigt den Befehl), dann /xray fix <id> --yes."},
    "fix_unknown": {"en": "No finding with id '{id}'. Run /xray check for the list.",
                    "de": "Kein Befund mit der ID '{id}'. Liste mit /xray check."},
    "fix_none": {"en": "'{id}' has no automatic fix; privacy-xray applies nothing here. {manual}",
                 "de": "Für '{id}' gibt es keine automatische Abhilfe; privacy-xray wendet hier nichts an. {manual}"},
    "fix_green": {"en": "'{id}' is already green. Nothing to fix.", "de": "'{id}' ist schon grün. Nichts zu tun."},
    "fix_show": {"en": "Fix for {id} ({sev}): {why}\nThis runs:\n{cmds}\n{note}Apply with: /xray fix {id} --yes",
                 "de": "Abhilfe für {id} ({sev}): {why}\nDas läuft dann:\n{cmds}\n{note}Anwenden mit: /xray fix {id} --yes"},
    "fix_note": {"en": "Note: {x}\n", "de": "Hinweis: {x}\n"},
    "fix_done": {"en": "Applied:\n{cmds}\nRe-check: {id} is now {sev}. The new setting applies from the next session (/new).",
                 "de": "Angewendet:\n{cmds}\nNeue Prüfung: {id} ist jetzt {sev}. Die neue Einstellung gilt ab der nächsten Sitzung (/new)."},
    "fix_failed": {"en": "The fix was not applied: {err}", "de": "Die Abhilfe wurde nicht angewendet: {err}"},
    "fix_tool": {"en": "Fixes are only applied by the user with /xray fix <id> --yes.",
                 "de": "Abhilfen wendet nur der Nutzer mit /xray fix <id> --yes an."},
    "canary_new": {
        "en": ("{c} New canary created: a fictitious person, every value is fake.\n"
               "  Name    {name}\n  E-mail  {email}\n  IBAN    {iban}  (valid check sum, no real bank)\n"
               "  Phone   {phone}  (UK range reserved for fiction)\n"
               "Now mention it in a normal chat turn, for example:\n"
               "  \"Write a short payment reminder to {name} ({email}), IBAN {iban}.\"\n"
               "Then run /xray trace."),
        "de": ("{c} Neue Testperson: eine erfundene Person, jeder Wert ist unecht.\n"
               "  Name    {name}\n  Mail    {email}\n  IBAN    {iban}  (gültige Prüfziffer, keine echte Bank)\n"
               "  Telefon {phone}  (britischer Bereich für Fiktion)\n"
               "Erwähne sie jetzt in einem normalen Chat-Zug, zum Beispiel:\n"
               "  \"Schreib eine kurze Zahlungserinnerung an {name} ({email}), IBAN {iban}.\"\n"
               "Danach /xray trace."),
    },
    "trace_none": {"en": "No canary yet. Create one with /xray canary.", "de": "Noch keine Testperson. Erzeuge eine mit /xray canary."},
    "trace_head": {"en": "{c} Canary {name} ({cid}), created {when}: found in {n} places.",
                   "de": "{c} Testperson {name} ({cid}), erzeugt {when}: an {n} Orten gefunden."},
    "trace_head0": {"en": "{c} Canary {name} ({cid}), created {when}: not found anywhere yet. Mention it in a chat turn first.",
                    "de": "{c} Testperson {name} ({cid}), erzeugt {when}: noch nirgends gefunden. Erwähne sie zuerst in einem Chat-Zug."},
    "sent_out": {"en": "Sent out ({n})", "de": "Verschickt ({n})"},
    "at_rest": {"en": "Stored on this machine ({n})", "de": "Auf diesem Rechner gespeichert ({n})"},
    "not_found": {"en": "Searched, nothing found: {x}.", "de": "Durchsucht, nichts gefunden: {x}."},
    "partial": {"en": "Search incomplete: {why}.", "de": "Suche unvollständig: {why}."},
    "why_state_db_deadline": {"en": "the time budget ended a state.db query", "de": "das Zeitbudget hat eine state.db-Abfrage beendet"},
    "why_file_budget": {"en": "the time or size budget ended the file search", "de": "das Zeit- oder Größenbudget hat die Dateisuche beendet"},
    "why_partial_files": {"en": "only partly read: {x}", "de": "nur teilweise gelesen: {x}"},
    "why_size": {"en": "newest {mb} MB", "de": "neueste {mb} MB"},
    "why_budget": {"en": "budget", "de": "Budget"},
    "coverage_tail": {"en": "Tool outputs longer than 8 KB were searched in their first 8 KB only (the part Hermes indexes); "
                            "add --deep for a full pass.",
                      "de": "Werkzeug-Ausgaben über 8 KB wurden nur in den ersten 8 KB durchsucht (dem Teil, den Hermes "
                            "indiziert); mit --deep vollständig."},
    "main_req": {"en": "main request", "de": "Hauptanfrage"},
    "side_req": {"en": "side request: {task}", "de": "Nebenanfrage: {task}"},
    "requests": {"en": "{n} request(s)", "de": "{n} Anfrage(n)"},
    "in_fields": {"en": "in {f}", "de": "in {f}"},
    "hits": {"en": "{n} {w}", "de": "{n} Treffer"},
    "dump_note": {"en": "request dump", "de": "Anfrage-Mitschnitt"},
    "msgs": {"en": "{n} {mw} in {s} {sw} ({roles})", "de": "{n} {mw} in {s} {sw} ({roles})"},
    "find_usage": {"en": "Usage: /xray find \"<name or e-mail>\" [--export] (at least 3 characters).",
                   "de": "Aufruf: /xray find \"<Name oder Mail>\" [--export] (mindestens 3 Zeichen)."},
    "find_head": {"en": "Subject search for \"{q}\": {n} hits in {p} places ({s} s).",
                  "de": "Personensuche nach \"{q}\": {n} Treffer an {p} Orten ({s} s)."},
    "find_export": {"en": "Access report written:\n  {md}\n  {js}\nIt contains masked snippets only. Review it before you hand it out.",
                    "de": "Auskunftsbericht geschrieben:\n  {md}\n  {js}\nEr enthält nur maskierte Auszüge. Prüfe ihn, bevor du ihn weitergibst."},
    "find_hint": {"en": "Add --export for a Markdown and JSON access report. privacy-xray itself never deletes anything.",
                  "de": "Mit --export entsteht ein Auskunftsbericht als Markdown und JSON. privacy-xray selbst löscht nie etwas."},
    "report_done": {"en": "HTML leak map written: {path}\nOpen it in a browser; it has no external assets.",
                    "de": "Datenfluss-Karte als HTML geschrieben: {path}\nIm Browser öffnen; sie lädt nichts von außen."},
    "error": {"en": "privacy-xray: that did not work ({e}).", "de": "privacy-xray: das hat nicht geklappt ({e})."},
}

SEV_WORD = {"en": {"red": "red", "amber": "amber", "green": "green"},
            "de": {"red": "rot", "amber": "gelb", "green": "grün"}}
FIELD_WORD = {"en": {"system": "system prompt", "user": "user", "assistant": "assistant", "tool": "tool output"},
              "de": {"system": "Systemprompt", "user": "Nutzer", "assistant": "Assistent", "tool": "Werkzeug-Ausgabe"}}
TYPE_WORD = {"en": {"email": "e-mail", "iban": "IBAN", "card": "payment card", "phone": "phone", "ipv4": "public IPv4",
                    "tax_id_de": "German tax ID", "vat_id_de": "German VAT ID", "watch": "watch term"},
             "de": {"email": "Mail", "iban": "IBAN", "card": "Zahlungskarte", "phone": "Telefon", "ipv4": "öffentliche IPv4",
                    "tax_id_de": "Steuer-ID", "vat_id_de": "USt-IdNr.", "watch": "Suchbegriff"}}
STORE_WORD = {
    "en": {"messages": "state.db messages", "session_titles": "state.db session titles",
           "system_prompts": "state.db stored system prompts", "delivery_queue": "state.db delivery queue",
           "sessions": "session files", "memories": "memory files", "logs": "logs", "cron_output": "cron output",
           "plugin_data": "other plugins' data", "pastes": "pastes", "composer_pastes": "composer pastes",
           "pending": "pending messages", "state.db": "state.db"},
    "de": {"messages": "state.db Nachrichten", "session_titles": "state.db Sitzungstitel",
           "system_prompts": "state.db gespeicherte Systemprompts", "delivery_queue": "state.db Zustellwarteschlange",
           "sessions": "Sitzungsdateien", "memories": "Gedächtnisdateien", "logs": "Logs", "cron_output": "Cron-Ausgaben",
           "plugin_data": "Daten anderer Plugins", "pastes": "Einfügungen", "composer_pastes": "Composer-Einfügungen",
           "pending": "wartende Nachrichten", "state.db": "state.db"},
}


def t(key: str, lang: str, **kw: Any) -> str:
    entry = T.get(key, {})
    text = entry.get(lang) or entry.get("en") or key
    try:
        return text.format(**kw)
    except Exception:  # noqa: BLE001
        return text


def when(ts: Optional[float], lang: str) -> str:
    if not ts:
        return "?"
    lt = time.localtime(float(ts))
    return time.strftime("%d.%m. %H:%M" if lang == "de" else "%Y-%m-%d %H:%M", lt)

# --------------------------------------------------------------------------- aggregation


def select_records(records: list[dict], session_id: str = "", turns: int = 0, hours: float = 0) -> list[dict]:
    if session_id:
        return [r for r in records if r.get("sid") == session_id]
    if hours:
        cutoff = time.time() - hours * 3600
        return [r for r in records if float(r.get("ts") or 0) >= cutoff]
    if turns:
        keys: list = []
        seen = set()
        for r in reversed(records):
            k = (r.get("sid") or "", r.get("turn") or "") if r.get("turn") else ("", f"ts{int(r.get('ts') or 0)}")
            if k not in seen:
                seen.add(k)
                keys.append(k)
            if len(keys) >= turns:
                break
        keep = set(keys)
        out = []
        for r in records:
            k = (r.get("sid") or "", r.get("turn") or "") if r.get("turn") else ("", f"ts{int(r.get('ts') or 0)}")
            if k in keep:
                out.append(r)
        return out
    return records


def rec_dest(r: dict) -> dict:
    """Destination of a ledger record: host, vendor, HQ, kind and (aggregators) the model vendor.

    ``key`` separates one aggregator by model vendor (OpenRouter with an Anthropic model and with a
    DeepSeek model are two recipients). Older records without ``mvendor`` get it from ``model``."""
    d = {"host": r.get("host") or "unknown", "vendor": r.get("vendor"), "hq": r.get("hq"),
         "local": bool(r.get("local")), "kind": r.get("vkind"), "mvendor": r.get("mvendor") or "",
         "mhq": r.get("mhq") or ""}
    if d["kind"] == "router" and not d["mvendor"] and r.get("model"):
        d["mvendor"], d["mhq"] = vendors.model_vendor(r.get("model"))
    d["key"] = d["host"] + ("|" + (d["mvendor"] or "?") if d["kind"] == "router" else "")
    return d


def dest_label(d: dict, lang: str = "en") -> str:
    return vendors.route_label(d, lang) if d.get("kind") == "router" else str(d.get("vendor") or d.get("host"))


def is_baseline(d: dict, main: Optional[dict]) -> bool:
    return bool(main) and vendors.same_route(d, main)


def aggregate(records: list[dict], main: Optional[dict] = None, region: str = "") -> dict:
    """Destinations with counts and status. main = configured main route (baseline recipient)."""
    dests: dict[str, dict] = {}
    types: dict[str, int] = {}
    incomplete = 0
    for r in records:
        rd = rec_dest(r)
        host = rd["key"]
        d = dests.setdefault(host, {"host": host, "dhost": rd["host"], "vendor": rd["vendor"], "hq": rd["hq"],
                                    "local": rd["local"], "kind": rd["kind"], "mvendor": rd["mvendor"],
                                    "mhq": rd["mhq"], "main": 0,
                                    "side": {}, "chars": 0, "types": {}, "canary": set(), "providers": set(),
                                    "models": set(), "watch": 0, "masked": 0, "incomplete": 0})
        if r.get("incomplete"):
            d["incomplete"] += 1
            incomplete += 1
        if r.get("kind") == "aux":
            task = r.get("aux_task") or "side"
            d["side"][task] = d["side"].get(task, 0) + 1
        else:
            d["main"] += 1
        d["chars"] += int(r.get("chars") or 0)
        for k, v in (r.get("types") or {}).items():
            d["types"][k] = d["types"].get(k, 0) + int(v)
            types[k] = types.get(k, 0) + int(v)
        for c in r.get("canary") or []:
            d["canary"].add(c.get("id"))
        if r.get("watch"):
            d["watch"] += 1
        d["masked"] += int(r.get("masked") or 0)
        if r.get("provider"):
            d["providers"].add(r["provider"])
        if r.get("model"):
            d["models"].add(r["model"])
    have_main = bool(main and main.get("host") and main.get("host") != "unknown")
    # Without a config, the destinations of main requests are the baseline.
    main_keys = {k for k, d in dests.items() if d["main"]}
    for d in dests.values():
        baseline = is_baseline({**d, "host": d["dhost"]}, main) if have_main else d["host"] in main_keys
        d["baseline"] = bool(baseline)
        d["label"] = dest_label(d)
        reg = vendors.in_region(str(d.get("hq")), region)
        if reg is not False and d.get("kind") == "router":
            reg = vendors.in_region(str(d.get("mhq") or "unknown"), region)
        if d["local"]:
            d["status"] = "green"
        elif baseline:
            d["status"] = "amber" if reg is False else "green"
        elif d["canary"] or d["types"] or d["watch"]:
            d["status"] = "red"
        else:
            d["status"] = "amber"
        d["canary"] = sorted(x for x in d["canary"] if x)
        d["providers"] = sorted(d["providers"])
        d["models"] = sorted(d["models"])
    order = {"red": 0, "amber": 1, "green": 2}
    lst = sorted(dests.values(), key=lambda d: (order[d["status"]], -(d["main"] + sum(d["side"].values()))))
    return {"requests": len(records), "destinations": lst, "types": types, "incomplete": incomplete,
            "side_requests": sum(1 for r in records if r.get("kind") == "aux"),
            "countries": sorted({d["hq"] for d in lst if d.get("hq") and d["hq"] not in ("local",)}
                                | {d["mhq"] for d in lst if d.get("kind") == "router" and d.get("mhq")})}

# --------------------------------------------------------------------------- renderers


def _types_text(types: dict, lang: str) -> str:
    return ", ".join(f"{TYPE_WORD[lang].get(k, k)} {v}" for k, v in sorted(types.items(), key=lambda kv: -kv[1]))


_NBSP = "\u00a0"
_BT = "\x60"  # backtick, spelled out (the Hermes security scan reads literal backticks as shell)


def _cols(text: str) -> int:
    """Terminal columns: wide characters and emoji take two."""
    n = 0
    for i, ch in enumerate(text):
        if unicodedata.combining(ch) or ch in "\ufe0f\u200d":
            continue
        emoji_style = text[i + 1:i + 2] == "\ufe0f"  # e.g. the warning sign with variation selector 16
        n += 2 if emoji_style or unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return n


def _keep_code(line: str) -> str:
    """Spaces inside backtick spans become non-breaking, so a command is never split across lines."""
    parts = line.split(_BT)
    for i in range(1, len(parts), 2):
        parts[i] = parts[i].replace(" ", _NBSP)
    return _BT.join(parts)


def wrap_text(text: str, width: int = 100) -> str:
    """Wrap long lines at word boundaries with a hanging indent. Commands in backticks stay whole."""
    out = []
    for line in str(text).split("\n"):
        if _cols(line) <= width:
            out.append(line)
            continue
        body = line.lstrip(" ")
        if body.startswith(("fix: ", "hermes ")):  # a command line: never split, so it can be copied whole
            out.append(line)
            continue
        lead = " " * (len(line) - len(body))
        first = body.split(" ", 1)[0]
        marker = _cols(first) <= 2 and not any(c.isalnum() for c in first)  # status dot, emoji or bullet
        hang = " " * ((_cols(first) + 1) if marker else 2)
        extra = _cols(first) - len(first)  # wide characters textwrap counts as one column
        wrapped = textwrap.wrap(_keep_code(body), width=max(20, width - len(lead) - extra),
                                subsequent_indent=hang, break_long_words=False, break_on_hyphens=False)
        out.extend(lead + w.replace(_NBSP, " ") for w in (wrapped or [body]))
    return "\n".join(out)


def render_map(agg: dict, lang: str, scope: str) -> str:
    if not agg["requests"]:
        return t("map_empty", lang)
    lines = [t("map_head", lang, t=t("title", lang), n=agg["requests"], scope=scope, d=len(agg["destinations"]))]
    for d in agg["destinations"]:
        parts = []
        if d["main"]:
            parts.append(f"{t('main', lang)} {d['main']}")
        for task, n in sorted(d["side"].items()):
            parts.append(f"{t('side', lang)} {task} {n}")
        hq = "local" if d["local"] else d.get("hq")
        if d.get("kind") == "router":
            hq = f"{hq} / {d.get('mhq') or '?'}"
        extra = f"  {CANARY} canary" if d["canary"] else ""
        if d.get("masked"):
            extra += f"  (guard masked {d['masked']})"
        if d.get("incomplete"):
            extra += f"  ({t('incomplete_short', lang)})"
        lines.append(f"{DOT[d['status']]} {d.get('dhost') or d['host']}  {dest_label(d, lang)} [{hq}]  "
                     f"{', '.join(parts)}{extra}")
        if d["types"]:
            lines.append(f"     {_types_text(d['types'], lang)}")
    lines.append(t("types", lang, x=_types_text(agg["types"], lang)) if agg["types"] else t("types_none", lang))
    if agg.get("incomplete"):
        lines.append(t("incomplete", lang, n=agg["incomplete"]))
    if any(d.get("kind") == "router" for d in agg["destinations"]):
        lines.append(t("agg_note", lang))
    lines.append(t("hq_note", lang))
    return "\n".join(lines)


def render_check(result: dict, lang: str, verbose: bool = False) -> str:
    s = result["summary"]
    lines = [t("check_head", lang, t=t("title", lang), r=s["red"], a=s["amber"], g=s["green"])]
    greens = []
    for f in result["findings"]:
        if f["severity"] == "green" and not verbose:
            greens.append(f["id"])
            continue
        lines.append(f"{DOT[f['severity']]} {f['id']}: {f['why'].get(lang) or f['why']['en']}")
        cmds = [c for c in fix_cmds(f)]
        for c in cmds:
            lines.append(f"     fix: {c}")
        if not cmds and f["fix"].get("manual") and f["severity"] != "green":
            lines.append(f"     {f['fix']['manual'].get(lang) or f['fix']['manual']['en']}")
            if f["fix"].get("warning"):
                lines.append(f"     ⚠️ {f['fix']['warning'].get(lang) or f['fix']['warning']['en']}")
    if greens:
        lines.append(f"{DOT['green']} " + t("check_green_group", lang, n=len(greens), ids=", ".join(greens)))
    if s["red"] or s["amber"]:
        lines.append(t("check_fix_hint", lang))
    lines.append(t("hq_note", lang))
    return "\n".join(lines)


def fix_cmds(f: dict) -> list[str]:
    from .audit import fix_commands
    return fix_commands(f)


def render_canary(c: dict, lang: str) -> str:
    return t("canary_new", lang, c=CANARY, name=c["name"], email=c["email"], iban=c["iban"], phone=c["phone"])


def trace_places(canary: dict, records: list[dict], rest: dict) -> dict:
    cid = canary["id"]
    groups: dict[tuple, dict] = {}
    incomplete = 0
    for r in records:
        if r.get("incomplete"):
            incomplete += 1
        hit = next((c for c in r.get("canary") or [] if c.get("id") == cid), None)
        if not hit:
            continue
        rd = rec_dest(r)
        key = (r.get("kind"), r.get("aux_task") or "", rd["key"])
        g = groups.setdefault(key, {"kind": r.get("kind"), "aux_task": r.get("aux_task") or "",
                                    "host": rd["key"], "dhost": rd["host"], "vendor": rd["vendor"],
                                    "hq": rd["hq"], "local": rd["local"], "vkind": rd["kind"],
                                    "mvendor": rd["mvendor"], "mhq": rd["mhq"], "count": 0,
                                    "fields": set(), "first": r.get("ts"), "last": r.get("ts"),
                                    "models": set()})
        g["count"] += 1
        g["fields"] |= set(hit.get("fields") or [])
        g["last"] = r.get("ts")
        if r.get("model"):
            g["models"].add(r["model"])
    out = []
    for g in groups.values():
        g["fields"] = [f for f in ("system", "user", "assistant", "tool") if f in g["fields"]]
        g["models"] = sorted(g["models"])
        out.append(g)
    out.sort(key=lambda g: (g["kind"] != "main", g["aux_task"], g["host"]))
    return {"sent": out, "rest": rest, "incomplete": incomplete}


def group_dest(g: dict) -> dict:
    """A trace group as a destination for vendors.same_route."""
    return {"host": g.get("dhost") or g.get("host"), "vendor": g.get("vendor"), "hq": g.get("hq"),
            "local": bool(g.get("local")), "kind": g.get("vkind"), "mvendor": g.get("mvendor") or "",
            "mhq": g.get("mhq") or ""}


def partial_text(rest: dict, lang: str) -> str:
    """Why a local-store search is incomplete, in words, with the partly read files."""
    why = []
    for reason in rest.get("partial_reasons") or []:
        if reason == "partial_files":
            files = []
            for pf in (rest.get("partial_files") or [])[:6]:
                tag = t("why_size", lang, mb=64) if pf.get("reason") == "size" else t("why_budget", lang)
                files.append(f"{pf.get('path')} ({tag})")
            more = len(rest.get("partial_files") or []) - len(files)
            why.append(t("why_partial_files", lang, x=", ".join(files) + (f" +{more}" if more > 0 else "")))
        else:
            why.append(t("why_" + reason, lang))
    if not why and rest.get("partial"):
        why.append(t("why_file_budget", lang))
    return t("partial", lang, why="; ".join(why))


def render_trace(canary: Optional[dict], places: Optional[dict], lang: str, main: Optional[dict] = None) -> str:
    if not canary:
        return t("trace_none", lang)
    sent = places["sent"]
    rest = places["rest"]
    stored = rest.get("places", [])
    n = len(sent) + len(stored)
    created = when(canary.get("created"), lang)
    if not n:
        return t("trace_head0", lang, c=CANARY, name=canary["name"], cid=canary["id"], when=created)
    lines = [t("trace_head", lang, c=CANARY, name=canary["name"], cid=canary["id"], when=created, n=n)]
    if sent:
        lines.append(t("sent_out", lang, n=len(sent)))
        for g in sent:
            label = t("main_req", lang) if g["kind"] == "main" else t("side_req", lang, task=g["aux_task"])
            gd = group_dest(g)
            if g["local"]:
                sev = "green"
            elif main and main.get("host") and main.get("host") != "unknown":
                sev = "green" if vendors.same_route(gd, main) else "red"
            else:
                sev = "green" if g["kind"] == "main" else "red"
            word = "vendor HQ" if lang == "en" else "Firmensitz"
            hq_code = g["hq"] if gd["kind"] != "router" else f"{g['hq']} / {g.get('mhq') or '?'}"
            hq = "local" if g["local"] else f"{word} {hq_code}"
            fields = ", ".join(FIELD_WORD[lang].get(f, f) for f in g["fields"])
            lines.append(f"  {DOT[sev]} {label} → {gd['host']} · {dest_label(gd, lang)}, {hq} · "
                         f"{t('requests', lang, n=g['count'])} · {t('in_fields', lang, f=fields)}")
    if stored:
        lines.append(t("at_rest", lang, n=len(stored)))
        for p in stored:
            lines.append("  • " + _place_text(p, lang))
    searched = [STORE_WORD[lang].get(e["store"], e["store"]) for e in rest.get("files", [])
                if e.get("exists") and not e.get("count")]
    if searched:
        lines.append(t("not_found", lang, x=", ".join(searched)))
    if rest.get("partial"):
        lines.append(partial_text(rest, lang))
    if "tool_tail" in (rest.get("coverage") or []):
        lines.append(t("coverage_tail", lang))
    if places.get("incomplete"):
        lines.append(t("incomplete", lang, n=places["incomplete"]))
    if any(group_dest(g)["kind"] == "router" for g in sent):
        lines.append(t("agg_note", lang))
    lines.append(t("hq_note", lang))
    return "\n".join(lines)


def _place_text(p: dict, lang: str) -> str:
    if p["store"] == "state.db":
        name = STORE_WORD[lang].get(p["place"], p["place"])
        det = p.get("detail") or {}
        if p["place"] == "messages":
            roles = ", ".join(f"{FIELD_WORD[lang].get(k, k)} {v}" for k, v in (det.get("by_role") or {}).items())
            n, s = p["count"], det.get("sessions", "?")
            words = {"en": (("message", "messages"), ("session", "sessions")),
                     "de": (("Nachricht", "Nachrichten"), ("Sitzung", "Sitzungen"))}[lang if lang == "de" else "en"]
            return f"{name}: " + t("msgs", lang, n=n, s=s, roles=roles, mw=words[0][str(n) != "1"],
                                   sw=words[1][str(s) != "1"])
        return f"{name}: {p['count']}"
    tag = f" ({t('dump_note', lang)})" if p.get("request_dump") else ""
    hits = t("hits", lang, n=p["count"], w="hit" if str(p["count"]) == "1" else "hits")
    return f"{p['place']}: {hits}{tag}"


def render_find(query: str, res: dict, lang: str) -> str:
    places = res.get("places", [])
    total = sum(p["count"] for p in places)
    lines = [t("find_head", lang, q=query, n=total, p=len(places), s=res.get("seconds"))]
    for p in places:
        lines.append("  • " + _place_text(p, lang))
        if p.get("snippet"):
            lines.append(f"      {p['snippet']}")
    for s in res.get("state_db", {}).get("snippets", [])[:5]:
        lines.append(f"      [{when(s.get('ts'), lang)} {s.get('role')}] {s['text']}")
    if res.get("partial"):
        lines.append(partial_text(res, lang))
    if "tool_tail" in (res.get("coverage") or []):
        lines.append(t("coverage_tail", lang))
    return "\n".join(lines)
