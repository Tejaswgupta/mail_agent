"""Keep Windows awake using SetThreadExecutionState (no mouse movement).
On non-Windows platforms this is a no-op so tests can run cross-platform.

The flag must be renewed periodically — Windows may reset it after ~45 s on
some power plans.  We refresh every 30 seconds to stay well inside that window."""
import sys
import threading
from loguru import logger

_stop_event = threading.Event()
_thread: threading.Thread | None = None

_REFRESH_INTERVAL = 30  # seconds


def _awake_loop() -> None:
    if sys.platform != "win32":
        logger.info("keep_awake: non-Windows platform — skipping SetThreadExecutionState")
        return
    import ctypes
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ES_DISPLAY_REQUIRED = 0x00000002
    flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
    kernel32 = ctypes.windll.kernel32
    kernel32.SetThreadExecutionState(flags)
    logger.info("keep_awake: system sleep prevented")
    while not _stop_event.wait(timeout=_REFRESH_INTERVAL):
        # Renew periodically so aggressive power plans don't override us
        kernel32.SetThreadExecutionState(flags)
    kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    logger.info("keep_awake: sleep prevention released")


def start() -> None:
    global _thread
    _stop_event.clear()
    _thread = threading.Thread(target=_awake_loop, daemon=True, name="keep-awake")
    _thread.start()


def stop() -> None:
    _stop_event.set()
    if _thread:
        _thread.join(timeout=5)
