# Starts the EzGrind backend.
#
#   .\run.ps1
#
# Leave the window open - Flask's reloader picks up .py changes on its own, so
# this only needs running once per session. Frontend files are served by Live
# Server, not by this, and need nothing more than a browser refresh.
#
# Works from any directory: paths resolve relative to this script.

$ErrorActionPreference = "Stop"

$backend = Join-Path $PSScriptRoot "EzGrind\Backend"

# venv layout differs by interpreter: msys2/MinGW Python builds a POSIX-style
# bin\, python.org builds Scripts\. Accept whichever is present.
$python = @(
    (Join-Path $backend "venv\bin\python.exe"),
    (Join-Path $backend "venv\Scripts\python.exe")
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $python) {
    Write-Host "No virtualenv found under EzGrind\Backend\venv" -ForegroundColor Red
    Write-Host ""
    Write-Host "Create one with:"
    Write-Host "  cd `"$backend`""
    Write-Host "  python -m venv venv"
    Write-Host "  .\venv\bin\python.exe -m pip install -r requirements.txt"
    exit 1
}

if (-not (Test-Path (Join-Path $backend ".env"))) {
    Write-Host "EzGrind\Backend\.env is missing." -ForegroundColor Red
    Write-Host ""
    Write-Host "The app refuses to start without SECRET_KEY and DATABASE_URL. Create it with:"
    Write-Host "  cd `"$backend`""
    Write-Host "  Copy-Item .env.example .env"
    Write-Host "  # then fill in SECRET_KEY and DATABASE_URL (Neon -> Connection Details)"
    exit 1
}

Write-Host "Backend  http://127.0.0.1:5000" -ForegroundColor DarkYellow
Write-Host "Frontend http://127.0.0.1:5500  (must be 127.0.0.1, not localhost - see CLAUDE.md)" -ForegroundColor DarkYellow
Write-Host "Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

Set-Location $backend
& $python app.py
