"""Destination classification: host -> vendor and the country of the vendor's headquarters.

The country is the vendor's headquarters (as of 2026-11), NOT the place where a request is
processed: many vendors run data centers in several regions, and aggregators such as OpenRouter
forward a request to further model vendors. The label is meant as a first orientation, never as
a legal statement. Unknown hosts stay "unknown".

Aggregators (``kind == "router"``, the hosts Hermes itself flags ``is_aggregator``): the model id
names the upstream model vendor (``deepseek/deepseek-v4-flash`` -> DeepSeek). That is the vendor
whose model runs, as far as the plugin can tell; which company finally processes the request behind
the aggregator (the model vendor itself or a hosting partner) is not visible to a plugin.
"""
from __future__ import annotations

import ipaddress
from typing import Optional
from urllib.parse import urlparse

AS_OF = "2026-11"

# (host suffix, vendor, HQ country ISO code, kind)
# kind: model = model vendor, router = forwards to other vendors, cloud = cloud platform,
#       service = other online service (search, browser, voice, chat platform)
_HOSTS: tuple[tuple[str, str, str, str], ...] = (
    ("api.anthropic.com", "Anthropic", "US", "model"),
    ("anthropic.com", "Anthropic", "US", "model"),
    ("api.openai.com", "OpenAI", "US", "model"),
    ("chatgpt.com", "OpenAI", "US", "model"),
    ("openai.com", "OpenAI", "US", "model"),
    ("openrouter.ai", "OpenRouter", "US", "router"),
    ("ai-gateway.vercel.sh", "Vercel AI Gateway", "US", "router"),
    ("api.kilo.ai", "Kilo Code", "unknown", "router"),
    ("opencode.ai", "OpenCode", "unknown", "router"),
    ("router.huggingface.co", "Hugging Face", "US", "router"),
    ("novita.ai", "Novita AI", "US", "router"),
    ("api.kimi.com", "Moonshot AI", "CN", "model"),
    ("kimi.com", "Moonshot AI", "CN", "model"),
    ("stepfun.ai", "StepFun", "CN", "model"),
    ("stepfun.com", "StepFun", "CN", "model"),
    ("lkeap.cloud.tencent.com", "Tencent Cloud", "CN", "cloud"),
    ("tencentmaas.com", "Tencent Cloud", "CN", "cloud"),
    ("portal.qwen.ai", "Alibaba Cloud (Qwen)", "CN", "model"),
    ("chat.qwen.ai", "Alibaba Cloud (Qwen)", "CN", "model"),
    ("integrate.api.nvidia.com", "NVIDIA", "US", "cloud"),
    ("ollama.com", "Ollama", "US", "cloud"),
    ("api.arcee.ai", "Arcee AI", "US", "model"),
    ("api.gmi-serving.com", "GMI Cloud", "US", "cloud"),
    ("api.upstage.ai", "Upstage", "KR", "model"),
    ("nousresearch.com", "Nous Research", "US", "model"),
    ("generativelanguage.googleapis.com", "Google", "US", "model"),
    ("aiplatform.googleapis.com", "Google Cloud", "US", "cloud"),
    ("googleapis.com", "Google", "US", "cloud"),
    ("api.deepseek.com", "DeepSeek", "CN", "model"),
    ("deepseek.com", "DeepSeek", "CN", "model"),
    ("api.mistral.ai", "Mistral AI", "FR", "model"),
    ("mistral.ai", "Mistral AI", "FR", "model"),
    ("api.x.ai", "xAI", "US", "model"),
    ("x.ai", "xAI", "US", "model"),
    ("api.groq.com", "Groq", "US", "model"),
    ("together.xyz", "Together AI", "US", "model"),
    ("fireworks.ai", "Fireworks AI", "US", "model"),
    ("githubcopilot.com", "GitHub (Microsoft)", "US", "model"),
    ("openai.azure.com", "Microsoft Azure", "US", "cloud"),
    ("azure.com", "Microsoft Azure", "US", "cloud"),
    ("amazonaws.com", "Amazon Web Services", "US", "cloud"),
    ("api.z.ai", "Z.ai (Zhipu)", "CN", "model"),
    ("bigmodel.cn", "Zhipu AI", "CN", "model"),
    ("moonshot.ai", "Moonshot AI", "CN", "model"),
    ("moonshot.cn", "Moonshot AI", "CN", "model"),
    ("minimax.io", "MiniMax", "CN", "model"),
    ("minimaxi.com", "MiniMax", "CN", "model"),
    ("aliyuncs.com", "Alibaba Cloud", "CN", "cloud"),
    ("xiaomimimo.com", "Xiaomi", "CN", "model"),
    ("huggingface.co", "Hugging Face", "US", "model"),
    ("cerebras.ai", "Cerebras", "US", "model"),
    ("deepinfra.com", "DeepInfra", "US", "model"),
    ("cohere.com", "Cohere", "CA", "model"),
    ("cohere.ai", "Cohere", "CA", "model"),
    ("perplexity.ai", "Perplexity", "US", "service"),
    ("aihosting.mittwald.de", "Mittwald", "DE", "cloud"),
    ("mittwald.de", "Mittwald", "DE", "cloud"),
    ("scaleway.ai", "Scaleway", "FR", "cloud"),
    ("scw.cloud", "Scaleway", "FR", "cloud"),
    ("ionos.com", "IONOS", "DE", "cloud"),
    ("ovh.net", "OVHcloud", "FR", "cloud"),
    ("infomaniak.com", "Infomaniak", "CH", "cloud"),
    ("nebius.ai", "Nebius", "NL", "cloud"),
    ("nebius.com", "Nebius", "NL", "cloud"),
    ("elevenlabs.io", "ElevenLabs", "US", "service"),
    ("firecrawl.dev", "Firecrawl", "US", "service"),
    ("tavily.com", "Tavily", "US", "service"),
    ("exa.ai", "Exa", "US", "service"),
    ("duckduckgo.com", "DuckDuckGo", "US", "service"),
    ("search.brave.com", "Brave", "US", "service"),
    ("browserbase.com", "Browserbase", "US", "service"),
    ("browser-use.com", "Browser Use", "US", "service"),
)

