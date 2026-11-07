"""Read-only configuration audit: the paths Hermes itself configures on which content leaves this machine.

Inputs are the merged Hermes config (``hermes_cli.config.load_config_readonly``, public API) and a
few files in HERMES_HOME that never contain secrets (gateway_state.json, file names under
sessions/). Nothing here writes; applying a fix is a separate, explicitly confirmed step.

How an auxiliary ("side") task picks its model was read from the Hermes source
(agent/auxiliary_client.py ``_resolve_auto_route``, v0.22.7): provider ``auto`` or empty means
"my main provider and main model" (title generation may opt into the provider's fast model with
``prefer_fast_model``); if the main provider is unavailable, the configured fallback chain is used.
An explicit ``provider``/``model``/``base_url`` on ``auxiliary.<task>`` wins. If that fails, Hermes
tries ``auxiliary.<task>.fallback_chain`` (``_try_configured_fallback_chain``) before the main chain.

Aggregators (OpenRouter and the other hosts in vendors.py with kind ``router``): the recipient is the
aggregator AND the upstream model vendor named by the model id (``deepseek/...``). A side task is an
extra recipient when either differs from the main route. Who finally processes a request behind an
aggregator is not visible to a plugin.

Web tools (tools/web_tools_rescue.py, agent/web_search_registry.py): ``web.search_backend`` /
``web.extract_backend`` fall back to ``web.backend``, then to an auto-detected vendor, then to the
keyless free tier (Exa, Parallel, Firecrawl, Keenable) when ``web.keyless_fallback`` is on. With
``web.keyless_rescue`` on (default), a call that fails on the chosen backend is retried once on that
keyless tier, so even a self-hosted SearXNG can hand a query to a third party.
"""
from __future__ import annotations

import contextlib
import io
import os
import time
from pathlib import Path
from typing import Any, Optional

from . import vendors

# Side tasks that receive (parts of) the conversation itself.
CONTEXT_TASKS = {"compression", "title_generation", "background_review", "review", "moa_reference",
                 "moa_aggregator", "goal_judge", "memory_query_rewrite", "voice_chat", "monitor", "session_search"}
# Short descriptions of what a side task sends, English / German.
TASK_INFO = {
    "compression": ("older chat history (for summarizing)", "ältere Chat-Teile (zum Zusammenfassen)"),
    "title_generation": ("the first messages of each chat (for its title)", "die ersten Nachrichten jedes Chats (für den Titel)"),
    "vision": ("images and screenshots you share", "Bilder und Screenshots"),
    "background_review": ("the conversation (reviewed for memory and skills)", "den Chat (Auswertung für Gedächtnis und Skills)"),
    "review": ("the conversation (for review)", "den Chat (zur Prüfung)"),
    "approval": ("commands that need approval", "freizugebende Befehle"),
    "goal_judge": ("the goal and recent turns", "das Ziel und die letzten Züge"),
    "memory_query_rewrite": ("your message (to search memory)", "deine Nachricht (für die Gedächtnissuche)"),
    "moa_reference": ("the full request (for extra models)", "die ganze Anfrage (für weitere Modelle)"),
    "moa_aggregator": ("the full request and the drafts", "die ganze Anfrage samt Entwürfen"),
    "mcp": ("MCP tool output", "Ausgaben von MCP-Werkzeugen"),
    "skills_hub": ("skill texts", "Skill-Texte"),
    "curator": ("skill texts", "Skill-Texte"),
    "voice_chat": ("spoken conversation turns", "gesprochene Chat-Züge"),
    "monitor": ("conversation activity", "Chat-Aktivität"),
    "session_search": ("past chats you search (for summarizing)", "durchsuchte alte Chats (zum Zusammenfassen)"),
    "web_extract": ("web pages the agent reads (for summarizing)", "gelesene Webseiten (zum Zusammenfassen)"),
    "kanban_decomposer": ("task descriptions", "Aufgabenbeschreibungen"),
    "triage_specifier": ("task descriptions", "Aufgabenbeschreibungen"),
    "profile_describer": ("profile descriptions", "Profilbeschreibungen"),
    "tts_audio_tags": ("answers to be read aloud", "vorzulesende Antworten"),
}
# Model id -> the model vendor behind an aggregator: see vendors.model_vendor.
KEYLESS_RING = ("Exa", "Parallel", "Firecrawl", "Keenable")
WEB_VENDORS = {"ddgs": ("ddgs (meta search: DuckDuckGo, Bing, Brave and others)",
                        "ddgs (Metasuche: DuckDuckGo, Bing, Brave und andere)"),
               "firecrawl": ("Firecrawl (US)",) * 2, "tavily": ("Tavily (US)",) * 2, "exa": ("Exa (US)",) * 2,
               "perplexity": ("Perplexity (US)",) * 2, "brave-free": ("Brave (US)",) * 2,
               "parallel": ("Parallel (US)",) * 2, "xai": ("xAI (US)",) * 2, "keenable": ("Keenable",) * 2,
               "openai-native": ("OpenAI (US), as part of the main request",
                                 "OpenAI (US), als Teil der Hauptanfrage"),
               "searxng": ("a SearXNG instance", "eine SearXNG-Instanz"),
               "nous": ("Nous Tool Gateway (US)",) * 2}
