@echo off
REM ── Build mail_agent.exe — zero-install single binary for Windows ─────────
REM
REM What gets bundled inside the .exe:
REM   - Python runtime
REM   - All Python packages (playwright, loguru, pydantic, openpyxl, pdfplumber…)
REM   - Playwright's Node.js driver
REM   - Chromium browser (~270 MB) — no system Chrome required on target machine
REM
REM Prerequisites (build machine only — NOT needed on the target machine):
REM   - Python 3.12  (python.org/downloads)
REM   - pip install -r requirements.txt
REM   - playwright install chromium
REM   - A C compiler reachable by Nuitka (MinGW-w64 or MSVC)
REM     Nuitka will prompt you to auto-install MinGW if none is found.
REM
REM Run this bat from the mail_agent\ directory.

setlocal

echo [build] Installing / upgrading Nuitka build tools...
pip install --quiet --upgrade nuitka ordered-set zstandard

echo [build] Ensuring Chromium is downloaded for bundling...
playwright install chromium

REM ── Locate package data dirs ─────────────────────────────────────────────
FOR /F "delims=" %%i IN ('python -c "import playwright, pathlib; print(pathlib.Path(playwright.__file__).parent / 'driver')"') DO SET PW_DRIVER=%%i
FOR /F "delims=" %%i IN ('python -c "import openpyxl, pathlib; print(pathlib.Path(openpyxl.__file__).parent)"') DO SET OPENPYXL_DIR=%%i
FOR /F "delims=" %%i IN ('python -c "import pdfminer, pathlib; print(pathlib.Path(pdfminer.__file__).parent)"') DO SET PDFMINER_DIR=%%i

echo [build] Playwright driver : %PW_DRIVER%
echo [build] openpyxl data     : %OPENPYXL_DIR%
echo [build] pdfminer data     : %PDFMINER_DIR%
echo [build] Compiling...

python -m nuitka ^
    --standalone ^
    --onefile ^
    --windows-console-mode=attach ^
    --output-filename=mail_agent.exe ^
    --include-package=playwright ^
    --include-package=loguru ^
    --include-package=pydantic ^
    --include-package=pydantic_settings ^
    --include-package=apscheduler ^
    --include-package=requests ^
    --include-package=openpyxl ^
    --include-package=pdfplumber ^
    --include-package=pdfminer ^
    --include-package=win32api ^
    --include-package=win32con ^
    --include-data-dir="%PW_DRIVER%"=playwright/driver ^
    --include-data-dir="%OPENPYXL_DIR%"=openpyxl ^
    --include-data-dir="%PDFMINER_DIR%"=pdfminer ^
    --include-data-dir=browser_profile=browser_profile ^
    --include-data-dir=downloads=downloads ^
    --include-data-dir=logs=logs ^
    --include-data-dir=screenshots=screenshots ^
    --include-data-files=.env=.env ^
    launcher.py

echo.
if exist mail_agent.exe (
    echo [build] SUCCESS: mail_agent.exe
    echo.
    echo Ship to the target machine:
    echo   mail_agent.exe
    echo   .env            ^(fill in credentials first^)
    echo.
    echo The target machine needs NOTHING installed — no Python, no Chrome.
) else (
    echo [build] FAILED — check output above
    exit /b 1
)

endlocal
pause
