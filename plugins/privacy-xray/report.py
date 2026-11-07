"""Self-contained HTML leak map: inline CSS and SVG, no external assets, no scripts.

Layout: a verdict headline, a Sankey style flow map (Hermes -> task -> vendor, band width = number of
requests, flowing particles on every band, a pulsing aura on extra recipients that saw personal data),
an optional before/after comparison of two canaries, local stores, personal data types and the config
findings with their fix commands. Animations are pure CSS and switch off with prefers-reduced-motion;
a static screenshot shows the particles as dotted bands.

The page may show canary values (they are fictitious) and never shows message content.
"""
from __future__ import annotations

import html
import time
from typing import Any, Optional

from . import vendors as _vendors
from . import views

COL = {"green": "#2ee59d", "amber": "#ffc53d", "red": "#ff3d6e", "canary": "#ffe14d", "src": "#8b8cff",
       "info": "#7dd3fc"}

COUNTRY = {
    "US": ("United States", "USA"), "CN": ("China", "China"), "FR": ("France", "Frankreich"),
    "DE": ("Germany", "Deutschland"), "GB": ("United Kingdom", "Vereinigtes Königreich"),
    "CA": ("Canada", "Kanada"), "CH": ("Switzerland", "Schweiz"), "NL": ("Netherlands", "Niederlande"),
    "IE": ("Ireland", "Irland"), "IL": ("Israel", "Israel"), "JP": ("Japan", "Japan"),
    "KR": ("South Korea", "Südkorea"), "SG": ("Singapore", "Singapur"), "SE": ("Sweden", "Schweden"),
    "FI": ("Finland", "Finnland"), "IN": ("India", "Indien"), "AE": ("UAE", "VAE"),
    "local": ("this machine", "dieser Rechner"), "unknown": ("unknown", "unbekannt"),
}

L10N = {
    "en": {
        "sub": "Where does your data actually go?", "generated": "Generated",
        "requests": "Requests", "vendors": "Vendors", "side": "Side requests", "countries": "Vendor countries",
        "findings": "Config findings", "flow": "Data flow",
        "flow_sub": "Every model request Hermes sent ({scope}). Band width = number of requests. "
                    "Moving dots = the requests; yellow dots carried the canary.",
        "machine": "This machine", "req_n": "{n} requests", "side_n": "{n} side requests",
        "your_chat": "Your chat", "rest": "Stored at rest", "rest_sub": "Local stores where the canary was found.",
        "rest_none": "No canary search yet. Run /xray canary, chat a turn, then /xray trace.",
        "types": "Personal data seen in requests", "types_none": "No personal data types detected.",
        "check": "Configuration findings", "fix": "Fix", "nofix": "no automatic fix",
        "legend_main": "your model vendor", "legend_extra": "extra recipient",
        "legend_red": "extra recipient with personal data", "legend_canary": "carried the canary",
        "empty": "No requests recorded yet.",
        "limits": ("Metadata only: privacy-xray records destinations, sizes and counts, never message content. "
                   "Detection is pattern based and not exhaustive. Country = vendor headquarters, not the processing "
                   "location. Side requests are visible but cannot be blocked by a plugin. Not legal advice and not "
                   "a compliance certificate. Behind an aggregator (OpenRouter and similar) the model's vendor is read "
                   "from the model id; which company finally processes the request is not visible to the plugin."),
        "incomplete": "Count incomplete: {n} request(s) were too long to scan in full for data types.",
        "canary_on": "canary", "pii": "personal data", "baseline": "your model vendor", "extra": "extra recipient",
        "base_short": "your vendor", "extra_short": "extra recipient",
        "green_head": "{n} paths without an extra recipient",
        "fake": "Canary person, every value is fictitious",
        "v_canary": "Your canary reached {v} in {c} ({cc}).",
        "v_map": "Hermes sent {r} to {v} in {c} ({cc}).",
        "v_side": "{s} you did not ask for.",
        "v_side_c": "{s} you did not ask for carried it.",
        "v_extra1": "{x} got it although it is not your model vendor.",
        "v_extraN": "{x} got it although they are not your model vendor.",
        "v_extra_pii1": "{x} received personal data although it is not your model vendor.",
        "v_extra_piiN": "{x} received personal data although they are not your model vendor.",
        "v_clean": "Every copy went to your model vendor {x}.",
        "v_home": "Data left your home region ({r}).",
        "v_none": "Your canary has not left this machine yet.",
        "v_empty": "No outgoing requests recorded yet.",
        "stamp_red": "Extra recipient", "stamp_amber": "Check", "stamp_green": "Contained", "stamp_info": "Waiting",
        "vendor1": "vendor", "vendorN": "vendors", "country1": "country", "countryN": "countries",
        "request1": "request", "requestN": "requests", "sidereq1": "side request", "sidereqN": "side requests",
        "cmp": "Before and after", "cmp_sub": ("Two canaries, the earlier one against the latest one: the same test, "
                                             "before and after your change."),
        "before": "Before", "after": "After", "cmp_vendors": "{v} · {s}",
        "cmp_gone": "Gone after the change: {x}.", "cmp_new": "New after the change: {x}.",
        "cmp_same": "Same recipients before and after.", "and": "and",
        "hero_scope": "Latest canary only", "c_req1": "request carried it", "c_reqN": "requests carried it",
        "sev_red": "high", "sev_amber": "check", "sev_green": "ok",
        "all_req": "{scope}, all requests",
        "flow_since": ("Starts when the latest canary was created, so the diagram shows the state after your "
                       "change. Earlier traffic is in Before and after."),
        "types_sub": ("Every match, not only the canary, summed over all requests ({scope}). Each request "
                      "repeats the chat so far, so the same value is counted again in every later request."),
        "rest_sub_c": "Local stores where the latest canary ({name}) was found.",
        "legend_pii": "values found",
    },
    "de": {
        "sub": "Wohin gehen deine Daten wirklich?", "generated": "Erstellt",
        "requests": "Anfragen", "vendors": "Anbieter", "side": "Nebenanfragen", "countries": "Länder der Anbieter",
        "findings": "Befunde", "flow": "Datenfluss",
        "flow_sub": "Jede Modell-Anfrage von Hermes ({scope}). Bandbreite = Zahl der Anfragen. "
                    "Die Punkte sind die Anfragen; gelbe Punkte trugen die Testperson.",
        "machine": "Dieser Rechner", "req_n": "{n} Anfragen", "side_n": "{n} Nebenanfragen",
        "your_chat": "Dein Chat", "rest": "Lokal gespeichert", "rest_sub": "Lokale Ablagen, in denen die Testperson liegt.",
        "rest_none": "Noch keine Suche nach einer Testperson. /xray canary, einen Zug chatten, dann /xray trace.",
        "types": "Personenbezogene Daten in Anfragen", "types_none": "Keine personenbezogenen Datenarten erkannt.",
        "check": "Befunde der Konfiguration", "fix": "Abhilfe", "nofix": "keine automatische Abhilfe",
        "legend_main": "dein Modellanbieter", "legend_extra": "zusätzlicher Empfänger",
        "legend_red": "zusätzlicher Empfänger mit Personendaten", "legend_canary": "trug die Testperson",
        "empty": "Noch keine Anfragen erfasst.",
        "limits": ("Nur Metadaten: privacy-xray speichert Ziele, Größen und Zählwerte, nie Nachrichteninhalte. "
                   "Die Erkennung arbeitet mit Mustern und ist nicht vollständig. Land = Firmensitz des Anbieters, nicht "
                   "der Ort der Verarbeitung. Nebenanfragen sind sichtbar, ein Plugin kann sie aber nicht blockieren. "
                   "Keine Rechtsberatung und kein Konformitätsnachweis. Hinter einem Aggregator (OpenRouter und "
                   "ähnliche) wird der Modellanbieter aus der Modell-ID gelesen; welche Firma die Anfrage am Ende "
                   "verarbeitet, kann das Plugin nicht sehen."),
        "incomplete": "Zählung unvollständig: {n} Anfrage(n) waren zu lang, um sie ganz nach Datenarten zu prüfen.",
        "canary_on": "Testperson", "pii": "Personendaten", "baseline": "dein Modellanbieter",
        "extra": "zusätzlicher Empfänger", "base_short": "dein Anbieter", "extra_short": "Zusatzempfänger",
        "green_head": "{n} Wege ohne zusätzlichen Empfänger",
        "fake": "Testperson, jeder Wert ist erfunden",
        "v_canary": "Deine Testperson hat {v} in {c} ({cc}) erreicht.",
        "v_map": "Hermes hat {r} an {v} in {c} ({cc}) geschickt.",
        "v_side": "{s}, um die du nicht gebeten hast.",
        "v_side_c": "{s}, um die du nicht gebeten hast, haben sie mitgenommen.",
        "v_extra1": "{x} hat sie bekommen, obwohl du dort kein Modell gewählt hast.",
        "v_extraN": "{x} haben sie bekommen, obwohl du dort kein Modell gewählt hast.",
        "v_extra_pii1": "{x} hat Personendaten bekommen, obwohl du dort kein Modell gewählt hast.",
        "v_extra_piiN": "{x} haben Personendaten bekommen, obwohl du dort kein Modell gewählt hast.",
        "v_clean": "Jede Kopie ging an deinen Modellanbieter {x}.",
        "v_home": "Daten haben deine Heimatregion verlassen ({r}).",
        "v_none": "Deine Testperson hat diesen Rechner noch nicht verlassen.",
        "v_empty": "Noch keine ausgehenden Anfragen erfasst.",
        "stamp_red": "Zusätzlicher Empfänger", "stamp_amber": "Prüfen", "stamp_green": "Eingegrenzt",
        "stamp_info": "Wartet",
        "vendor1": "Anbieter", "vendorN": "Anbieter", "country1": "Land", "countryN": "Ländern",
        "request1": "Anfrage", "requestN": "Anfragen", "sidereq1": "Nebenanfrage", "sidereqN": "Nebenanfragen",
        "cmp": "Vorher und nachher", "cmp_sub": ("Zwei Testpersonen, die frühere gegen die neueste: derselbe Test vor und "
                                               "nach deiner Änderung."),
        "before": "Vorher", "after": "Nachher", "cmp_vendors": "{v} · {s}",
        "cmp_gone": "Nach der Änderung weg: {x}.", "cmp_new": "Nach der Änderung neu: {x}.",
        "cmp_same": "Vorher und nachher dieselben Empfänger.", "and": "und",
        "hero_scope": "Nur die neueste Testperson", "c_req1": "Anfrage trug sie", "c_reqN": "Anfragen trugen sie",
        "sev_red": "hoch", "sev_amber": "prüfen", "sev_green": "ok",
        "all_req": "{scope}, alle Anfragen",
        "flow_since": ("Beginnt, als die neueste Testperson angelegt wurde, und zeigt also den Stand nach deiner "
                       "Änderung. Den Verkehr davor zeigt Vorher und nachher."),
        "types_sub": ("Jeder Fund, nicht nur die Testperson, summiert über alle Anfragen ({scope}). Jede Anfrage "
                      "wiederholt den bisherigen Chat, derselbe Wert zählt also in jeder späteren Anfrage erneut."),
        "rest_sub_c": "Lokale Ablagen, in denen die neueste Testperson ({name}) liegt.",
        "legend_pii": "gefundene Werte",
    },
}

