"""PNG export through a headless Chrome or Chromium, when one is installed.

Nothing is downloaded. The browser only opens the local card files (file://, no network
needed: the cards have no external resources). Without a browser the HTML cards remain.
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

# Purpose-built headless shells first, then desktop browsers. Snap packages come last: their
# confinement blocks hidden folders such as ~/.hermes (page load fails with ERR_ACCESS_DENIED).
PLAYWRIGHT_GLOBS = ("~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell",
                    "~/Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell",
                    "~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")
CANDIDATES = ("chrome-headless-shell", "google-chrome", "google-chrome-stable", "chrome", "chromium",
              "chromium-browser", "microsoft-edge", "brave-browser")
MAC_APPS = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")


def find_browsers(explicit: str = "") -> list[str]:
    """Every usable candidate, best first. An explicit path or name wins and stands alone."""
    if explicit:
        p = shutil.which(explicit) or (explicit if os.path.isfile(explicit) else None)
        return [p] if p else []
    found: list[str] = []
    for pattern in PLAYWRIGHT_GLOBS:
        hits = sorted(glob.glob(os.path.expanduser(pattern)))
        if hits:
            found.append(hits[-1])
    for name in CANDIDATES:
        p = shutil.which(name)
        if p:
            found.append(p)
    found += [p for p in MAC_APPS if os.path.isfile(p)]
    seen: set[str] = set()
    uniq = [p for p in found if not (os.path.realpath(p) in seen or seen.add(os.path.realpath(p)))]
    return [p for p in uniq if not _is_snap(p)] + [p for p in uniq if _is_snap(p)]


def _is_snap(path: str) -> bool:
    real = os.path.realpath(path)
    if path.startswith("/snap/") or real.endswith("/usr/bin/snap"):
        return True
    try:  # Ubuntu's chromium-browser is a shell script that starts the snap
        with open(path, "rb") as fh:
            head = fh.read(4096)
        return head.startswith(b"#!") and b"/snap/" in head
    except OSError:
        return False


def find_browser(explicit: str = "") -> Optional[str]:
    found = find_browsers(explicit)
    return found[0] if found else None


def screenshot(browser: str, html_file: Path, png_file: Path, timeout: int = 60) -> bool:
    args = [browser]
    if "headless-shell" not in os.path.basename(browser):
        args.append("--headless=new")
    args += ["--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1", "--window-size=1080,1920",
             "--default-background-color=00000000", "--disable-extensions", "--no-first-run",
             "--virtual-time-budget=2000", "--screenshot=" + str(png_file.resolve()),
             html_file.resolve().as_uri()]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        args.insert(1, "--no-sandbox")  # Chrome refuses to start as root otherwise
    try:
        subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return png_file.is_file() and png_file.stat().st_size > 1000
