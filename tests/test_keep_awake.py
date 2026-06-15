"""Tests for keep_awake.py — run on non-Windows so Win32 path is skipped."""
import keep_awake
import time


def test_start_stop_no_crash():
    keep_awake.start()
    time.sleep(0.1)
    keep_awake.stop()


def test_double_stop():
    keep_awake.start()
    keep_awake.stop()
    keep_awake.stop()  # should not raise


def test_start_twice():
    keep_awake.start()
    keep_awake.start()  # second start should replace thread cleanly
    keep_awake.stop()