TASK_WORD = {
    "en": {"title_generation": "Title generation", "compression": "Compression", "vision": "Vision",
           "web_extract": "Web extract", "session_search": "Session search", "approval": "Approval",
           "background_review": "Background review", "curator": "Curator", "memory": "Memory",
           "skills_hub": "Skills hub", "mcp": "MCP"},
    "de": {"title_generation": "Titelerzeugung", "compression": "Kompression", "vision": "Bilderkennung",
           "web_extract": "Webauszug", "session_search": "Sitzungssuche", "approval": "Freigabe",
           "background_review": "Hintergrundprüfung", "curator": "Kurator", "memory": "Gedächtnis",
           "skills_hub": "Skills-Hub", "mcp": "MCP"},
}

CSS = """
*{box-sizing:border-box}html,body{margin:0;background:#05070d;color:#eef1f8;
font:16px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif}
body{background:radial-gradient(1100px 520px at 0% -8%,rgba(110,90,255,.20),transparent 62%),
radial-gradient(900px 520px at 100% 0%,rgba(255,61,110,.12),transparent 60%),#05070d;min-height:100vh}
.wrap{max-width:1240px;margin:0 auto;padding:30px 30px 52px}
header{display:flex;align-items:center;justify-content:space-between;gap:24px;margin-bottom:18px}
.brand{display:flex;align-items:center;gap:14px}.brand h1{margin:0;font-size:26px;letter-spacing:-.02em;font-weight:780}
.brand p{margin:0;color:#c9d0de;font-size:15px}.meta{color:#c2c9d8;font-size:13.5px;text-align:right}
.hero{position:relative;display:grid;grid-template-columns:1fr auto;gap:28px;align-items:center;padding:26px 30px;
border-radius:24px;margin-bottom:20px;overflow:hidden;border:1px solid var(--hc55);
background:linear-gradient(120deg,var(--hc22),rgba(255,255,255,.03) 55%),#0b0f1a;box-shadow:0 0 0 1px rgba(0,0,0,.4),
0 24px 80px var(--hc22)}
.hero:before{content:"";position:absolute;left:0;top:0;bottom:0;width:7px;background:var(--hc)}
.vh{margin:0;font-size:34px;line-height:1.18;font-weight:800;letter-spacing:-.025em;color:#fff}
.vh b,.vs b{color:var(--hc);font-weight:850}.vs{margin:10px 0 0;font-size:20px;line-height:1.35;color:#e6eaf3;font-weight:600}
.vs.warn b{color:#ff8fab}.chips{display:flex;flex-wrap:wrap;gap:10px;margin-top:18px}
.chip{display:inline-flex;align-items:center;gap:8px;padding:6px 13px;border-radius:999px;font-size:14px;color:#e8ecf5;
background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.14)}.chip b{font-size:16px;color:#fff}
.chip .pill{margin-left:2px}
.stamp{display:flex;flex-direction:column;align-items:center;gap:12px;min-width:230px}
.badge{display:flex;align-items:center;gap:10px;padding:10px 18px;border-radius:14px;font-weight:850;font-size:17px;
letter-spacing:.06em;text-transform:uppercase;color:#05070d;background:var(--hc);box-shadow:0 0 34px var(--hc77)}
.idc{width:100%;padding:12px 15px;border-radius:14px;background:rgba(255,225,77,.08);border:1px dashed rgba(255,225,77,.55);
font-size:13.5px;color:#fff2b0}.idc .n{font-size:17px;font-weight:800;color:#ffe14d}.idc .l{font-size:11.5px;
text-transform:uppercase;letter-spacing:.08em;color:#fff6c8;margin-bottom:3px;font-weight:700}
.card{background:linear-gradient(180deg,rgba(255,255,255,.055),rgba(255,255,255,.018));border:1px solid rgba(255,255,255,.10);
border-radius:22px;padding:20px 24px;margin-bottom:20px;box-shadow:0 20px 60px rgba(0,0,0,.4)}
.card h2{margin:0 0 3px;font-size:19px;font-weight:760;letter-spacing:-.01em}
.card .sub{margin:0 0 10px;color:#c9d0de;font-size:14px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.legend{display:flex;flex-wrap:wrap;gap:20px;color:#d7dceb;font-size:13.5px;margin-top:4px}
.legend i{display:inline-block;width:24px;height:8px;border-radius:4px;vertical-align:middle;margin-right:8px}
.row{display:flex;align-items:flex-start;gap:14px;padding:14px 0;border-top:1px solid rgba(255,255,255,.08)}
.row:first-of-type{border-top:0}.dot{width:12px;height:12px;border-radius:50%;margin-top:7px;flex:none;box-shadow:0 0 14px currentColor}
.row .t{font-weight:700;font-size:16.5px}.row .w{color:#dfe4ef;font-size:14.5px}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"DejaVu Sans Mono",monospace}
.cmd{display:flex;align-items:center;gap:10px;margin-top:9px;padding:9px 14px;border-radius:12px;background:#02040a;
border:1px solid rgba(46,229,157,.35);box-shadow:inset 3px 0 0 #2ee59d;font-size:15px;color:#f4fff9;overflow-x:auto;
white-space:nowrap}.cmd .p{color:#2ee59d;font-weight:800}.fixl{font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;
color:#9ff5cf;font-weight:750;margin-top:8px}
.ic{display:inline-block;padding:1px 9px;margin:2px 1px;border-radius:8px;background:#02040a;color:#f4fff9;
border:1px solid rgba(46,229,157,.35);font-size:14.5px}
.pill{display:inline-block;border-radius:999px;padding:1px 10px;font-size:13px;font-weight:750}
.bar{height:10px;border-radius:5px;background:rgba(255,255,255,.10);overflow:hidden}
.bar>div{height:100%;background:#8b8cff}
.cl{width:100%;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#c9d0de;font-weight:750;margin-bottom:-2px}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin:2px 0 12px}.stats .cl{margin-bottom:0}
.card h2 .pill{margin-left:6px;vertical-align:2px}
.typ{display:grid;grid-template-columns:130px 1fr 44px;align-items:center;gap:12px;padding:7px 0;font-size:15px}
.typ .n{text-align:right;color:#fff;font-weight:700}.empty{color:#c2c9d8;font-size:14.5px;padding:8px 0}
.place{display:grid;grid-template-columns:minmax(170px,auto) 1fr;gap:16px;align-items:baseline;padding:10px 0;
border-top:1px solid rgba(255,255,255,.08);font-size:14.5px}.place .k{white-space:nowrap;color:#eef1f8}
.place .c{color:#ffe98a;font-weight:650}
.fid{color:#c2c9d8;font-weight:400;font-size:13px;margin-left:6px}
.greens{margin-top:12px;padding-top:14px;border-top:1px solid rgba(255,255,255,.08);display:flex;flex-wrap:wrap;gap:8px}
.greens .gh{width:100%;color:#a6f7d2;font-size:14px;font-weight:700;margin-bottom:2px}
.gchip{display:inline-flex;align-items:center;gap:7px;padding:4px 11px;border-radius:999px;font-size:13px;color:#e2e8f2;
background:rgba(46,229,157,.08);border:1px solid rgba(46,229,157,.28)}.gchip i{width:7px;height:7px;border-radius:50%}
.cmp{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.cmpp{border-radius:18px;padding:16px 18px 10px;border:1px solid var(--pc55);background:linear-gradient(160deg,var(--pc18),
rgba(255,255,255,.02) 60%)}
.cmph{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.tag{padding:4px 12px;border-radius:9px;font-weight:850;
font-size:14px;letter-spacing:.08em;text-transform:uppercase;color:#05070d;background:var(--pc)}
.cmph .nm{font-size:18px;font-weight:800;color:#fff}.cmph .tm{color:#c9d0de;font-size:13.5px}
.cmps{margin:6px 0 2px;font-size:16px;font-weight:650;color:#eef1f8}.cmps b{color:var(--pc)}
.delta{margin-top:14px;padding:12px 16px;border-radius:14px;background:rgba(46,229,157,.09);border:1px solid rgba(46,229,157,.35);
font-size:16.5px;font-weight:700;color:#d9ffef}.delta.bad{background:rgba(255,61,110,.10);border-color:rgba(255,61,110,.45);color:#ffd6e0}
footer{color:#d0d6e2;font-size:13px;line-height:1.6;margin-top:8px}
svg text{font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif}
svg .mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"DejaVu Sans Mono",monospace}
.pt{fill:none;stroke-linecap:round;animation:flow var(--d,1.6s) linear infinite}
.aura{animation:pulse 1.8s ease-in-out infinite}
@keyframes flow{to{stroke-dashoffset:-72}}
@keyframes pulse{0%,100%{opacity:.45}50%{opacity:1}}
@media (prefers-reduced-motion:reduce){.pt,.aura{animation:none}}
@media (min-width:1700px){.wrap{max-width:1680px;padding-top:26px}html,body{font-size:17px}.vh{font-size:40px}
.vs{font-size:22px}}
@media (max-width:900px){.grid2,.cmp{grid-template-columns:1fr}.hero{grid-template-columns:1fr}}
"""

