# Lexorama launcher - starts the API (full DB) + the web dev server, then opens
# the browser. Double-click start-lexorama.bat (which calls this), or run directly.
#
# Ports: API 8011, web 5180 (both pinned - 8000/5173 are held by another app).
# If a server is already listening on its port, this script leaves it alone.
#
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads BOM-less .ps1 as
# cp1252, which mangles non-ASCII bytes and breaks string parsing.

$ErrorActionPreference = "Stop"

# Repo root = parent of this script's folder (scripts\).
$root = Split-Path -Parent $PSScriptRoot
$dbPath = Join-Path $root "data\db\lexorama.sqlite"
$webDir = Join-Path $root "apps\web"
$apiPort = 8011
$webPort = 5180
$webUrl  = "http://localhost:$webPort"

function Test-Port($port) {
    $null -ne (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

Write-Host "Lexorama launcher" -ForegroundColor Cyan
Write-Host "  root: $root"

if (-not (Test-Path $dbPath)) {
    Write-Host "  ! Database not found at $dbPath" -ForegroundColor Yellow
    Write-Host "    Run the ingest pipeline first (see HANDOFF.md)." -ForegroundColor Yellow
}

# --- API (uvicorn) ---
if (Test-Port $apiPort) {
    Write-Host "  API already running on :$apiPort - leaving it." -ForegroundColor DarkGray
} else {
    Write-Host "  Starting API on :$apiPort ..." -ForegroundColor Green
    $apiCmd = "`$env:PYTHONIOENCODING='utf-8'; `$env:LEXORAMA_DB='$dbPath'; Set-Location '$root'; python -m uvicorn services.api.app.main:app --port $apiPort"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiCmd -WorkingDirectory $root
}

# --- Web (vite) ---
if (Test-Port $webPort) {
    Write-Host "  Web already running on :$webPort - leaving it." -ForegroundColor DarkGray
} else {
    Write-Host "  Starting web on :$webPort ..." -ForegroundColor Green
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$webDir'; npm run dev" -WorkingDirectory $webDir
}

# --- Wait for the web server to answer, then open the browser ---
Write-Host "  Waiting for $webUrl ..." -ForegroundColor DarkGray
$deadline = (Get-Date).AddSeconds(40)
while ((Get-Date) -lt $deadline) {
    if (Test-Port $webPort) { Start-Sleep -Milliseconds 800; break }
    Start-Sleep -Milliseconds 500
}
Start-Process $webUrl
Write-Host "  Opened $webUrl - two server windows are running; close them to stop." -ForegroundColor Cyan