TTS_VENDORS = {"edge": "Microsoft (Edge TTS, US)", "elevenlabs": "ElevenLabs (US)", "openai": "OpenAI (US)",
               "gemini": "Google (US)", "google": "Google (US)", "minimax": "MiniMax (CN)",
               "mistral": "Mistral AI (FR)", "xai": "xAI (US)", "cartesia": "Cartesia (US)",
               "deepgram": "Deepgram (US)"}
STT_VENDORS = {"openai": "OpenAI (US)", "groq": "Groq (US)", "elevenlabs": "ElevenLabs (US)",
               "deepgram": "Deepgram (US)", "mistral": "Mistral AI (FR)", "gemini": "Google (US)",
               "assemblyai": "AssemblyAI (US)"}
MEMORY_CLOUD = {"honcho", "mem0", "supermemory", "zep", "retaindb", "byterover", "letta", "openmemory"}
MEMORY_LOCAL = {"holographic", "builtin", "local", "file", "sqlite"}
TTS_LOCAL = {"kittentts", "neutts", "piper", "kokoro", "local", "say", "espeak"}
STT_LOCAL = {"local", "faster-whisper", "whisper", "whisper.cpp"}
PLATFORMS = {
    "telegram": ("Telegram", "AE"), "discord": ("Discord", "US"), "whatsapp": ("Meta (WhatsApp)", "US"),
    "slack": ("Slack (Salesforce)", "US"), "signal": ("Signal", "US"), "teams": ("Microsoft Teams", "US"),
    "sms": ("SMS gateway", "unknown"), "email": ("your mail provider", "unknown"),
    "matrix": ("your Matrix homeserver", "unknown"), "mattermost": ("your Mattermost server", "unknown"),
    "feishu": ("Feishu (ByteDance)", "CN"), "dingtalk": ("DingTalk (Alibaba)", "CN"),
    "wecom": ("WeCom (Tencent)", "CN"), "bluebubbles": ("Apple iMessage via BlueBubbles", "US"),
    "google_chat": ("Google Chat", "US"), "line": ("LINE", "JP"),
}
REDACT_PLATFORMS = {"whatsapp", "signal", "telegram", "bluebubbles"}


def L(en: str, de: str) -> dict:
    return {"en": en, "de": de}


def _d(x: Any) -> dict:
    return x if isinstance(x, dict) else {}


def _s(x: Any) -> str:
    return str(x or "").strip()


