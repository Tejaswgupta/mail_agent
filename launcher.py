"""Application entry point — launches Chrome with a persistent profile and starts the watcher."""
from __future__ import annotations

import signal
import sys
import time

from loguru import logger
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

def _chrome_executable() -> str | None:
    """Return the system Chrome path on Windows; None elsewhere (Playwright default)."""
    import os
    import platform
    if platform.system() != "Windows":
        return None
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None  # fall back to bundled Chromium if Chrome isn't installed


def _launch_context(playwright) -> BrowserContext:
    temp_downloads = settings.DOWNLOADS_DIR / ".temp"
    temp_downloads.mkdir(parents=True, exist_ok=True)
    chrome_exe = _chrome_executable()
    return playwright.chromium.launch_persistent_context(
        user_data_dir=str(settings.BROWSER_PROFILE_DIR),
        channel="chrome" if sys.platform != "win32" else None,
        executable_path=chrome_exe,
        headless=False,
        no_viewport=True,
        args=[
            "--start-maximized",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            "--disable-blink-features=AutomationControlled",
        ],
        accept_downloads=True,
        downloads_path=str(temp_downloads),
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

    # Clean up old temp downloads if any exist from a previous run crash
    temp_dir = settings.DOWNLOADS_DIR / ".temp"
    if temp_dir.exists():
        import shutil
        for item in temp_dir.iterdir():
            try:
                if item.is_file() or item.is_symlink():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            except Exception as exc:
                logger.warning(f"Failed to clean up old temp download {item}: {exc}")

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
