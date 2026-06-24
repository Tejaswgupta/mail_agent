"""Application entry point — launches Chrome with a persistent profile and starts the watcher."""
from __future__ import annotations

import signal
import sys
import time

from loguru import logger
from playwright.sync_api import sync_playwright, BrowserContext, Page, TimeoutError as PWTimeoutError

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

def _short_url(url: str, limit: int = 180) -> str:
    if len(url) <= limit:
        return url
    return f"{url[:limit]}..."


def _attach_page_logging(page: Page, label: str = "page") -> None:
    if getattr(page, "_mail_agent_logging_attached", False):
        return
    setattr(page, "_mail_agent_logging_attached", True)

    def log_console(message):
        text = message.text
        if message.type in {"error", "warning"}:
            logger.debug(f"Browser console {message.type} [{label}]: {text[:500]}")

    def log_page_error(error):
        logger.warning(f"Browser page error [{label}]: {error}")

    def log_request_failed(request):
        if request.resource_type in {"document", "xhr", "fetch", "script"}:
            failure = request.failure or "unknown failure"
            logger.warning(
                "Browser request failed "
                f"[{label}] {request.method} {request.resource_type} "
                f"{_short_url(request.url)} | {failure}"
            )

    def log_response(response):
        if response.status >= 400 and response.request.resource_type in {"document", "xhr", "fetch", "script"}:
            logger.warning(
                "Browser HTTP error "
                f"[{label}] {response.status} {response.request.method} "
                f"{response.request.resource_type} {_short_url(response.url)}"
            )

    def log_frame_navigated(frame):
        if frame == page.main_frame:
            logger.debug(f"Main frame navigated [{label}]: {_short_url(frame.url)}")
        elif "mgovcloud" in frame.url or "zoho" in frame.url:
            logger.debug(f"Child frame navigated [{label}]: {_short_url(frame.url)}")

    page.on("console", log_console)
    page.on("pageerror", log_page_error)
    page.on("requestfailed", log_request_failed)
    page.on("response", log_response)
    page.on("framenavigated", log_frame_navigated)


def _attach_context_logging(context: BrowserContext) -> None:
    for index, page in enumerate(context.pages):
        _attach_page_logging(page, f"existing-{index}")

    def attach_new_page(page):
        logger.debug(f"New browser page opened: {_short_url(page.url)}")
        _attach_page_logging(page, "new")

    context.on("page", attach_new_page)


def _launch_context(playwright) -> BrowserContext:
    temp_downloads = settings.DOWNLOADS_DIR / ".temp"
    temp_downloads.mkdir(parents=True, exist_ok=True)

    browser_args = [
        "--start-maximized",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-backgrounding-occluded-windows",
        "--disable-blink-features=AutomationControlled",
        "--disable-quic",
        "--disable-features=UseDnsHttpsSvcbAlpn,EncryptedClientHello",
    ]
    if settings.BROWSER_PROXY_MODE == "direct":
        browser_args.extend([
            "--no-proxy-server",
            "--proxy-server=direct://",
            "--proxy-bypass-list=*",
        ])

    launch_options = {
        "user_data_dir": str(settings.BROWSER_PROFILE_DIR),
        "headless": False,
        "no_viewport": True,
        "args": browser_args,
        "accept_downloads": True,
        "downloads_path": str(temp_downloads),
    }
    if settings.BROWSER_CHANNEL == "chrome":
        launch_options["channel"] = "chrome"

    return playwright.chromium.launch_persistent_context(**launch_options)


def _get_or_create_page(context: BrowserContext) -> Page:
    page = context.new_page()
    for old_page in context.pages:
        if old_page != page:
            try:
                old_page.close()
            except Exception as exc:
                logger.debug(f"Could not close restored browser tab: {exc}")
    return page


def _check_browser_connectivity(context: BrowserContext) -> None:
    if not settings.BROWSER_CONNECTIVITY_CHECK_URL:
        return

    page = context.new_page()
    try:
        logger.info(f"Checking browser connectivity: {settings.BROWSER_CONNECTIVITY_CHECK_URL}")
        response = page.goto(
            settings.BROWSER_CONNECTIVITY_CHECK_URL,
            wait_until="domcontentloaded",
            timeout=15_000,
        )
        status = response.status if response is not None else "no response"
        logger.info(f"Browser connectivity check completed: {status}")
    except PWTimeoutError:
        logger.warning(
            "Browser connectivity check timed out. If normal Chrome loads websites but this "
            "browser does not, set BROWSER_PROXY_MODE=system in .env and restart."
        )
    except Exception as exc:
        logger.warning(f"Browser connectivity check failed: {exc}")
    finally:
        try:
            page.close()
        except Exception:
            pass


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
                _attach_context_logging(context)
                _check_browser_connectivity(context)
                page = _get_or_create_page(context)
                _attach_page_logging(page, "main")

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
