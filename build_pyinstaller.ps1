#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Build mail_agent.exe with PyInstaller (fast alternative to Nuitka)
.DESCRIPTION
    Generates a license key, injects the signing key, and builds a Windows EXE with PyInstaller
.PARAMETER ClientId
    Client name (e.g., "AcmeCorp")
.PARAMETER Expiry
    License expiry date in YYYY-MM-DD format
.PARAMETER SigningKey
    Base64-encoded HMAC signing key (optional - will be generated if not provided)
.EXAMPLE
    .\build_pyinstaller.ps1 -ClientId "AcmeCorp" -Expiry "2027-12-31"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$ClientId,

    [Parameter(Mandatory=$true)]
    [ValidatePattern('^\d{4}-\d{2}-\d{2}$')]
    [string]$Expiry,

    [Parameter(Mandatory=$false)]
    [string]$SigningKey
)

$ErrorActionPreference = "Stop"

# ============================================================================
# Load or generate signing key
# ============================================================================

Write-Host "`n==> Loading signing key..." -ForegroundColor Cyan

$signingKeyFile = ".signing_key"

if (-not $SigningKey) {
    # Try to load from file
    if (Test-Path $signingKeyFile) {
        $SigningKey = Get-Content $signingKeyFile -Raw
        $SigningKey = $SigningKey.Trim()
        Write-Host "    Loaded existing signing key from $signingKeyFile" -ForegroundColor Green
    }
    # Try environment variable
    elseif ($env:LICENSE_SIGNING_KEY) {
        $SigningKey = $env:LICENSE_SIGNING_KEY
        Write-Host "    Loaded signing key from LICENSE_SIGNING_KEY environment variable" -ForegroundColor Green
    }
    # Generate new key
    else {
        Write-Host "    No signing key found - generating new one..." -ForegroundColor Yellow

        $tempScript = "generate_key_temp.py"
        $pythonCode = @"
import secrets, base64
key = secrets.token_bytes(32)
print(base64.b64encode(key).decode())
"@

        Set-Content -Path $tempScript -Value $pythonCode -Encoding UTF8
        $SigningKey = python $tempScript
        Remove-Item $tempScript -ErrorAction SilentlyContinue

        if (-not $SigningKey) {
            Write-Host "ERROR: Failed to generate signing key" -ForegroundColor Red
            exit 1
        }

        # Save for future builds
        Set-Content -Path $signingKeyFile -Value $SigningKey -NoNewline

        Write-Host "    Generated new signing key and saved to $signingKeyFile" -ForegroundColor Green
        Write-Host "    IMPORTANT: Keep this file secure and back it up!" -ForegroundColor Yellow
        Write-Host "    You need the same key to validate licenses in the future." -ForegroundColor Yellow
    }
}

if (-not $SigningKey) {
    Write-Host "ERROR: Could not obtain signing key" -ForegroundColor Red
    exit 1
}

# ============================================================================
# Validate prerequisites
# ============================================================================

Write-Host "`n==> Validating prerequisites..." -ForegroundColor Cyan

# Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "    Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Python not found. Install Python 3.11+ and add to PATH." -ForegroundColor Red
    exit 1
}

# Check required files
$requiredFiles = @("launcher.py", "license_validator.py", "requirements.txt")
foreach ($file in $requiredFiles) {
    if (-not (Test-Path $file)) {
        Write-Host "ERROR: Missing required file: $file" -ForegroundColor Red
        exit 1
    }
}

Write-Host "    All prerequisites OK" -ForegroundColor Green

# ============================================================================
# Install dependencies
# ============================================================================

Write-Host "`n==> Installing dependencies..." -ForegroundColor Cyan

Write-Host "    Installing Python packages..." -ForegroundColor Gray
pip install -q -r requirements.txt
pip install -q pyinstaller

Write-Host "    Installing Playwright Chromium..." -ForegroundColor Gray
python -m playwright install chromium

Write-Host "    Dependencies installed" -ForegroundColor Green

# ============================================================================
# Inject signing key into license_validator.py
# ============================================================================

Write-Host "`n==> Injecting signing key..." -ForegroundColor Cyan

$validatorPath = "license_validator.py"
$validatorBackup = "license_validator.py.bak"

# Backup original
if (-not (Test-Path $validatorBackup)) {
    Copy-Item $validatorPath $validatorBackup
}

$validatorContent = Get-Content $validatorPath -Raw

# Replace the placeholder signing key
$pattern = '_SIGNING_KEY = b"[^"]+"'
$replacement = "_SIGNING_KEY = b`"$SigningKey`""
$validatorContent = $validatorContent -replace $pattern, $replacement

Set-Content -Path $validatorPath -Value $validatorContent -NoNewline

Write-Host "    Signing key injected into license_validator.py" -ForegroundColor Green

# ============================================================================
# Generate license key
# ============================================================================

Write-Host "`n==> Generating license key..." -ForegroundColor Cyan
Write-Host "    Client ID: $ClientId" -ForegroundColor Gray
Write-Host "    Expiry: $Expiry" -ForegroundColor Gray

# Write Python script to temporary file to avoid escaping issues
$tempScript = "generate_license_temp.py"
$pythonCode = @"
import os, base64, hashlib, hmac, json

key = os.environ['SIGNING_KEY'].encode()
client_id = os.environ['CLIENT_ID']
expiry = os.environ['EXPIRY']

