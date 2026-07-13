# Building the Windows EXE

This document explains how to build `mail_agent.exe` from source.

---

## Prerequisites

- **Windows 10 or 11** (or Windows VM on macOS)
- **Python 3.11+** installed and added to PATH
- **Git** (optional, for cloning the repo)
- **LICENSE_SIGNING_KEY** environment variable set

---

## Quick Start

1. **Run the build script** (it auto-generates the signing key on first run):
   ```powershell
   .\build.ps1 -ClientId "AcmeCorp" -Expiry "2027-12-31"
   ```

2. **Wait 10-15 minutes** (first build only; subsequent builds are faster)

3. **Find your files**:
   - `dist\mail_agent.exe` — the standalone executable
   - `license.key` — the generated license file
   - `mail_agent_AcmeCorp.zip` — ready-to-ship package

---

## What the Script Does

1. 🔑 **Generates or loads signing key** (auto-creates `.signing_key` file on first run)
2. ✅ Validates Python and required files
3. 📦 Installs dependencies (pip packages, Playwright)
4. 🔑 Injects the signing key into `license_validator.py`
5. 🎫 Generates a signed license key for the client
6. 🏗️ Compiles the EXE with Nuitka (bundles Python + all dependencies)
7. 🔄 Restores original `license_validator.py` (removes embedded key)
8. 📁 Packages everything into a zip file

---

## Build Options

### Use existing signing key
The script automatically uses `.signing_key` if it exists. To use a different key:
```powershell
.\build.ps1 -ClientId "TestClient" -Expiry "2026-12-31" -SigningKey "your-key-here"
```

Or set it as an environment variable:
```powershell
$env:LICENSE_SIGNING_KEY = "your-key-here"
.\build.ps1 -ClientId "TestClient" -Expiry "2026-12-31"
```

### Multiple clients
Build for different clients by running the script multiple times:
```powershell
.\build.ps1 -ClientId "ClientA" -Expiry "2027-06-30"
.\build.ps1 -ClientId "ClientB" -Expiry "2028-01-15"
```

Each build creates a separate `mail_agent_<ClientId>.zip` file.

---

## Troubleshooting

### "Python not found"
- Install Python from [python.org](https://python.org)
- During installation, check **"Add Python to PATH"**
- Restart PowerShell after installation

### "Failed to generate signing key"
- Make sure Python is installed correctly
- Check that Python's `secrets` module is available: `python -c "import secrets; print('OK')"`

### "Build failed - dist\mail_agent.exe not found"
- Check the output for errors
- Common issues:
  - Missing dependencies: re-run `pip install -r requirements.txt`
  - Disk space: Nuitka needs ~2GB free space
  - Antivirus: may block Nuitka; add an exception for the project folder

### "The script cannot be loaded because running scripts is disabled"
Run this once as Administrator:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### Build takes forever
- First build: 10-15 minutes is normal (Nuitka compiles everything)
- Subsequent builds: 2-5 minutes (cached)
- Close other applications to free up CPU/RAM

---

## File Structure After Build

```
mail_agent/
├── dist/
│   └── mail_agent.exe          ← Standalone EXE (50-80 MB)
├── release/
│   ├── mail_agent.exe
│   ├── license.key
│   ├── .env.example
│   └── INSTALL.md
├── build/                      ← Nuitka intermediate files (can delete)
├── license.key                 ← Generated license
├── mail_agent_<ClientId>.zip   ← Ready to ship
└── build.ps1                   ← This build script
```

---

## Cleaning Up

To start fresh:
```powershell
Remove-Item -Recurse -Force dist, build, release, *.zip
```

---

## Advanced: Manual Build

If you need to customize the build, here's the raw Nuitka command:

```powershell
python -m nuitka `
  --onefile `
  --standalone `
  --assume-yes-for-downloads `
  --windows-console-mode=attach `
  --windows-company-name="DRI" `
  --windows-product-name="Mail Agent" `
  --windows-file-version="1.0.0.0" `
  --windows-product-version="1.0.0.0" `
  --windows-file-description="DRI Mail Agent" `
  --onefile-tempdir-spec="{CACHE_DIR}\DRI\mail_agent" `
  --include-package=playwright `
  --include-package=pydantic `
  --include-package=pydantic_settings `
  --include-package=loguru `
  --include-package=supabase `
  --include-package=gotrue `
  --include-package=httpx `
  --include-package=requests `
  --include-package=openpyxl `
  --include-package=pdfplumber `
  --include-data-dir=migrations=migrations `
  --output-dir=dist `
  --output-filename=mail_agent.exe `
  launcher.py
```

---

## CI/CD Alternative

Instead of building locally, you can use GitHub Actions:

1. Go to your repo on GitHub
2. Click **Actions** → **Build Windows EXE**
3. Click **Run workflow**
4. Enter client ID and expiry date
5. Download the built zip from the artifacts

This requires the `LICENSE_SIGNING_KEY` secret to be set in your repo settings.

---

## Support

- **Build issues**: Check the PowerShell output for specific errors
- **License issues**: Verify your signing key is correct
- **Runtime issues**: See `INSTALL.md` for end-user troubleshooting
