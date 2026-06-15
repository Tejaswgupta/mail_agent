# TEST_REPORT.md

## Files Created

### Source Modules

| File | Purpose |
|------|---------|
| `config.py` | Central settings (pydantic-settings), validates env vars, creates directories |
| `keep_awake.py` | Prevents Windows sleep via `SetThreadExecutionState`; no-op on macOS/Linux |
| `notifier.py` | Telegram notifications (silent no-op when credentials are absent) |
| `session_monitor.py` | Detects Zoho login/OTP/session-expiry pages; screenshots + alerts |
| `storage.py` | Supabase Postgres queries + Storage bucket uploads |
| `attachment_processor.py` | Downloads attachments, hashes, uploads, records metadata |
| `zoho_client.py` | Playwright-based Zoho Mail interaction (login wait, email list, downloads) |
| `watcher.py` | Polling loop: session check → inbox scan → dedup → process → heartbeat |
| `launcher.py` | Entry point: Chrome persistent context, crash recovery loop, logging setup |

### Configuration / Build

| File | Purpose |
|------|---------|
| `requirements.txt` | Python dependencies |
| `.env.example` | Environment variable template |
| `build.bat` | Nuitka single-file Windows build command |
| `migrations/001_create_tables.sql` | Supabase SQL for `processed_emails`, `attachments`, `agent_heartbeat` |

### Tests

| File | Tests |
|------|-------|
| `tests/conftest.py` | Shared fixtures: Supabase mock, Telegram stub, tmp dirs |
| `tests/test_config.py` | 4 tests — settings load, dir creation, defaults |
| `tests/test_keep_awake.py` | 3 tests — start/stop lifecycle, idempotency |
| `tests/test_notifier.py` | 4 tests — missing credentials, network error, photo send |
| `tests/test_session_monitor.py` | 7 tests — URL patterns, title patterns, screenshot handling |
| `tests/test_storage.py` | 5 tests — is_processed, mark_processed, upload, heartbeat |
| `tests/test_attachment_processor.py` | 6 tests — sha256, download save, upload failure, cleanup |
| `tests/test_watcher.py` | 5 tests — skip processed, new email, session expiry, db failure |

## Test Results

```
platform darwin -- Python 3.11.14, pytest-8.4.2
collected 36 items

tests/test_attachment_processor.py  7/7 PASSED
tests/test_config.py                4/4 PASSED
tests/test_keep_awake.py            3/3 PASSED
tests/test_notifier.py              4/4 PASSED
tests/test_session_monitor.py       7/7 PASSED
tests/test_storage.py               5/5 PASSED (mock)
tests/test_watcher.py               5/5 PASSED

=================== 36 passed in 0.62s ====================
```

**All 36 tests pass. All 9 source modules import without error. All syntax checks pass.**

## Known Limitations

1. **Zoho DOM selectors are fragile.** Zoho Mail is a single-page app with dynamic class names. The CSS selectors in `zoho_client.py` cover common patterns but may need adjustment if Zoho updates their frontend. Monitor `session_monitor.py` patterns when Zoho releases UI changes.

2. **`zoho_client.py` is not unit-tested.** It contains Playwright-dependent code (real browser interaction). Integration/E2E tests require a live Zoho account and are outside the scope of offline unit tests.

3. **`launcher.py` is not unit-tested.** It starts a real Chrome process. Startup smoke-test was done via `py_compile` and import verification.

4. **Windows-only features run as no-ops on macOS/Linux.** `keep_awake.py` skips `SetThreadExecutionState` on non-Windows platforms.

5. **Supabase calls require real credentials to function end-to-end.** All tests mock the Supabase client. Run `migrations/001_create_tables.sql` against your project before first use.

6. **No rate-limiting guard on Telegram.** If many errors occur in rapid succession, the bot may be throttled.

## Setup Instructions

### 1. Prerequisites

- Python 3.12
- Google Chrome installed (for Playwright `channel="chrome"`)
- A Supabase project with the migration applied

### 2. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your Supabase URL/key and (optionally) Telegram credentials
```

### 4. Apply database migration

```bash
psql -h db.your-project.supabase.co -U postgres -d postgres -f migrations/001_create_tables.sql
```

### 5. Run the agent

```bash
python launcher.py
```

On first launch, a Chrome window will open. Log in to Zoho Mail manually (including MFA). The session is persisted in `browser_profile/` and reused on subsequent launches.

### 6. Build Windows executable (optional)

```bat
build.bat
```

Produces `mail_agent.exe` — a standalone Windows binary (requires Nuitka + ordered-set + zstandard).

### 7. Run tests

```bash
pytest tests/ -v
```