payload = json.dumps({'client_id': client_id, 'expiry': expiry}, separators=(',', ':'))
payload_b64 = base64.b64encode(payload.encode()).decode()
sig = hmac.new(key, payload_b64.encode(), hashlib.sha256).hexdigest()

with open('license.key', 'w', encoding='utf-8') as f:
    f.write(f'{payload_b64}.{sig}\n')

print('License key generated: license.key')
"@

Set-Content -Path $tempScript -Value $pythonCode -Encoding UTF8

$env:SIGNING_KEY = $SigningKey
$env:CLIENT_ID = $ClientId
$env:EXPIRY = $Expiry

python $tempScript

Remove-Item $tempScript -ErrorAction SilentlyContinue

if (-not (Test-Path "license.key")) {
    Write-Host "ERROR: Failed to generate license.key" -ForegroundColor Red
    exit 1
}

Write-Host "    License key generated: license.key" -ForegroundColor Green

# ============================================================================
# Build EXE with PyInstaller
# ============================================================================

Write-Host "`n==> Building EXE with PyInstaller..." -ForegroundColor Cyan
Write-Host "    This takes 2-3 minutes..." -ForegroundColor Yellow

# Clean previous builds
if (Test-Path "dist") {
    Remove-Item "dist" -Recurse -Force -ErrorAction SilentlyContinue
}
if (Test-Path "build") {
    Remove-Item "build" -Recurse -Force -ErrorAction SilentlyContinue
}

pyinstaller `
    --onefile `
    --console `
    --name mail_agent `
    --add-data "migrations;migrations" `
    --hidden-import "playwright" `
    --hidden-import "pydantic" `
    --hidden-import "pydantic_settings" `
    --hidden-import "loguru" `
    --hidden-import "supabase" `
    --hidden-import "httpx" `
    --hidden-import "requests" `
    --hidden-import "openpyxl" `
    --hidden-import "pdfplumber" `
    --icon "NONE" `
    launcher.py

if (-not (Test-Path "dist\mail_agent.exe")) {
    Write-Host "`nERROR: Build failed - dist\mail_agent.exe not found" -ForegroundColor Red
    exit 1
}

Write-Host "`n    Build complete!" -ForegroundColor Green

# ============================================================================
# Restore original license_validator.py
# ============================================================================

Write-Host "`n==> Cleaning up..." -ForegroundColor Cyan

if (Test-Path $validatorBackup) {
    Copy-Item $validatorBackup $validatorPath -Force
    Remove-Item $validatorBackup -Force
    Write-Host "    Restored original license_validator.py" -ForegroundColor Green
}

# Clean PyInstaller artifacts
if (Test-Path "mail_agent.spec") {
    Remove-Item "mail_agent.spec" -Force
}
if (Test-Path "build") {
    Remove-Item "build" -Recurse -Force
}

Write-Host "    Cleaned up build artifacts" -ForegroundColor Green

# ============================================================================
# Package for distribution
# ============================================================================

Write-Host "`n==> Packaging release..." -ForegroundColor Cyan

$releaseDir = "release"
if (Test-Path $releaseDir) {
    Remove-Item $releaseDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

Copy-Item "dist\mail_agent.exe" "$releaseDir\mail_agent.exe"
Copy-Item "license.key" "$releaseDir\license.key"
Copy-Item ".env.example" "$releaseDir\.env.example"

if (Test-Path "INSTALL.md") {
    Copy-Item "INSTALL.md" "$releaseDir\INSTALL.md"
}

$zipName = "mail_agent_${ClientId}.zip"
if (Test-Path $zipName) {
    Remove-Item $zipName -Force
}

Compress-Archive -Path "$releaseDir\*" -DestinationPath $zipName

Write-Host "    Release package: $zipName" -ForegroundColor Green

# ============================================================================
# Summary
# ============================================================================

$exeSize = (Get-Item "dist\mail_agent.exe").Length / 1MB
$zipSize = (Get-Item $zipName).Length / 1MB

Write-Host "`n===========================================================" -ForegroundColor Green
Write-Host "BUILD SUCCESSFUL (PyInstaller)" -ForegroundColor Green
Write-Host "===========================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Client ID:      $ClientId" -ForegroundColor White
Write-Host "  License Expiry: $Expiry" -ForegroundColor White
Write-Host "  EXE Size:       $([math]::Round($exeSize, 2)) MB" -ForegroundColor White
Write-Host "  Package Size:   $([math]::Round($zipSize, 2)) MB" -ForegroundColor White
Write-Host ""
Write-Host "  Files created:" -ForegroundColor Cyan
Write-Host "    dist\mail_agent.exe" -ForegroundColor Gray
Write-Host "    license.key" -ForegroundColor Gray
Write-Host "    $zipName" -ForegroundColor Gray
Write-Host "    $signingKeyFile (signing key backup)" -ForegroundColor Gray
Write-Host ""
Write-Host "  Build time: ~2-3 minutes (much faster than Nuitka!)" -ForegroundColor Yellow
Write-Host ""
Write-Host "  IMPORTANT: Back up $signingKeyFile securely!" -ForegroundColor Yellow
Write-Host "  You need it to generate licenses for future builds." -ForegroundColor Yellow
Write-Host ""
Write-Host "===========================================================" -ForegroundColor Green
Write-Host ""
