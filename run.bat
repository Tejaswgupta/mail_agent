@echo off
REM ── Start the mail agent ─────────────────────────────────────────────────
REM Copy .env.example to .env and fill in credentials before running.

setlocal
cd /d "%~dp0"

if not exist ".env" (
    echo [error] .env file not found. Copy .env.example to .env and fill in credentials.
    pause
    exit /b 1
)

echo [start] Starting Zoho Mail attachment agent...
python launcher.py

echo.
echo [exit] Agent stopped. Press any key to close.
pause