# Provider ids as Hermes names them -> default host (used when a config entry has no base_url).
PROVIDER_HOSTS: dict[str, str] = {
    "anthropic": "api.anthropic.com", "openai": "api.openai.com", "openai-api": "api.openai.com",
    "openai-codex": "chatgpt.com", "codex": "chatgpt.com", "openrouter": "openrouter.ai",
    "nous": "inference-api.nousresearch.com", "gemini": "generativelanguage.googleapis.com",
    "google": "generativelanguage.googleapis.com", "google-gemini-cli": "generativelanguage.googleapis.com",
    "vertex": "aiplatform.googleapis.com", "deepseek": "api.deepseek.com", "mistral": "api.mistral.ai",
    "xai": "api.x.ai", "xai-oauth": "api.x.ai", "groq": "api.groq.com", "together": "api.together.xyz",
    "fireworks": "api.fireworks.ai", "copilot": "api.githubcopilot.com",
    "github-copilot": "api.githubcopilot.com", "zai": "api.z.ai", "kimi-coding": "api.moonshot.ai",
    "moonshot": "api.moonshot.ai", "kimi": "api.moonshot.ai", "minimax": "api.minimax.io",
    "alibaba": "dashscope-intl.aliyuncs.com", "dashscope": "dashscope-intl.aliyuncs.com",
    "qwen": "dashscope-intl.aliyuncs.com", "xiaomi": "api.xiaomimimo.com",
    "huggingface": "router.huggingface.co", "cerebras": "api.cerebras.ai",
    "deepinfra": "api.deepinfra.com", "bedrock": "bedrock-runtime.amazonaws.com",
    "azure": "openai.azure.com", "azure-foundry": "openai.azure.com", "cohere": "api.cohere.com",
    "perplexity": "api.perplexity.ai", "ollama": "localhost", "lmstudio": "localhost",
    "llamacpp": "localhost", "llama.cpp": "localhost", "vllm": "localhost", "local": "localhost",
    "ollama-cloud": "ollama.com", "vercel": "ai-gateway.vercel.sh", "ai-gateway": "ai-gateway.vercel.sh",
    "kilo": "api.kilo.ai", "kilocode": "api.kilo.ai", "opencode": "opencode.ai", "opencode-zen": "opencode.ai",
    "opencode-go": "opencode.ai", "novita": "api.novita.ai", "hf": "router.huggingface.co",
    "stepfun": "api.stepfun.ai", "nvidia": "integrate.api.nvidia.com", "arcee": "api.arcee.ai",
    "gmi": "api.gmi-serving.com", "upstage": "api.upstage.ai", "tencent-tokenhub": "tokenhub.tencentmaas.com",
    "qwen-oauth": "portal.qwen.ai",
}

