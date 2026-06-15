"""Application entry point — launches Chrome with a persistent profile and starts the watcher."""
from __future__ import annotations

import signal
import sys
import time
from pathlib import Path

# pyrefly: ignore [missing-import]
from loguru import logger
# pyrefly: ignore [missing-import]
from playwright.sync_api import sync_playwright, BrowserContext, Page

import keep_awake
import notifier
import storage
import watcher
import zoho_client
from config import settings

# ── Windows CTRL+C / CTRL+BREAK handler ─────────────────────────────────────
# signal.SIGBREAK only exists on Windows; SIGINT works on both.
def _shutdown_handler(sig, frame):
    logger.info("Shutdown signal received")
    raise KeyboardInterrupt

signal.signal(signal.SIGINT, _shutdown_handler)
if sys.platform == "win32":
    signal.signal(signal.SIGBREAK, _shutdown_handler)

# ─────────────────────────────────────────────────────────────────────────────
# Logging setup
# ─────────────────────────────────────────────────────────────────────────────

settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)
logger.add(
    str(settings.LOGS_DIR / "application.log"),
    rotation="10 MB",
    retention="30 days",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{line} | {message}",
    enqueue=True,
)


# ─────────────────────────────────────────────────────────────────────────────
# Browser management
# ─────────────────────────────────────────────────────────────────────────────

def _chromium_executable() -> str | None:
    """Return path to the Chromium bundled inside the Nuitka onefile exe, or
    None when running from source (falls back to system Chrome below)."""
    # Nuitka extracts onefile contents to a temp dir and sets sys._MEIPASS-style
    # via __compiled__. We use the location of this file as the anchor.
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else None
    if base is None:
        # Also handle Nuitka's __compiled__ attribute
        try:
            if __compiled__:          # type: ignore[name-defined]
                base = Path(sys.executable).parent
        except NameError:
            pass
    if base is None:
        return None

    # Playwright bundles the chromium binary under playwright/driver/package/.local-chromium/
    candidates = list(base.glob("playwright/driver/package/.local-chromium/**/chrome.exe"))
    if candidates:
        return str(candidates[0])
    # Fallback: playwright/driver/node_modules/playwright-core/.local-chromium
    candidates = list(base.glob("**/chrome.exe"))
    if candidates:
        return str(candidates[0])
    return None


def _launch_context(playwright) -> BrowserContext:
    exe = _chromium_executable()
    if exe:
        logger.info(f"Using bundled Chromium: {exe}")
        return playwright.chromium.launch_persistent_context(
            user_data_dir=str(settings.BROWSER_PROFILE_DIR),
            executable_path=exe,
            headless=False,
            no_viewport=True,
            args=[
                "--start-maximized",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
            ],
            accept_downloads=True,
            downloads_path=str(settings.DOWNLOADS_DIR),
        )
    else:
        logger.info("Bundled Chromium not found — using system Chrome")
        return playwright.chromium.launch_persistent_context(
            user_data_dir=str(settings.BROWSER_PROFILE_DIR),
            channel="chrome",
            headless=False,
            no_viewport=True,
            args=[
                "--start-maximized",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
            ],
            accept_downloads=True,
            downloads_path=str(settings.DOWNLOADS_DIR),
        )


def _get_or_create_page(context: BrowserContext) -> Page:
    pages = context.pages
    if pages:
        return pages[0]
    return context.new_page()


# ─────────────────────────────────────────────────────────────────────────────
# Main recovery loop
# ─────────────────────────────────────────────────────────────────────────────

MAX_CRASHES = 10
CRASH_BACKOFF = 30  # seconds


def run() -> None:
    keep_awake.start()
    logger.info("Application starting")
    storage.init_db()
    notifier.send("🚀 Mail agent starting up…")

    crash_count = 0

    while crash_count < MAX_CRASHES:
        context = None
        try:
            with sync_playwright() as pw:
                logger.info("Launching Chrome with persistent profile: %s", settings.BROWSER_PROFILE_DIR)
                context = _launch_context(pw)
                page = _get_or_create_page(context)

                if not zoho_client.ensure_logged_in(page):
                    logger.error("Could not log in — retrying after backoff")
                    context.close()
                    context = None
                    time.sleep(CRASH_BACKOFF)
                    crash_count += 1
                    continue

                crash_count = 0  # reset on successful login
                watcher.watch(page)

        except KeyboardInterrupt:
            logger.info("Interrupted by user — shutting down")
            notifier.send("🛑 Mail agent stopped by user")
            break
        except Exception as exc:
            crash_count += 1
            logger.error(f"Browser/watcher crash #{crash_count}: {exc}")
            notifier.send(f"💥 Mail agent crashed (attempt {crash_count}/{MAX_CRASHES}): {exc}")
            # Always attempt a clean context close to release the Chrome profile lock
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
                context = None
            if crash_count < MAX_CRASHES:
                logger.info(f"Recovering in {CRASH_BACKOFF}s…")
                notifier.send(f"♻️ Recovering in {CRASH_BACKOFF}s…")
                time.sleep(CRASH_BACKOFF)
            else:
                logger.critical("Max crash retries reached — exiting")
                notifier.send("🚨 Max crash retries reached — agent stopped")

    keep_awake.stop()
    logger.info("Application exited")


if __name__ == "__main__":
    run()
