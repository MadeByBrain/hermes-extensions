"""privacy-xray dashboard backend, mounted at /api/plugins/privacy-xray/.

GET /report?lang=en|de returns the same self-contained HTML leak map as /xray report, built from the
ledger in this Hermes home, plus a signature that only changes when the content changes (the tab
polls it and redraws only then). Read-only apart from refreshing the cached config check, exactly
like /xray report. Metadata only: the page never contains message content.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import sys
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter

router = APIRouter()

_PKG_DIR = Path(__file__).resolve().parent.parent
_NAME = "privacy_xray_dashboard_backend"
_lock = threading.Lock()


def _package() -> Any:
    """The plugin package, loaded once from the plugin folder under a private module name."""
    with _lock:
        mod = sys.modules.get(_NAME)
        if mod is not None:
            return mod
        spec = importlib.util.spec_from_file_location(_NAME, _PKG_DIR / "__init__.py",
                                                      submodule_search_locations=[str(_PKG_DIR)])
        if spec is None or spec.loader is None:
            raise ImportError("privacy-xray package not found")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[_NAME] = mod
        try:
            spec.loader.exec_module(mod)
        except BaseException:
            for key in [k for k in sys.modules if k == _NAME or k.startswith(_NAME + ".")]:
                sys.modules.pop(key, None)
            raise
        return mod


def _signature(page: str) -> str:
    """Hash of the page without the 'Generated' line, so an unchanged map keeps its signature."""
    head, sep, tail = page.partition('<div class="meta">')
    if sep:
        tail = tail.partition("</div>")[2]
    return hashlib.sha256((head + tail).encode("utf-8")).hexdigest()[:16]


def render(lang: str = "") -> dict:
    px = _package()
    lang = lang if lang in ("en", "de") else px._lang()
    page = px.build_report_page(lang)
    return {"ok": True, "lang": lang, "sig": _signature(page), "ts": int(time.time()), "html": page}


@router.get("/report")
async def report(lang: str = "") -> dict:
    try:
        return await asyncio.to_thread(render, lang)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