def load_config() -> dict:
    try:
        from hermes_cli.config import load_config_readonly  # public plugin API
        cfg = load_config_readonly()
        return cfg if isinstance(cfg, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def default_config() -> dict:
    try:
        from hermes_cli.config import DEFAULT_CONFIG
        return DEFAULT_CONFIG if isinstance(DEFAULT_CONFIG, dict) else {}
    except Exception:  # noqa: BLE001
        return {}

# --------------------------------------------------------------------------- routes


def _custom_base_url(cfg: dict, name: str) -> str:
    name = name.split(":", 1)[1] if name.startswith("custom:") else name
    entry = _d(_d(cfg.get("providers")).get(name))
    url = _s(entry.get("api") or entry.get("base_url") or entry.get("url"))
    if url:
        return url
    for item in cfg.get("custom_providers") or []:
        if isinstance(item, dict) and _s(item.get("name")) == name:
            return _s(item.get("base_url") or item.get("api"))
    return ""


def route(cfg: dict, provider: str, model: str, base_url: str) -> dict:
    """Destination record for a provider/model/base_url triple (no network, config only)."""
    p = _s(provider).lower()
    url = _s(base_url)
    if not url and p and (p.startswith("custom:") or p in _d(cfg.get("providers"))):
        url = _custom_base_url(cfg, p)
    host = vendors.host_of(url) if url else vendors.PROVIDER_HOSTS.get(p.split(":", 1)[0], "")
    info = vendors.with_model(vendors.classify(host, p), model)
    return {"provider": p or "unknown", "model": _s(model), "base_url": url, **info}


def main_route(cfg: dict) -> dict:
    m = cfg.get("model")
    if isinstance(m, str):
        m = {"default": m}
    m = _d(m)
    return route(cfg, _s(m.get("provider")), _s(m.get("default") or m.get("model")), _s(m.get("base_url")))


def aux_tasks(cfg: dict) -> list[str]:
    names = set()
    for src in (_d(default_config().get("auxiliary")), _d(cfg.get("auxiliary"))):
        names |= {k for k, v in src.items() if isinstance(v, dict)}
    return sorted(names)


def aux_route(cfg: dict, task: str, main: dict) -> dict:
    t = _d(_d(cfg.get("auxiliary")).get(task))
    if t.get("enabled") is False:
        return {"disabled": True, **main}
    p, model, url = _s(t.get("provider")).lower(), _s(t.get("model")), _s(t.get("base_url"))
    if url:
        r = route(cfg, p or "custom", model, url)
    elif p in ("", "auto"):
        r = dict(main)
        r["inherits_main"] = True
        if task == "title_generation" and t.get("prefer_fast_model") is True:
            r["model"] = "fast model of " + main.get("provider", "")
            if vendors.is_aggregator(r):
                # Hermes picks the fast model from the aggregator's live catalog at runtime.
                r["mvendor"], r["mhq"], r["fast_unknown"] = "", "", True
    elif p == "main":
        r = dict(main)
        r["model"] = model or main.get("model", "")
        r["inherits_main"] = True
        if model:
            r = vendors.with_model(r, model) | {"inherits_main": True}
    else:
        r = route(cfg, p, model, "")
    r["pinned"] = {k: v for k, v in (("provider", p), ("model", model), ("base_url", url)) if v}
    return r


def same_recipient(a: dict, b: dict) -> bool:
    """Same recipient: see vendors.same_route (aggregators also need the same model vendor)."""
    return vendors.same_route(a, b)


def who(r: dict, lang: str = "en") -> str:
    """'DeepSeek (vendor HQ CN)' or 'OpenRouter → DeepSeek model (vendor HQ US / CN)'."""
    word = "Firmensitz" if lang == "de" else "vendor HQ"
    if vendors.is_aggregator(r):
        mhq = r.get("mhq") or "unknown"
        return f"{vendors.route_label(r, lang)} ({word} {r.get('hq')} / {mhq})"
    return f"{r.get('vendor')} ({word} {r.get('hq')})"


def _agg_note(r: dict) -> dict:
    if not vendors.is_aggregator(r):
        return L("", "")
    return L(f" {r.get('vendor')} forwards it to the model's vendor or a hosting partner; which company finally "
             "processes it is not visible to privacy-xray.",
             f" {r.get('vendor')} leitet es an den Modellanbieter oder einen Hosting-Partner weiter; welche Firma es "
             "am Ende verarbeitet, kann privacy-xray nicht sehen.")

# --------------------------------------------------------------------------- findings


def _dest_text(r: dict) -> str:
    if r.get("local"):
        return f"{r.get('host') or 'local'} (local)"
    hq = r.get("hq")
    return f"{r.get('host')} ({r.get('vendor')}, vendor HQ {hq})"


def _finding(fid: str, severity: str, area: str, title: dict, why: dict, dest: Optional[dict] = None,
             sets: Optional[list] = None, manual: Optional[dict] = None, consequence: Optional[dict] = None,
             warning: Optional[dict] = None) -> dict:
    """``sets`` = what /xray fix --yes applies; ``manual`` = advice only, never applied by the plugin;
    ``consequence`` = side effects of the fix; ``warning`` = shown with a manual command that would
    delete data or otherwise cannot be undone."""
    fix: dict[str, Any] = {"sets": sets or [], "manual": manual}
    if consequence:
        fix["consequence"] = consequence
    if warning:
        fix["warning"] = warning
    return {"id": fid, "severity": severity, "area": area, "title": title, "why": why,
            "destination": dest, "fix": fix}


def check(cfg: Optional[dict] = None, home: Optional[Path] = None, region: str = "") -> dict:
    cfg = cfg if isinstance(cfg, dict) else load_config()
    home = home or _home()
    main = main_route(cfg)
    F: list[dict] = []

    # 1. main model
    reg = vendors.in_region(str(main.get("hq")), region)
    if reg is not False and vendors.is_aggregator(main):
        reg = vendors.in_region(str(main.get("mhq") or "unknown"), region)
    if main.get("local"):
        sev, why = "green", L("Your main model runs on this machine or your private network.",
                              "Dein Hauptmodell läuft auf diesem Rechner oder in deinem privaten Netz.")
    elif reg is False:
        sev, why = "amber", L(
            f"Every message, tool result and the system prompt go to {who(main)}. "
            f"That is outside your home region {region}.",
            f"Jede Nachricht, jedes Werkzeug-Ergebnis und der Systemprompt gehen an {who(main, 'de')}. "
            f"Das liegt außerhalb deiner Region {region}.")
    else:
        note = _agg_note(main)
        sev, why = "green", L(
            f"Baseline recipient you chose: every message goes to {who(main)}.{note['en']}",
            f"Von dir gewählter Grundempfänger: jede Nachricht geht an {who(main, 'de')}.{note['de']}")
    F.append(_finding("main.model", sev, "model", L("Main model", "Hauptmodell"), why, main,
                      manual=None if sev == "green" else L(
                          "Pick a local or in-region provider with `hermes model`.",
                          "Wähle mit `hermes model` einen lokalen Anbieter oder einen aus deiner Region.")))

    # 2. fallback providers
    for i, fb in enumerate(cfg.get("fallback_providers") or []):
        if not isinstance(fb, dict):
            continue
        r = route(cfg, _s(fb.get("provider")), _s(fb.get("model")), _s(fb.get("base_url")))
        same = same_recipient(r, main)
        F.append(_finding(
            f"fallback.{i}", "green" if (same or r.get("local")) else "amber", "model",
            L(f"Fallback model {i + 1}", f"Ersatzmodell {i + 1}"),
            L("Same recipient as the main model." if same else
              f"When the main model fails, the whole conversation goes to {who(r)}.",
              "Gleicher Empfänger wie das Hauptmodell." if same else
              f"Fällt das Hauptmodell aus, geht der ganze Chat an {who(r, 'de')}."),
            r, manual=None if same else L("Remove or replace it in `fallback_providers` with `hermes model`.",
                                          "Entferne oder ersetze es in `fallback_providers` per `hermes model`.")))

    # 3. auxiliary (side) tasks
    comp_enabled = _d(cfg.get("compression")).get("enabled", True) is not False
    for task in aux_tasks(cfg):
        r = aux_route(cfg, task, main)
        en_info, de_info = TASK_INFO.get(task, ("data for this side task", "Daten für diese Nebenaufgabe"))
        fid = f"aux.{task}"
        title = L(f"Side task: {task}", f"Nebenaufgabe: {task}")
        if r.get("disabled") or (task == "compression" and not comp_enabled):
            F.append(_finding(fid, "green", "side", title, L("Turned off.", "Ausgeschaltet."), None))
            continue
        fb_chain = _d(_d(cfg.get("auxiliary")).get(task)).get("fallback_chain")
        for i, fb in enumerate(fb_chain if isinstance(fb_chain, list) else []):
            if not isinstance(fb, dict) or not _s(fb.get("provider")):
                continue
            rf = route(cfg, _s(fb.get("provider")), _s(fb.get("model")), _s(fb.get("base_url")))
            if rf.get("local") or same_recipient(rf, main):
                continue
            F.append(_finding(
                f"{fid}.fallback.{i}", "amber", "side", L(f"Side task fallback: {task} {i + 1}", f"Ersatz für Nebenaufgabe: {task} {i + 1}"),
                L(f"When the side task fails, Hermes sends {en_info} to {who(rf)}.",
                  f"Scheitert die Nebenaufgabe, schickt Hermes {de_info} an {who(rf, 'de')}."), rf,
                manual=L(f"Remove the entry from `auxiliary.{task}.fallback_chain` in config.yaml.",
                         f"Entferne den Eintrag aus `auxiliary.{task}.fallback_chain` in der config.yaml.")))
        if r.get("fast_unknown") and not r.get("local"):
            F.append(_finding(fid, "amber", "side", title,
                              L(f"Uses the fast model of {r['vendor']}, chosen from its catalog at runtime; it may be "
                                f"another model vendor than your main model. Sends {en_info}. /xray map shows the real "
                                "model of every recorded request.",
                                f"Nutzt das schnelle Modell von {r['vendor']}, zur Laufzeit aus dessen Katalog gewählt; "
                                f"das kann ein anderer Modellanbieter sein als dein Hauptmodell. Sendet {de_info}. "
                                "/xray map zeigt das echte Modell jeder erfassten Anfrage."), r,
                              sets=[[f"auxiliary.{task}.prefer_fast_model", "false"]]))
            continue
        if r.get("local") or same_recipient(r, main):
            how = "inherits your main model" if r.get("inherits_main") else "pinned to the same recipient"
            how_de = "nutzt dein Hauptmodell" if r.get("inherits_main") else "fest auf denselben Empfänger gestellt"
            F.append(_finding(fid, "green", "side", title,
                              L(f"No extra recipient ({how}). Sends {en_info}.",
                                f"Kein zusätzlicher Empfänger ({how_de}). Sendet {de_info}."), r))
            continue
        sev = "red" if task in CONTEXT_TASKS else "amber"
        sets = [[f"auxiliary.{task}.provider", "auto"], [f"auxiliary.{task}.model", ""]]
        if r.get("pinned", {}).get("base_url"):
            sets.append([f"auxiliary.{task}.base_url", ""])
        note = _agg_note(r)
        F.append(_finding(
            fid, sev, "side", title,
            L(f"Extra recipient: sends {en_info} to {who(r)}, not to your main model.{note['en']}",
              f"Zusätzlicher Empfänger: sendet {de_info} an {who(r, 'de')}, nicht an dein Hauptmodell.{note['de']}"),
            r, sets=sets,
            consequence=L(f"The task then runs on your main model ({main.get('model') or main.get('vendor')}): "
                          "it may cost more and take longer than a small side model.",
                          f"Die Aufgabe läuft dann auf deinem Hauptmodell ({main.get('model') or main.get('vendor')}): "
                          "das kann mehr kosten und länger dauern als ein kleines Nebenmodell.")))

    # 4. delegation and cron models
    for key, label_en, label_de in (("delegation", "Subagents (delegate_task)", "Subagenten (delegate_task)"),
                                    ("cron", "Scheduled jobs (cron)", "Geplante Aufgaben (Cron)")):
        sec = _d(cfg.get(key))
        p = _s(sec.get("provider") or sec.get("model_provider"))
        if not p and not _s(sec.get("base_url")):
            continue
        r = route(cfg, p, _s(sec.get("model")), _s(sec.get("base_url")))
        same = same_recipient(r, main) or bool(r.get("local"))
        F.append(_finding(f"{key}.model", "green" if same else "amber", "model", L(label_en, label_de),
                          L("Same recipient as the main model." if same else
                            f"Tasks run on {who(r)}.",
                            "Gleicher Empfänger wie das Hauptmodell." if same else
                            f"Aufgaben laufen bei {who(r, 'de')}."), r,
                          sets=None if same else [[f"{key}.provider", ""], [f"{key}.model", ""]]))

    # 5. memory provider
    mem = _d(cfg.get("memory"))
    mp = _s(mem.get("provider")).lower()
    if not mp or mp in MEMORY_LOCAL:
        F.append(_finding("memory.provider", "green", "memory", L("Memory", "Gedächtnis"),
                          L("Built-in memory: MEMORY.md and USER.md on this machine (they are part of the system prompt).",
                            "Eingebautes Gedächtnis: MEMORY.md und USER.md auf diesem Rechner (Teil des Systemprompts)."), None))
    else:
        cloud = mp in MEMORY_CLOUD
        F.append(_finding("memory.provider", "red" if cloud else "amber", "memory", L("Memory", "Gedächtnis"),
                          L(f"External memory provider '{mp}' receives conversation turns to remember them"
                            + ("." if cloud else "; check where it stores them."),
                            f"Der externe Gedächtnis-Anbieter '{mp}' bekommt Chat-Züge zum Merken"
                            + ("." if cloud else "; prüfe, wo er sie speichert.")), None,
                          sets=[["memory.provider", ""]],
                          consequence=L(f"This turns the external memory '{mp}' off; Hermes then uses only its "
                                        "built-in memory. What the provider already stored stays there.",
                                        f"Das schaltet das externe Gedächtnis '{mp}' ab; Hermes nutzt dann nur sein "
                                        "eingebautes Gedächtnis. Was der Anbieter schon gespeichert hat, bleibt dort.")))

    # 6. web search, web extract and browser
    F.extend(_web_findings(_d(cfg.get("web"))))
    br = _d(cfg.get("browser"))
    cp = _s(br.get("cloud_provider")).lower()
    cdp_host = vendors.host_of(_s(br.get("cdp_url")))
    if cp and cp not in ("local", "none"):
        F.append(_finding("browser.cloud", "amber", "tools", L("Browser", "Browser"),
                          L(f"Pages the agent opens run in a cloud browser at {cp}.",
                            f"Seiten, die der Agent öffnet, laufen in einem Cloud-Browser bei {cp}."), None,
                          sets=[["browser.cloud_provider", "local"]]))
    elif cdp_host and not vendors.is_local_host(cdp_host):
        F.append(_finding("browser.cloud", "amber", "tools", L("Browser", "Browser"),
                          L(f"The browser is remote ({cdp_host}).", f"Der Browser läuft entfernt ({cdp_host})."), None))
    else:
        F.append(_finding("browser.cloud", "green", "tools", L("Browser", "Browser"),
                          L("Local browser.", "Lokaler Browser."), None))
    if br.get("use_real_profile") is True:
        F.append(_finding("browser.profile", "amber", "tools", L("Browser profile", "Browser-Profil"),
                          L("The agent browses with your real browser profile: logged-in sessions and cookies are in reach.",
                            "Der Agent surft mit deinem echten Browser-Profil: eingeloggte Sitzungen und Cookies sind erreichbar."),
                          None, sets=[["browser.use_real_profile", "false"]]))

    # 7. voice
    tts = _s(_d(cfg.get("tts")).get("provider")).lower()
    if tts and tts not in TTS_LOCAL:
        tv = TTS_VENDORS.get(tts, f"'{tts}'")
        F.append(_finding("voice.tts", "amber", "voice", L("Voice output (TTS)", "Sprachausgabe (TTS)"),
                          L(f"When answers are read aloud, their text goes to the TTS vendor {tv}.",
                            f"Werden Antworten vorgelesen, geht ihr Text an den TTS-Anbieter {tv}."), None))
    stt = _s(_d(cfg.get("stt")).get("provider")).lower()
    if stt and stt not in STT_LOCAL:
        sv = STT_VENDORS.get(stt, f"'{stt}'")
        F.append(_finding("voice.stt", "amber", "voice", L("Voice input (STT)", "Spracheingabe (STT)"),
                          L(f"Voice messages are transcribed by {sv}.",
                            f"Sprachnachrichten werden von {sv} verschriftet."), None,
                          sets=[["stt.provider", "local"]],
                          consequence=L("Local transcription needs faster-whisper installed "
                                        "(`pip install faster-whisper` in the Hermes environment); without it "
                                        "voice input stops working.",
                                        "Lokale Verschriftung braucht faster-whisper (`pip install faster-whisper` "
                                        "in der Hermes-Umgebung); ohne das geht die Spracheingabe nicht mehr.")))

    # 8. streaming (no extra destination, listed for completeness)
    streaming = _d(cfg.get("streaming")).get("enabled") is True
    F.append(_finding("streaming", "green", "delivery", L("Streaming", "Streaming"),
                      L(("On" if streaming else "Off") + ": streaming changes how fast answers appear, not where data goes.",
                        ("An" if streaming else "Aus") + ": Streaming ändert, wie schnell Antworten erscheinen, nicht wohin Daten gehen."),
                      None))

    # 9. messaging gateways
    connected = _connected_platforms(home)
    redact = _d(cfg.get("privacy")).get("redact_pii") is True
    for name in connected:
        vendor, hq = PLATFORMS.get(name, (name, "unknown"))
        if name in ("api_server", "webhook", "web", "desktop"):
            continue
        F.append(_finding(f"gateway.{name}", "amber", "delivery", L(f"Gateway: {name}", f"Gateway: {name}"),
                          L(f"Messages and answers pass through {vendor} (vendor HQ {hq}).",
                            f"Nachrichten und Antworten laufen über {vendor} (Firmensitz {hq})."), None))
    if any(n in REDACT_PLATFORMS for n in connected):
        F.append(_finding("privacy.redact_pii", "green" if redact else "amber", "delivery",
                          L("Chat partner IDs", "IDs der Chatpartner"),
                          L("User IDs are hashed and phone numbers removed before they reach the model." if redact else
                            "Raw user IDs and phone numbers of chat partners reach the model.",
                            "Nutzer-IDs werden gehasht und Telefonnummern entfernt, bevor sie das Modell erreichen." if redact else
                            "Rohe Nutzer-IDs und Telefonnummern der Chatpartner erreichen das Modell."), None,
                          sets=None if redact else [["privacy.redact_pii", "true"]]))

    # 10. local stores at rest
    dumps = _request_dumps(home)
    dump_env = os.environ.get("HERMES_DUMP_REQUESTS", "").strip().lower() in ("1", "true", "yes", "on")
    if dumps or dump_env:
        F.append(_finding("dumps", "red", "storage", L("Request dumps", "Request-Dumps"),
                          L(f"{len(dumps)} request dump file(s) in sessions/ hold complete prompts and auth headers."
                            + (" HERMES_DUMP_REQUESTS is on." if dump_env else ""),
                            f"{len(dumps)} Request-Dump-Datei(en) in sessions/ enthalten komplette Prompts und Auth-Header."
                            + (" HERMES_DUMP_REQUESTS ist an." if dump_env else "")), None,
                          manual=L("Turn HERMES_DUMP_REQUESTS off and delete sessions/request_dump_*.json yourself "
                                   "(privacy-xray never deletes).",
                                   "Schalte HERMES_DUMP_REQUESTS ab und lösche sessions/request_dump_*.json selbst "
                                   "(privacy-xray löscht nie).")))
    else:
        F.append(_finding("dumps", "green", "storage", L("Request dumps", "Request-Dumps"),
                          L("No request dumps on disk.", "Keine Request-Dumps auf der Platte."), None))
    sess = _d(cfg.get("sessions"))
    db = home / "state.db"
    size = _mb(db)
    days = sess.get("retention_days", 90)
    if sess.get("auto_prune") is True:
        F.append(_finding("sessions.retention", "green", "storage", L("Chat history", "Chat-Verlauf"),
                          L(f"Chats older than {days} days are pruned (state.db {size}).",
                            f"Chats älter als {days} Tage werden gelöscht (state.db {_mb(db, 'de')})."), None))
    else:
        # Never applied by the plugin: Hermes would delete old chats on its next start
        # (hermes_cli/cli_auto_maintenance.py). Deletion only on the user's own, literal decision.
        F.append(_finding("sessions.retention", "amber", "storage", L("Chat history", "Chat-Verlauf"),
                          L(f"Every chat is kept in state.db until you delete it ({size}).",
                            f"Jeder Chat bleibt in state.db, bis du ihn löschst ({_mb(db, 'de')})."), None,
                          manual=L("If you want old chats deleted automatically, run it yourself: "
                                   "`hermes config set sessions.auto_prune true`.",
                                   "Wenn alte Chats automatisch gelöscht werden sollen, führe es selbst aus: "
                                   "`hermes config set sessions.auto_prune true`."),
                          warning=L(f"Warning: on its next start Hermes then DELETES every chat older than {days} days "
                                    "(sessions.retention_days) from state.db and sessions/, for good. privacy-xray "
                                    "never runs this command.",
                                    f"Achtung: Beim nächsten Start LÖSCHT Hermes dann jeden Chat, der älter als {days} "
                                    "Tage ist (sessions.retention_days), aus state.db und sessions/, endgültig. "
                                    "privacy-xray führt diesen Befehl nie aus.")))
    level = _s(_d(cfg.get("logging")).get("level")).upper()
    if level == "DEBUG":
        F.append(_finding("logging.level", "amber", "storage", L("Log level", "Log-Stufe"),
                          L("DEBUG logs can contain message text.", "DEBUG-Logs können Nachrichtentext enthalten."),
                          None, sets=[["logging.level", "INFO"]]))

    order = {"red": 0, "amber": 1, "green": 2}
    F.sort(key=lambda f: (order.get(f["severity"], 3), f["area"], f["id"]))
    summary = {k: sum(1 for f in F if f["severity"] == k) for k in ("red", "amber", "green")}
    return {"ts": int(time.time()), "main": main, "region": region, "findings": F, "summary": summary}

def _web_name(backend: str, lang: str) -> str:
    names = WEB_VENDORS.get(backend)
    if names:
        return names[1] if lang == "de" else names[0]
    return f"'{backend}'"


def _web_findings(web: dict) -> list[dict]:
    """web.search, web.extract and web.rescue, following agent/web_search_registry.py and
    tools/web_tools_rescue.py (v0.22.7)."""
    out: list[dict] = []
    shared = _s(web.get("backend")).lower()
    sb = _s(web.get("search_backend")).lower() or shared
    eb = _s(web.get("extract_backend")).lower() or shared
    keyless = web.get("keyless_fallback", True) is not False
    rescue = keyless and web.get("keyless_rescue", True) is not False
    ring_en = ", ".join(KEYLESS_RING)
    ring_de = ring_en.replace(", Keenable", " und Keenable")
    searx_local = vendors.is_local_host(vendors.host_of(os.environ.get("SEARXNG_URL", "")))

    def auto(kind_en: str, kind_de: str) -> dict:
        tail_en = f"; with no web key at all, the keyless free tier ({ring_en})" if keyless else ""
        tail_de = f"; ganz ohne Web-Schlüssel die freie Stufe ohne Schlüssel ({ring_de})" if keyless else ""
        return L(f"an auto-detected {kind_en} vendor{tail_en}", f"einen automatisch gewählten {kind_de}{tail_de}")

    # search
    if sb == "searxng" and searx_local and not rescue:
        out.append(_finding("web.search", "green", "tools", L("Web search", "Websuche"),
                            L("Self-hosted SearXNG on your network, no third-party fallback.",
                              "Selbst betriebenes SearXNG in deinem Netz, ohne Ausweichen zu Dritten."), None))
    elif sb == "searxng" and searx_local:
        out.append(_finding("web.search", "amber", "tools", L("Web search", "Websuche"),
                            L("Self-hosted SearXNG on your network, but when a search fails there, Hermes retries "
                              f"that query once on the keyless free tier ({ring_en}): see web.rescue.",
                              "Selbst betriebenes SearXNG in deinem Netz, aber scheitert dort eine Suche, schickt "
                              f"Hermes diese Anfrage einmal an die freie Stufe ohne Schlüssel ({ring_de}): siehe web.rescue."),
                            None, manual=L("Turn the rescue off: see web.rescue.", "Ausweichen abschalten: siehe web.rescue.")))
    else:
        w = L(_web_name(sb, "en"), _web_name(sb, "de")) if sb else auto("search", "Suchanbieter")
        out.append(_finding("web.search", "amber", "tools", L("Web search", "Websuche"),
                            L(f"Search queries the agent writes go to {w['en']}; they can contain names from your chat.",
                              f"Suchanfragen des Agenten gehen an {w['de']}; sie können Namen aus deinem Chat enthalten."),
                            None,
                            manual=L("Self-host SearXNG and run `hermes config set web.search_backend searxng`.",
                                     "SearXNG selbst betreiben und `hermes config set web.search_backend searxng` ausführen.")))
    # extract
    w = L(_web_name(eb, "en"), _web_name(eb, "de")) if eb else auto("extract", "Anbieter zum Seitenlesen")
    out.append(_finding("web.extract", "amber", "tools", L("Web page reading", "Webseiten lesen"),
                        L(f"Web pages the agent reads (the URLs, and through them what you asked about) are fetched "
                          f"by {w['en']}.",
                          f"Webseiten, die der Agent liest (die URLs und damit, wonach du gefragt hast), holt Hermes "
                          f"über {w['de']}."), None,
                        manual=L("Pick an extract backend you trust with `hermes tools`; it is stored as "
                                 "`web.extract_backend`.",
                                 "Wähle mit `hermes tools` einen Anbieter, dem du vertraust; gespeichert wird er als "
                                 "`web.extract_backend`.")))
    # rescue
    if rescue and (sb or eb):
        out.append(_finding("web.rescue", "amber", "tools", L("Web fallback", "Web-Ausweichen"),
                            L(f"When the chosen web backend fails a call, Hermes retries that call once on the keyless "
                              f"free tier ({ring_en}), so the query or URL reaches one of them.",
                              f"Scheitert der gewählte Web-Anbieter bei einem Aufruf, versucht Hermes diesen Aufruf einmal "
                              f"über die freie Stufe ohne Schlüssel ({ring_de}); die Anfrage oder URL geht dann an einen davon."),
                            None, sets=[["web.keyless_rescue", "false"]],
                            consequence=L("A failed search or page fetch then stays failed instead of being retried "
                                          "elsewhere.",
                                          "Eine gescheiterte Suche oder ein gescheiterter Seitenabruf bleibt dann "
                                          "gescheitert, statt woanders wiederholt zu werden.")))
    return out

# --------------------------------------------------------------------------- helpers


def _home() -> Path:
    from .store import hermes_home
    return hermes_home()


def _mb(path: Path, lang: str = "en") -> str:
    try:
        size = f"{path.stat().st_size / 1_048_576:.1f} MB"
        return size.replace(".", ",") if lang == "de" else size
    except OSError:
        return "nicht vorhanden" if lang == "de" else "not found"


def _request_dumps(home: Path, cap: int = 10000) -> list[Path]:
    out: list[Path] = []
    try:
        for p in (home / "sessions").glob("request_dump_*.json"):
            out.append(p)
            if len(out) >= cap:
                break
    except OSError:
        pass
    return out


def _connected_platforms(home: Path) -> list[str]:
    from .store import read_json
    data = read_json(home / "gateway_state.json", {})
    if not isinstance(data, dict) or data.get("gateway_state") not in ("running", "starting", None):
        return []
    plats = _d(data.get("platforms"))
    return sorted(k for k, v in plats.items() if isinstance(v, dict) and v.get("state") == "connected")


def command_line(key: str, value: str) -> str:
    v = value if value not in ("",) else '""'
    if " " in v:
        v = f'"{v}"'
    return f"hermes config set {key} {v}"


def fix_commands(finding: dict) -> list[str]:
    return [command_line(k, v) for k, v in finding.get("fix", {}).get("sets") or []]


def apply_sets(sets: list) -> tuple[bool, str]:
    """Apply ``hermes config set`` steps in-process through the public ``set_config_value``.

    Same code path as the CLI command (validation, coercion, atomic save). Its console output is
    captured; a refusal (SystemExit) stops at that step."""
    try:
        from hermes_cli.config import set_config_value
    except Exception as exc:  # noqa: BLE001
        return False, f"hermes_cli.config not available: {exc}"
    log = io.StringIO()
    before = load_config()
    done: list[tuple[str, Any]] = []

    def _old(key: str) -> Any:
        cur: Any = before
        for part in str(key).split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        return cur

    def _rollback() -> str:
        # Best effort: put the steps that already ran back to their previous value.
        failed = []
        for key, old in reversed(done):
            try:
                with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                    set_config_value(key, "" if old is None else (str(old).lower() if isinstance(old, bool) else str(old)))
            except BaseException:  # noqa: BLE001
                failed.append(key)
        return (" Rolled back: " + ", ".join(k for k, _ in done if k not in failed)) if done else ""

    for key, value in sets:
        try:
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                set_config_value(str(key), str(value))
            done.append((str(key), _old(str(key))))
        except SystemExit:
            msg = log.getvalue().strip()[-400:] or f"refused: {key}"
            return False, msg + _rollback()
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"[:400] + _rollback()
    return True, log.getvalue().strip()[-600:]


def verify_sets(sets: list) -> bool:
    cfg = load_config()
    for key, value in sets:
        cur: Any = cfg
        for part in str(key).split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        want = {"true": True, "false": False}.get(str(value).lower(), value)
        if (cur if cur is not None else "") != want and str(cur if cur is not None else "") != str(value):
            return False
    return True