# Model id prefix (vendor/model) on an aggregator -> (model vendor, HQ). Lowercase keys.
MODEL_PREFIXES: dict[str, tuple[str, str]] = {
    "anthropic": ("Anthropic", "US"), "openai": ("OpenAI", "US"), "google": ("Google", "US"),
    "deepseek": ("DeepSeek", "CN"), "deepseek-ai": ("DeepSeek", "CN"), "qwen": ("Alibaba (Qwen)", "CN"),
    "alibaba": ("Alibaba (Qwen)", "CN"), "moonshotai": ("Moonshot AI", "CN"), "moonshot": ("Moonshot AI", "CN"),
    "z-ai": ("Zhipu (Z.ai)", "CN"), "zai-org": ("Zhipu (Z.ai)", "CN"), "thudm": ("Zhipu (Z.ai)", "CN"),
    "mistralai": ("Mistral AI", "FR"), "mistral": ("Mistral AI", "FR"), "x-ai": ("xAI", "US"), "xai": ("xAI", "US"),
    "meta-llama": ("Meta", "US"), "meta": ("Meta", "US"), "minimax": ("MiniMax", "CN"),
    "minimaxai": ("MiniMax", "CN"), "nousresearch": ("Nous Research", "US"), "cohere": ("Cohere", "CA"),
    "amazon": ("Amazon", "US"), "microsoft": ("Microsoft", "US"), "nvidia": ("NVIDIA", "US"),
    "perplexity": ("Perplexity", "US"), "xiaomi": ("Xiaomi", "CN"), "xiaomimimo": ("Xiaomi", "CN"),
    "baidu": ("Baidu", "CN"), "tencent": ("Tencent", "CN"), "bytedance": ("ByteDance", "CN"),
    "bytedance-seed": ("ByteDance", "CN"), "stepfun-ai": ("StepFun", "CN"), "stepfun": ("StepFun", "CN"),
    "ai21": ("AI21 Labs", "IL"), "arcee-ai": ("Arcee AI", "US"), "inception": ("Inception", "US"),
    "liquid": ("Liquid AI", "US"), "ibm-granite": ("IBM", "US"), "inflection": ("Inflection AI", "US"),
}
# Prefix-less model ids on flat-namespace aggregators: family keyword -> model vendor key above.
_FAMILIES = (("claude", "anthropic"), ("gpt-", "openai"), ("o3", "openai"), ("o4", "openai"),
             ("gemini", "google"), ("gemma", "google"), ("deepseek", "deepseek"), ("qwen", "qwen"),
             ("kimi", "moonshotai"), ("glm", "z-ai"), ("grok", "x-ai"), ("mistral", "mistralai"),
             ("codestral", "mistralai"), ("devstral", "mistralai"), ("llama", "meta-llama"),
             ("minimax", "minimax"), ("hermes", "nousresearch"), ("mimo", "xiaomi"), ("nemotron", "nvidia"))


def model_vendor(model: Optional[str]) -> tuple[str, str]:
    """(vendor, HQ) of the model behind an aggregator, from its id; ('', '') when not known.

    ``deepseek/deepseek-v4-flash`` -> DeepSeek; ``openrouter/auto`` -> ('', '') (routing decided by the
    aggregator); a prefix-less id is matched by model family (``claude-sonnet-5`` -> Anthropic)."""
    m = str(model or "").strip().lower()
    if not m:
        return "", ""
    m = m.split(":", 1)[0] if "/" in m.split(":", 1)[0] else m
    if "/" in m:
        prefix = m.split("/", 1)[0]
        if prefix in MODEL_PREFIXES:
            return MODEL_PREFIXES[prefix]
        if prefix in ("openrouter", "auto"):
            return "", ""
        rest = m.split("/", 1)[1]
    else:
        rest = m
    for word, key in _FAMILIES:
        if rest.startswith(word) or ("-" + word) in rest or ("/" + word) in rest:
            return MODEL_PREFIXES[key]
    if "/" in m:
        return m.split("/", 1)[0], "unknown"
    return "", ""


def is_aggregator(info: dict) -> bool:
    return info.get("kind") == "router"


def with_model(info: dict, model: Optional[str]) -> dict:
    """``info`` plus ``mvendor``/``mhq`` (model vendor behind an aggregator; empty otherwise)."""
    out = dict(info)
    if is_aggregator(out):
        mv, mhq = model_vendor(model)
        out["mvendor"], out["mhq"] = mv, mhq
    else:
        out["mvendor"], out["mhq"] = "", ""
    return out