LOGO = ('<svg width="44" height="44" viewBox="0 0 46 46" aria-hidden="true"><defs><linearGradient id="lg" x1="0" y1="0" '
        'x2="1" y2="1"><stop offset="0" stop-color="#8b8cff"/><stop offset="1" stop-color="#ff3d6e"/></linearGradient></defs>'
        '<rect x="1" y="1" width="44" height="44" rx="13" fill="url(#lg)" opacity=".2" stroke="url(#lg)"/>'
        '<circle cx="23" cy="23" r="10.5" fill="none" stroke="url(#lg)" stroke-width="2.6"/>'
        '<circle cx="23" cy="23" r="3.6" fill="#ffe14d"/><path d="M8 23h5M33 23h5M23 8v5M23 33v5" stroke="#dfe4ef" '
        'stroke-width="2" stroke-linecap="round" opacity=".8"/></svg>')


def e(x: Any) -> str:
    return html.escape(str(x if x is not None else ""), quote=True)


def _trunc(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _pl(tx: dict, n: int, key: str) -> str:
    return f"{n} {tx[key + ('1' if n == 1 else 'N')]}"


def _join(items: list[str], lang: str) -> str:
    items = [x for x in items if x]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + f" {L10N[lang]['and']} " + items[-1]


def task_word(task: str, lang: str) -> str:
    if not task or task == "main":
        return L10N[lang]["your_chat"]
    return TASK_WORD[lang].get(task) or task.replace("_", " ").capitalize()


def country_name(code: str, lang: str) -> str:
    names = COUNTRY.get(code or "unknown")
    if not names:
        return str(code)
    return names[1] if lang == "de" else names[0]


def _country_label(code: str, lang: str) -> str:
    name = country_name(code, lang)
    return name if (" " not in name and len(name) <= 4) or name == code else f"{code} {name}"


def _inline_code(text: str) -> str:
    """Escape text; segments between backticks become inline command spans."""
    parts = str(text).split("\x60")
    return "".join(f'<span class="ic mono">{e(s)}</span>' if i % 2 else e(s) for i, s in enumerate(parts))


def _hc(sev: str) -> str:
    """CSS custom properties for a severity colour (base, 18/22/55/77 % alpha variants)."""
    c = COL.get(sev, COL["info"])
    return f"--hc:{c};--hc22:{c}38;--hc55:{c}8c;--hc77:{c}c4"


def _group_is_base(g: dict, main: Optional[dict], fallback: set) -> bool:
    """A trace group goes to the main route (same host/vendor, and for aggregators the same model
    vendor). Without a configured main route the destinations of main requests are the baseline."""
    if g.get("local"):
        return True
    if main and main.get("host") and main.get("host") != "unknown":
        return _vendors.same_route(views.group_dest(g), main)
    return g["host"] in fallback


def _base_fallback(groups: list[dict]) -> set:
    return {g["host"] for g in groups if g.get("kind") == "main"}


def _glabel(g: dict, lang: str = "en") -> str:
    return views.dest_label(views.group_dest(g), lang)


def _countries(items: list[dict]) -> list[str]:
    out = set()
    for x in items:
        out.add(str(x.get("hq") or "unknown"))
        if (x.get("kind") == "router" or x.get("vkind") == "router") and x.get("mhq"):
            out.add(str(x["mhq"]))
    return sorted(out)

# --------------------------------------------------------------------------- verdict


def verdict(lang: str, agg: dict, trace: Optional[dict], main: Optional[dict] = None, region: str = "") -> dict:
    """Headline facts. Returns {sev, head (html), subs [(html, cls)], vendors, countries, side, extra}."""
    tx = L10N[lang]
    sent = (trace or {}).get("sent") or []
    if trace is not None and sent:
        remote = [g for g in sent if not g.get("local")]
        fb = _base_fallback(sent)
        vendors_ = sorted({_glabel(g, lang) for g in remote})
        countries = _countries(remote)
        side = sum(int(g.get("count") or 0) for g in sent if g.get("kind") == "aux")
        extra = sorted({_glabel(g, lang) for g in remote if not _group_is_base(g, main, fb)})
        head = tx["v_canary"].format(v=f"<b>{e(_pl(tx, len(vendors_), 'vendor'))}</b>",
                                     c=f"<b>{e(_pl(tx, len(countries), 'country'))}</b>", cc=e(", ".join(countries)))
        pii_word, side_key = False, "v_side_c"
    elif trace is not None:
        return {"sev": "info", "head": e(tx["v_none"]), "subs": [], "vendors": [], "countries": [], "side": 0,
                "extra": []}
    else:
        dests = agg.get("destinations") or []
        if not dests:
            return {"sev": "info", "head": e(tx["v_empty"]), "subs": [], "vendors": [], "countries": [], "side": 0,
                    "extra": []}
        remote = [d for d in dests if not d.get("local")]
        vendors_ = sorted({views.dest_label(d, lang) for d in remote})
        countries = _countries(remote)
        side = int(agg.get("side_requests") or 0)
        extra = sorted({views.dest_label(d, lang) for d in remote if d.get("status") == "red"})
        head = tx["v_map"].format(r=f"<b>{e(_pl(tx, int(agg.get('requests') or 0), 'request'))}</b>",
                                  v=f"<b>{e(_pl(tx, len(vendors_), 'vendor'))}</b>",
                                  c=f"<b>{e(_pl(tx, len(countries), 'country'))}</b>", cc=e(", ".join(countries)))
        pii_word, side_key = True, "v_side"
    subs: list[tuple[str, str]] = []
    if side:
        subs.append((tx[side_key].format(s=f"<b>{e(_pl(tx, side, 'sidereq'))}</b>"), ""))
    if extra:
        key = ("v_extra_pii" if pii_word else "v_extra") + ("1" if len(extra) == 1 else "N")
        subs.append((tx[key].format(x=_join([f"<b>{e(x)}</b>" for x in extra], lang)), "warn"))
        sev = "red"
    else:
        base = sorted({v for v in vendors_}) or ["-"]
        subs.append((tx["v_clean"].format(x=_join([f"<b>{e(x)}</b>" for x in base], lang)), ""))
        sev = "green"
        from . import vendors as _v
        outside = [c for c in countries if _v.in_region(c, region) is False]
        if outside:
            sev = "amber"
            subs.append((e(tx["v_home"].format(r=region)), "warn"))
    return {"sev": sev, "head": head, "subs": subs, "vendors": vendors_, "countries": countries, "side": side,
            "extra": extra}

# --------------------------------------------------------------------------- sankey


def _flows_from_agg(agg: dict, trace: Optional[dict], max_dest: int = 7) -> tuple[list[dict], list[dict]]:
    dests = (agg.get("destinations") or [])[:max_dest]
    canary_keys = {("main" if g.get("kind") == "main" else (g.get("aux_task") or "side"), g["host"])
                   for g in (trace or {}).get("sent") or []}
    flows = []
    for d in dests:
        items = ([("main", d["main"])] if d["main"] else []) + sorted(d["side"].items())
        for task, n in items:
            if trace is not None:
                can = (task, d["host"]) in canary_keys
            else:
                can = bool(d.get("canary"))
            flows.append({"task": task, "host": d["host"], "n": int(n), "canary": can})
    nodes = []
    for d in dests:
        nodes.append({"host": d["host"], "dhost": d.get("dhost") or d["host"], "vendor": d.get("vendor") or d["host"],
                      "agg": d.get("kind") == "router", "mvendor": d.get("mvendor") or "", "mhq": d.get("mhq") or "",
                      "hq": "local" if d.get("local")
                      else (d.get("hq") or "unknown"), "status": d["status"], "baseline": bool(d.get("baseline")),
                      "types": d.get("types") or {},
                      "canary": (bool(d.get("canary")) if trace is None else False) or any(
                          f["canary"] for f in flows if f["host"] == d["host"])})
    return flows, nodes


def _flows_from_groups(groups: list[dict], main: Optional[dict]) -> tuple[list[dict], list[dict]]:
    fb = _base_fallback(groups)
    flows, nodes, seen = [], [], {}
    for g in groups:
        task = "main" if g.get("kind") == "main" else (g.get("aux_task") or "side")
        flows.append({"task": task, "host": g["host"], "n": int(g.get("count") or 0), "canary": True})
        if g["host"] not in seen:
            base = _group_is_base(g, main, fb)
            seen[g["host"]] = {"host": g["host"], "dhost": g.get("dhost") or g["host"],
                               "vendor": g.get("vendor") or g["host"], "agg": g.get("vkind") == "router",
                               "mvendor": g.get("mvendor") or "", "mhq": g.get("mhq") or "",
                               "hq": "local" if g.get("local") else (g.get("hq") or "unknown"),
                               "status": "green" if base else "red", "baseline": base, "types": {}, "canary": True}
            nodes.append(seen[g["host"]])
    nodes.sort(key=lambda n: (n["status"] != "red", n["vendor"]))
    return flows, nodes


def _band(x0: float, y0: float, x1: float, y1: float, t: float) -> str:
    m = (x0 + x1) / 2
    return (f"M{x0:.1f},{y0:.1f} C{m:.1f},{y0:.1f} {m:.1f},{y1:.1f} {x1:.1f},{y1:.1f} "
            f"L{x1:.1f},{y1 + t:.1f} C{m:.1f},{y1 + t:.1f} {m:.1f},{y0 + t:.1f} {x0:.1f},{y0 + t:.1f} Z")


def _mid(x0: float, y0: float, x1: float, y1: float) -> str:
    m = (x0 + x1) / 2
    return f"M{x0:.1f},{y0:.1f} C{m:.1f},{y0:.1f} {m:.1f},{y1:.1f} {x1:.1f},{y1:.1f}"


def _globe(x: float, y: float, r: float, col: str) -> str:
    return (f'<g opacity=".9"><circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="none" stroke="{col}" stroke-width="1.6"/>'
            f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{r * .45:.1f}" ry="{r}" fill="none" stroke="{col}" stroke-width="1.2"/>'
            f'<path d="M{x - r:.1f},{y:.1f}h{2 * r}M{x - r * .85:.1f},{y - r * .5:.1f}h{1.7 * r:.1f}'
            f'M{x - r * .85:.1f},{y + r * .5:.1f}h{1.7 * r:.1f}" stroke="{col}" stroke-width="1.1"/></g>')


def sankey(flows: list[dict], nodes: list[dict], lang: str, *, uid: str, compact: bool = False,
           canary_label: str = "", total_label: str = "") -> str:
    """Hermes -> task -> vendor bands. flows: {task, host, n, canary}; nodes: vendor nodes in display order."""
    tx = L10N[lang]
    flows = [f for f in flows if f["n"] > 0 and any(n["host"] == f["host"] for n in nodes)]
    if not flows:
        return f'<div class="empty">{e(tx["empty"])}</div>'
    if compact:
        W, x0w, tx0, tw, vx = 580, 92, 160, 140, 352
        vw, unit_max, avail, gap, vmin, tmin = 228, 16, 190, 14, 84, 56
    else:
        W, x0w, tx0, tw, vx = 1200, 186, 382, 196, 790
        vw, unit_max, avail, gap, vmin, tmin = 410, 22, 300, 20, 104, 58
    total = sum(f["n"] for f in flows)
    unit = max(3.0, min(unit_max, avail / max(total, 1)))
    th = {id(f): max(5.0, f["n"] * unit) for f in flows}
    task_order: list[str] = []
    for f in sorted(flows, key=lambda f: (f["task"] != "main", f["task"])):
        if f["task"] not in task_order:
            task_order.append(f["task"])
    hosts = [n["host"] for n in nodes if any(f["host"] == n["host"] for f in flows)]
    # fewer crossings: order vendors by the weighted mean position of their tasks and back (main stays on top)
    for _ in range(2):
        def bary(key: str, val: str, ref: list) -> float:
            fs = [f for f in flows if f[key] == val]
            w = sum(f["n"] for f in fs) or 1
            return sum(ref.index(f["host" if key == "task" else "task"]) * f["n"] for f in fs) / w
        prev = list(hosts)
        hosts = sorted(prev, key=lambda h: (bary("host", h, task_order), prev.index(h)))
        rest = sorted(task_order[1:] if task_order[0] == "main" else task_order,
                      key=lambda t: (bary("task", t, hosts), task_order.index(t)))
        task_order = (["main"] if task_order[0] == "main" else []) + rest
    nmap = {n["host"]: n for n in nodes}
    pad = 8.0

    def col_layout(keys: list, size: dict, minh: float) -> dict:
        hs = {k: max(minh, size[k] + 2 * pad) for k in keys}
        return hs

    tsize = {t: sum(th[id(f)] for f in flows if f["task"] == t) for t in task_order}
    vsize = {h: sum(th[id(f)] for f in flows if f["host"] == h) for h in hosts}
    th_h = col_layout(task_order, tsize, tmin)
    vh_h = col_layout(hosts, vsize, vmin)
    stack = sum(th[id(f)] for f in flows)
    hh = max(stack + 2 * pad, (190 if canary_label else 150) if not compact else 110)
    col_h = [hh, sum(th_h.values()) + gap * (len(task_order) - 1), sum(vh_h.values()) + gap * (len(hosts) - 1)]
    top_pad = 12
    H = max(col_h) + 2 * top_pad
    if compact:
        H = max(H, 262.0)  # before and after panels line up

    def place(keys: list, hs: dict, total_h: float) -> dict:
        y = top_pad + (H - 2 * top_pad - total_h) / 2
        out = {}
        for k in keys:
            out[k] = y
            y += hs[k] + gap
        return out

    ty = place(task_order, th_h, col_h[1])
    vy = place(hosts, vh_h, col_h[2])
    hy = top_pad + (H - 2 * top_pad - hh) / 2
    # stacking offsets
    by_src = sorted(flows, key=lambda f: (task_order.index(f["task"]), hosts.index(f["host"])))
    y = hy + (hh - stack) / 2
    src_y = {}
    for f in by_src:
        src_y[id(f)] = y
        y += th[id(f)]
    tin, tout = {}, {}
    for t in task_order:
        fs = [f for f in by_src if f["task"] == t]
        y = ty[t] + (th_h[t] - tsize[t]) / 2
        for f in fs:
            tin[id(f)] = y
            tout[id(f)] = y
            y += th[id(f)]
    vin = {}
    for h in hosts:
        fs = sorted([f for f in flows if f["host"] == h], key=lambda f: task_order.index(f["task"]))
        y = vy[h] + (vh_h[h] - vsize[h]) / 2
        for f in fs:
            vin[id(f)] = y
            y += th[id(f)]

    out = [f'<svg viewBox="0 0 {W} {H:.0f}" width="100%" role="img" aria-label="data flow" style="display:block">',
           '<defs>']
    for sev in ("green", "amber", "red"):
        out.append(f'<linearGradient id="{uid}g{sev}" gradientUnits="userSpaceOnUse" x1="{x0w}" y1="0" x2="{vx}" y2="0">'
                   f'<stop offset="0" stop-color="{COL["src"]}" stop-opacity=".55"/>'
                   f'<stop offset=".45" stop-color="{COL[sev]}" stop-opacity=".45"/>'
                   f'<stop offset="1" stop-color="{COL[sev]}" stop-opacity=".75"/></linearGradient>')
    out.append(f'<filter id="{uid}glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3"'
               f' result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
               f'<filter id="{uid}blur" x="-30%" y="-60%" width="160%" height="220%"><feGaussianBlur stdDeviation="9"/>'
               f'</filter><linearGradient id="{uid}hg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#4338ca"/>'
               f'<stop offset="1" stop-color="#1e1b4b"/></linearGradient></defs>')
    bands, parts = [], []
    for i, f in enumerate(by_src):
        n = nmap[f["host"]]
        sev = n["status"]
        t = th[id(f)]
        segs = [(x0w, src_y[id(f)], tx0, tin[id(f)]), (tx0 + tw, tout[id(f)], vx, vin[id(f)])]
        for (a, b, c, d) in segs:
            bands.append(f'<path d="{_band(a, b, c, d, t)}" fill="url(#{uid}g{sev})"/>')
            mid = _mid(a, b + t / 2, c, d + t / 2)
            if f["canary"]:
                w = max(4.5, min(9.0, t * .42))
                parts.append(f'<path class="pt" d="{mid}" stroke="{COL["canary"]}" stroke-width="{w:.1f}" '
                             f'stroke-dasharray="0.1 17.9" filter="url(#{uid}glow)" style="--d:{1.1 + (i % 3) * .2:.1f}s"/>')
            else:
                w = max(2.5, min(5.0, t * .3))
                parts.append(f'<path class="pt" d="{mid}" stroke="#ffffff" stroke-opacity=".55" stroke-width="{w:.1f}" '
                             f'stroke-dasharray="0.1 23.9" style="--d:{1.8 + (i % 3) * .3:.1f}s"/>')
    out += bands + parts
    # Hermes node
    fs_big = 18 if compact else 24
    out.append(f'<rect x="0" y="{hy:.1f}" width="{x0w}" height="{hh:.1f}" rx="20" fill="url(#{uid}hg)" stroke="#8b8cff" '
               f'stroke-opacity=".8" stroke-width="1.5"/>')
    cy = hy + hh / 2 - (16 if canary_label else 0)
    out.append(f'<text x="{x0w / 2:.0f}" y="{cy - (6 if compact else 10):.0f}" fill="#fff" font-size="{fs_big}" '
               f'font-weight="800" text-anchor="middle">Hermes</text>')
    out.append(f'<text x="{x0w / 2:.0f}" y="{cy + 16:.0f}" fill="#dfe2ff" '
               f'font-size="{12.5 if compact else 14}" text-anchor="middle">{e(tx["machine"])}</text>')
    if total_label:
        out.append(f'<text x="{x0w / 2:.0f}" y="{cy + (28 if compact else 40):.0f}" fill="#c7cbff" '
                   f'font-size="{11 if compact else 13.5}" font-weight="700" text-anchor="middle">{e(total_label)}</text>')
    if canary_label:
        cw = x0w - 20
        y_c = cy + 62
        out.append(f'<rect x="10" y="{y_c:.0f}" width="{cw:.0f}" height="44" rx="12" '
                   f'fill="rgba(255,225,77,.16)" stroke="{COL["canary"]}" stroke-dasharray="4 3"/>'
                   f'<text x="{x0w / 2:.0f}" y="{y_c + 17:.0f}" fill="#fff3b8" font-size="11.5" font-weight="700" '
                   f'text-anchor="middle" letter-spacing=".06em">{e(tx["canary_on"].upper())}</text>'
                   f'<text x="{x0w / 2:.0f}" y="{y_c + 35:.0f}" fill="{COL["canary"]}" font-size="14.5" '
                   f'font-weight="800" text-anchor="middle">{e(_trunc(canary_label, 20))}</text>')
    # task nodes
    for t in task_order:
        y0, h = ty[t], th_h[t]
        n_t = sum(f["n"] for f in flows if f["task"] == t)
        out.append(f'<rect x="{tx0}" y="{y0:.1f}" width="{tw}" height="{h:.1f}" rx="14" fill="#0c1222" '
                   f'stroke="{"#a5a6ff" if t == "main" else "#c084fc"}" stroke-opacity=".75" stroke-width="1.4"/>')
        mid_y = y0 + h / 2
        out.append(f'<text x="{tx0 + tw / 2:.0f}" y="{mid_y - 2:.0f}" fill="#fff" font-size="{14.5 if compact else 16}" '
                   f'font-weight="760" text-anchor="middle">{e(_trunc(task_word(t, lang), 16 if compact else 22))}</text>')
        sub = _pl(tx, n_t, "request" if t == "main" else "sidereq")
        out.append(f'<text x="{tx0 + tw / 2:.0f}" y="{mid_y + (16 if compact else 18):.0f}" fill="#e4d7ff" '
                   f'font-size="{13 if compact else 13.5}" text-anchor="middle">{e(sub)}</text>')
    # vendor nodes
    for h in hosts:
        n = nmap[h]
        y0, hgt = vy[h], vh_h[h]
        col = COL[n["status"]]
        hazard = n["status"] == "red"
        if hazard:
            out.append(f'<rect class="aura" x="{vx - 6}" y="{y0 - 6:.1f}" width="{vw + 12}" height="{hgt + 12:.1f}" rx="22" '
                       f'fill="none" stroke="{col}" stroke-width="10" filter="url(#{uid}blur)"/>')
        elif n["canary"]:
            out.append(f'<rect x="{vx - 3}" y="{y0 - 3:.1f}" width="{vw + 6}" height="{hgt + 6:.1f}" rx="19" '
                       f'fill="none" stroke="{COL["canary"]}" stroke-opacity=".35" stroke-width="6" '
                       f'filter="url(#{uid}blur)"/>')
        out.append(f'<rect x="{vx}" y="{y0:.1f}" width="{vw}" height="{hgt:.1f}" rx="16" '
                   f'fill="{"#1d0a12" if hazard else "#0b1220"}" stroke="{col}" stroke-opacity=".9" '
                   f'stroke-width="{2.2 if hazard else 1.5}"/>')
        out.append(f'<rect x="{vx}" y="{y0 + 12:.1f}" width="5" height="{max(10, hgt - 24):.1f}" rx="2.5" fill="{col}"/>')
        hq = n["hq"]
        agg = bool(n.get("agg"))
        model_word = "Modell" if lang == "de" else "model"
        sub_line = ((f"→ {n['mvendor']} {model_word}" if n.get("mvendor") else
                     ("→ unbekanntes Modell" if lang == "de" else "→ unknown model"))
                    if agg else str(n.get("dhost") or h))
        if agg:
            hq = f"{hq}→{n.get('mhq') or '?'}"
        if compact:
            yc = y0 + (hgt - 66) / 2
            out.append(f'<text x="{vx + 16}" y="{yc + 20:.0f}" fill="#fff" font-size="16.5" font-weight="800">'
                       f'{e(_trunc(str(n["vendor"]), 13))}</text>')
            out.append(f'<text x="{vx + 16}" y="{yc + 40:.0f}" fill="#e1e6f0" font-size="12.5" class="mono">'
                       f'{e(_trunc(sub_line, 21))}</text>')
            out.append(f'<text x="{vx + vw - 12}" y="{yc + 21:.0f}" fill="{col}" font-size="{14 if agg else 18}" '
                       f'font-weight="900" text-anchor="end">{e(hq)}</text>')
            word = tx["base_short"] if n["status"] == "green" else tx["extra_short"]
            out.append(f'<text x="{vx + 16}" y="{yc + 60:.0f}" fill="{col}" font-size="13.5" font-weight="800">'
                       f'{e(word)}</text>')
            continue
        y0 = y0 + max(0.0, (hgt - 104) / 2)  # centre the content block in tall nodes
        out.append(f'<text x="{vx + 22}" y="{y0 + 32:.0f}" fill="#fff" font-size="20" font-weight="800">'
                   f'{e(_trunc(str(n["vendor"]), 20))}</text>')
        line2 = f"{n.get('dhost') or h} {sub_line}" if agg else sub_line
        out.append(f'<text x="{vx + 22}" y="{y0 + 54:.0f}" fill="#dbe1ee" font-size="14" class="mono">'
                   f'{e(_trunc(line2, 34))}</text>')
        # country block
        cx = vx + vw - 18
        out.append(_globe(cx - (92 if agg else 70), y0 + 27, 9, col))
        out.append(f'<text x="{cx}" y="{y0 + 34:.0f}" fill="#fff" font-size="{19 if agg else 22}" font-weight="900" '
                   f'text-anchor="end">{e(hq)}</text>')
        cname = country_name(n.get("mhq") or "unknown", lang) if agg else country_name(hq, lang)
        out.append(f'<text x="{cx}" y="{y0 + 53:.0f}" fill="#d3d9e6" font-size="12.5" text-anchor="end">'
                   f'{e(cname)}</text>')
        # chips
        chips = []
        if n["canary"]:
            chips.append((tx["canary_on"], COL["canary"], "rgba(255,225,77,.16)"))
        if n["status"] == "green":
            chips.append((tx["baseline"], COL["green"], "rgba(46,229,157,.12)"))
        elif n["types"]:
            chips.append((tx["pii"] + ": " + ", ".join(f"{views.TYPE_WORD[lang].get(k, k)} {v}" for k, v in sorted(
                n["types"].items(), key=lambda kv: -kv[1])[:2]), COL["red"], "rgba(255,61,110,.16)"))
        else:
            chips.append((tx["extra"], COL[n["status"]], "rgba(255,197,61,.14)"))
        x = vx + 22
        cy2 = y0 + 66
        for label, c, bg in chips:
            w = 18 + 7.4 * len(label)
            if x + w > vx + vw - 10:
                break
            out.append(f'<rect x="{x:.0f}" y="{cy2:.0f}" width="{w:.0f}" height="25" rx="12.5" fill="{bg}" stroke="{c}" '
                       f'stroke-opacity=".8"/><text x="{x + w / 2:.0f}" y="{cy2 + 17:.0f}" fill="{c}" font-size="13" '
                       f'font-weight="800" text-anchor="middle">{e(label)}</text>')
            x += w + 8
    out.append("</svg>")
    return "".join(out)

# --------------------------------------------------------------------------- before / after


def compare_data(canaries: list[dict], records: list[dict]) -> Optional[dict]:
    """The two most recent canaries that were sent out at least once: {before, after}, each with
    public fields (id, name, created) and its sent groups. None if fewer than two."""
    with_hits = []
    for c in sorted(canaries or [], key=lambda c: float(c.get("created") or 0)):
        sent = views.trace_places(c, records, {})["sent"]
        if sent:
            with_hits.append({"id": c.get("id"), "name": c.get("name"), "created": c.get("created"), "sent": sent})
    if len(with_hits) < 2:
        return None
    return {"before": with_hits[-2], "after": with_hits[-1]}


def _panel_state(groups: list[dict], main: Optional[dict], lang: str = "en") -> tuple[str, list[str], int]:
    fb = _base_fallback(groups)
    extra = sorted({_glabel(g, lang) for g in groups if not g.get("local") and not _group_is_base(g, main, fb)})
    side = sum(int(g.get("count") or 0) for g in groups if g.get("kind") == "aux")
    return ("red" if extra else "green"), extra, side


def compare_html(cmp: dict, lang: str, main: Optional[dict]) -> str:
    tx = L10N[lang]
    panels = []
    vendor_sets = {}
    for key in ("before", "after"):
        p = cmp[key]
        sev, extra, side = _panel_state(p["sent"], main, lang)
        vendors_ = sorted({_glabel(g, lang) for g in p["sent"] if not g.get("local")})
        vendor_sets[key] = {_glabel(g, lang): (f"{g.get('hq')}→{g.get('mhq') or '?'}" if g.get("vkind") == "router"
                                               else str(g.get("hq") or "")) for g in p["sent"] if not g.get("local")}
        flows, nodes = _flows_from_groups(p["sent"], main)
        summary = tx["cmp_vendors"].format(v=f"<b>{e(_pl(tx, len(vendors_), 'vendor'))}</b>",
                                           s=e(_pl(tx, side, "sidereq")))
        if extra:
            summary += " · " + _join([f"<b>{e(x)}</b>" for x in extra], lang) + " " + e(tx["extra"])
        c = COL[sev]
        style = f"--pc:{c};--pc18:{c}2e;--pc55:{c}8c"
        panels.append(
            f'<div class="cmpp" style="{style}"><div class="cmph"><span class="tag">{e(tx[key])}</span>'
            f'<span class="nm">{e(p["name"])}</span><span class="tm">{e(views.when(p.get("created"), lang))}</span></div>'
            f'<div class="cmps">{summary}</div>'
            f'{sankey(flows, nodes, lang, uid="c" + key[0], compact=True)}</div>')
    gone = [f"{v} ({hq})" for v, hq in sorted(vendor_sets["before"].items()) if v not in vendor_sets["after"]]
    new = [f"{v} ({hq})" for v, hq in sorted(vendor_sets["after"].items()) if v not in vendor_sets["before"]]
    if new:
        delta = f'<div class="delta bad">{e(tx["cmp_new"].format(x=_join(new, lang)))}</div>'
    elif gone:
        delta = f'<div class="delta">{e(tx["cmp_gone"].format(x=_join(gone, lang)))}</div>'
    else:
        delta = f'<div class="delta">{e(tx["cmp_same"])}</div>'
    return (f'<section class="card" id="compare"><h2>{e(tx["cmp"])}</h2><p class="sub">{e(tx["cmp_sub"])}</p>'
            f'<div class="cmp">{"".join(panels)}</div>{delta}</section>')

# --------------------------------------------------------------------------- page


def canary_flow_since(canary: Optional[dict], compare: Optional[dict]) -> Optional[float]:
    """Start time for the Data flow diagram, or None for the normal window.

    With a before/after pair whose 'after' side is the traced (latest) canary, the main diagram starts
    when that canary was created: hero, flow and comparison then tell one story (red before, green
    after) instead of mixing pre-change traffic into the current picture."""
    if not canary or not compare:
        return None
    if (compare.get("after") or {}).get("id") != canary.get("id"):
        return None
    try:
        ts = float(canary.get("created") or 0)
    except (TypeError, ValueError):
        return None
    return ts or None


def _chip(n: Any, label: str) -> str:
    return f'<span class="chip"><b>{e(n)}</b>{e(label)}</span>'


def _pchip(tx: dict, n: int, key: str) -> str:
    """Chip with the correct singular or plural word (1 vendor, 2 vendors)."""
    return _chip(n, tx[key + ("1" if int(n) == 1 else "N")])


def _country_chip(countries: list[str], lang: str) -> str:
    return ('<span class="chip"><svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true">'
            f'{_globe(10, 10, 8, "#dfe4ef")}</svg>' + e(", ".join(_country_label(c, lang) for c in countries))
            + "</span>")


def _window_chips(agg: dict, tx: dict, lang: str) -> list[str]:
    countries = agg.get("countries") or []
    vendors_ = {views.dest_label(d, lang) for d in agg.get("destinations") or [] if not d.get("local")}
    out = [_pchip(tx, int(agg.get("requests") or 0), "request"), _pchip(tx, len(vendors_), "vendor"),
           _pchip(tx, int(agg.get("side_requests") or 0), "sidereq")]
    if countries:
        out.append(_country_chip(countries, lang))
    return out


def build_html(*, lang: str, agg: dict, scope: str, check: Optional[dict], trace: Optional[dict],
               canary: Optional[dict], compare: Optional[dict] = None, main: Optional[dict] = None,
               region: str = "", generated: Optional[float] = None, flow_agg: Optional[dict] = None,
               flow_scope: str = "") -> str:
    """The leak map page. Scopes are explicit and never mixed inside one block:

    hero = the latest canary only (or, without a canary, the window ``agg``/``scope``); the Data flow
    card, its stats and the personal data bars = ``flow_agg``/``flow_scope`` when given (requests since
    the latest canary, see canary_flow_since), otherwise the window."""
    tx = L10N[lang]
    stored = (trace or {}).get("rest", {}).get("places", []) if trace else []
    summ = (check or {}).get("summary", {"red": 0, "amber": 0, "green": 0})
    gen = time.strftime("%Y-%m-%d %H:%M", time.localtime(generated or time.time()))
    since_mode = flow_agg is not None
    fagg = flow_agg if since_mode else agg
    fscope = flow_scope if since_mode else scope

    def pill(sev: str, n: Any) -> str:
        return (f'<span class="pill" style="background:{COL[sev]}30;color:{COL[sev]};border:1px solid {COL[sev]}99">'
                f'{e(n)} {e(tx["sev_" + sev])}</span>')

    v = verdict(lang, agg, trace, main, region)
    sent = (trace or {}).get("sent") or []
    if trace is not None and sent:
        # hero = the latest canary only: every number here comes from its trace groups
        carried = sum(int(g.get("count") or 0) for g in sent)
        chips = [f'<span class="cl">{e(tx["hero_scope"])}</span>', _pchip(tx, carried, "c_req"),
                 _pchip(tx, len(v["vendors"]), "vendor"), _pchip(tx, int(v["side"]), "sidereq")]
        if v["countries"]:
            chips.append(_country_chip(v["countries"], lang))
    elif trace is None:
        chips = [f'<span class="cl">{e(tx["all_req"].format(scope=scope))}</span>'] + _window_chips(agg, tx, lang)
    else:
        chips = []  # canary not sent yet: window numbers belong to the Data flow card
    idc = ""
    if canary and trace is not None:
        idc = (f'<div class="idc"><div class="l">{e(tx["fake"])}</div><div class="n">{e(canary.get("name"))}</div>'
               f'<div class="mono">{e(canary.get("email"))}</div><div class="mono">{e(canary.get("phone"))}</div></div>')
    subs = "".join(f'<p class="vs {cls}">{s}</p>' for s, cls in v["subs"])
    chips_html = f'<div class="chips">{"".join(chips)}</div>' if chips else ""
    hero = (f'<section class="hero" style="{_hc(v["sev"])}"><div><h2 class="vh">{v["head"]}</h2>{subs}'
            f'{chips_html}</div><div class="stamp">'
            f'<div class="badge">{e(tx["stamp_" + v["sev"]])}</div>{idc}</div></section>')

    flows, nodes = _flows_from_agg(fagg, trace)
    shown = {n["status"] for n in nodes if any(f["host"] == n["host"] and f["n"] > 0 for f in flows)}
    leg = [f'<span><i style="background:{COL["green"]}"></i>{e(tx["legend_main"])}</span>']
    if "amber" in shown:
        leg.append(f'<span><i style="background:{COL["amber"]}"></i>{e(tx["legend_extra"])}</span>')
    if "red" in shown:
        leg.append(f'<span><i style="background:{COL["red"]}"></i>{e(tx["legend_red"])}</span>')
    if any(f["canary"] for f in flows):
        leg.append(f'<span><i style="background:repeating-linear-gradient(90deg,{COL["canary"]} 0 5px,transparent '
                   f'5px 10px)"></i>{e(tx["legend_canary"])}</span>')
    legend = f'<div class="legend">{"".join(leg)}</div>'
    # The canary name sits on the Hermes node only when the whole diagram follows that canary.
    flow_svg = sankey(flows, nodes, lang, uid="m",
                      canary_label=(str(canary["name"]) if canary and trace is not None and since_mode else ""),
                      total_label=_pl(tx, int(fagg.get("requests") or 0), "request"))
    flow_stats = (f'<div class="stats"><span class="cl">{e(tx["all_req"].format(scope=fscope))}</span>'
                  f'{"".join(_window_chips(fagg, tx, lang))}</div>') if fagg.get("requests") else ""
    flow_sub = tx["flow_sub"].format(scope=fscope) + (" " + tx["flow_since"] if since_mode else "")

    rest_sub = tx["rest_sub_c"].format(name=canary.get("name")) if (canary and trace is not None) else tx["rest_sub"]
    if trace:
        rows = []
        for p in stored:
            label = views._place_text(p, lang)
            name, _, rest = label.partition(": ")
            rows.append(f'<div class="place"><span class="k mono">{e(name)}</span><span class="c">{e(rest)}</span></div>')
        rest_html = "".join(rows) or '<div class="empty">-</div>'
    else:
        rest_html = f'<div class="empty">{e(tx["rest_none"])}</div>'

    types = fagg.get("types") or {}
    maxt = max(types.values()) if types else 1
    typ_html = "".join(
        f'<div class="typ"><span>{e(views.TYPE_WORD[lang].get(k, k))}</span><div class="bar"><div style="width:'
        f'{max(4, 100 * v_ / maxt):.0f}%"></div></div><span class="n">{e(v_)}</span></div>'
        for k, v_ in sorted(types.items(), key=lambda kv: -kv[1])) or f'<div class="empty">{e(tx["types_none"])}</div>'
    if fagg.get("incomplete"):
        typ_html += f'<div class="empty" style="color:#ffd27a">{e(tx["incomplete"].format(n=fagg["incomplete"]))}</div>'

    find_rows, greens = [], []
    for f in (check or {}).get("findings", []):
        col = COL[f["severity"]]
        title = f["title"].get(lang) or f["title"]["en"]
        if f["severity"] == "green":
            greens.append(f'<span class="gchip" title="{e(f["why"].get(lang) or f["why"]["en"])}">'
                          f'<i style="background:{col}"></i>{e(title)}</span>')
            continue
        cmds = views.fix_cmds(f)
        fix = (f'<div class="fixl">{e(tx["fix"])}</div>' if cmds else "") + "".join(
            f'<div class="cmd mono"><span class="p">$</span>{e(c)}</div>' for c in cmds)
        if not cmds and f["fix"].get("manual"):
            fix = (f'<div class="fixl">{e(tx["fix"])}</div><div class="w" style="margin-top:2px">'
                   f'{_inline_code(f["fix"]["manual"].get(lang) or f["fix"]["manual"]["en"])}</div>')
            if f["fix"].get("warning"):
                fix += (f'<div class="w" style="margin-top:6px;color:#ffb3c4;font-weight:700">'
                        f'{e(f["fix"]["warning"].get(lang) or f["fix"]["warning"]["en"])}</div>')
        find_rows.append(f'<div class="row"><span class="dot" style="background:{col};color:{col}"></span><div style="min-width:0">'
                         f'<div class="t">{e(title)} <span class="fid mono">{e(f["id"])}</span></div>'
                         f'<div class="w">{e(f["why"].get(lang) or f["why"]["en"])}</div>{fix}</div></div>')
    check_html = "".join(find_rows)
    if greens:
        check_html += (f'<div class="greens"><div class="gh">{e(tx["green_head"].format(n=len(greens)))}</div>'
                       f'{"".join(greens)}</div>')
    check_html = check_html or '<div class="empty">/xray check</div>'
    cmp_html = compare_html(compare, lang, main) if compare else ""

    return f"""<!doctype html><html lang="{e(lang)}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Privacy X-ray</title>
<style>{CSS}</style></head><body><div class="wrap">
<header><div class="brand">{LOGO}<div><h1>Privacy X-ray</h1><p>{e(tx["sub"])}</p></div></div>
<div class="meta">{e(tx["generated"])} {e(gen)}</div></header>
{hero}
<section class="card" id="flow"><h2>{e(tx["flow"])}</h2><p class="sub">{e(flow_sub)}</p>{flow_stats}
{flow_svg}{legend}</section>
{cmp_html}
<div class="grid2"><section class="card"><h2>{e(tx["rest"])}</h2><p class="sub">{e(rest_sub)}</p>{rest_html}</section>
<section class="card"><h2>{e(tx["types"])}</h2><p class="sub">{e(tx["types_sub"].format(scope=fscope))}</p>{typ_html}</section></div>
<section class="card" id="check"><h2>{e(tx["check"])}{pill("red", summ["red"])}{pill("amber", summ["amber"])}{pill("green", summ["green"])}</h2>{check_html}</section>
<footer>{e(tx["limits"])}</footer></div></body></html>"""