def route_label(info: dict, lang: str = "en") -> str:
    """'OpenRouter → DeepSeek model' for aggregators, else the vendor name."""
    vendor = str(info.get("vendor") or info.get("host") or "unknown")
    if is_aggregator(info) or info.get("vkind") == "router":
        mv = str(info.get("mvendor") or "")
        if mv:
            return f"{vendor} → {mv} " + ("Modell" if lang == "de" else "model")
        return f"{vendor} → " + ("unbekanntes Modell" if lang == "de" else "unknown model")
    return vendor


def same_route(a: dict, b: dict) -> bool:
    """Whether two destinations are the same recipient (used for 'extra recipient').

    Same company at the host (same host, or same known vendor), and for aggregators also the same
    upstream model vendor. An aggregator model whose vendor is not known never counts as the same."""
    if a.get("local") and b.get("local"):
        return True
    if a.get("local") or b.get("local"):
        return False
    same_host = bool(a.get("host")) and a.get("host") == b.get("host")
    same_vendor = a.get("hq") not in (None, "unknown") and a.get("vendor") == b.get("vendor")
    if not (same_host or same_vendor):
        return False
    agg_a = a.get("kind") == "router" or a.get("vkind") == "router"
    agg_b = b.get("kind") == "router" or b.get("vkind") == "router"
    if agg_a or agg_b:
        mv_a, mv_b = str(a.get("mvendor") or ""), str(b.get("mvendor") or "")
        return bool(mv_a) and mv_a == mv_b
    return True

EU = frozenset("AT BE BG CY CZ DE DK EE ES FI FR GR HR HU IE IT LT LU LV MT NL PL PT RO SE SI SK".split())
EEA = EU | {"IS", "LI", "NO"}


def host_of(base_url: Optional[str]) -> str:
    """Lowercase host of a base URL ('' when there is none). Ports and paths are dropped."""
    raw = str(base_url or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    try:
        host = urlparse(raw).hostname or ""
    except Exception:  # noqa: BLE001
        host = ""
    return host.strip(".").lower()


def is_local_host(host: str) -> bool:
    """Loopback, private, link-local and Tailscale/CGNAT addresses, .local/.internal names."""
    h = (host or "").strip("[]").lower()
    if not h:
        return False
    if h in ("localhost", "host.docker.internal") or h.endswith((".localhost", ".local", ".internal",
                                                                 ".lan", ".home.arpa", ".ts.net")):
        return True
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return False
    if ip.is_loopback or ip.is_private or ip.is_link_local:
        return True
    return isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network("100.64.0.0/10")


def classify(host: str, provider: str = "") -> dict[str, object]:
    """Vendor record for a host: vendor, hq (ISO code or 'local'/'unknown'), kind, local."""
    h = (host or "").lower()
    p = (provider or "").strip().lower()
    if not h and p:
        h = PROVIDER_HOSTS.get(p.split(":", 1)[0], "")
    if h and is_local_host(h):
        return {"host": h, "vendor": "This machine / private network", "hq": "local", "kind": "local",
                "local": True}
    for suffix, vendor, hq, kind in _HOSTS:
        if h == suffix or h.endswith("." + suffix):
            return {"host": h, "vendor": vendor, "hq": hq, "kind": kind, "local": False}
    return {"host": h or "unknown", "vendor": h or (p or "unknown"), "hq": "unknown", "kind": "unknown",
            "local": False}


def in_region(hq: str, region: str) -> Optional[bool]:
    """Whether a vendor HQ lies in the configured home region. None = no region configured."""
    reg = (region or "").strip().upper()
    if not reg:
        return None
    if hq == "local":
        return True
    if hq == "unknown":
        return False
    allowed: set[str] = set()
    for part in reg.replace(";", ",").split(","):
        part = part.strip()
        if part == "EU":
            allowed |= EU
        elif part == "EEA":
            allowed |= EEA
        elif len(part) == 2:
            allowed.add(part)
    return hq in allowed


COUNTRY_NAMES = {
    "US": "USA", "CN": "China", "FR": "France", "DE": "Germany", "CA": "Canada", "CH": "Switzerland",
    "NL": "Netherlands", "AE": "United Arab Emirates", "GB": "United Kingdom",
}
