# Instant public URL for the local app (no account needed).
# Uses cloudflared quick tunnel; downloads it on first use.

$ErrorActionPreference = "Stop"
$dir = "$env:TEMP\kinema-tools"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$exe = Join-Path $dir "cloudflared.exe"
if (-not (Test-Path $exe)) {
  Write-Host "Downloading cloudflared…"
  Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile $exe
}

Write-Host "Starting app on :8000 (if not already running)…"
$up = $false
try { $up = (Invoke-WebRequest -Uri http://127.0.0.1:8000/ -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 } catch {}
if (-not $up) {
  Start-Process -WindowStyle Hidden python -ArgumentList '-m','uvicorn','web.app:app','--host','127.0.0.1','--port','8000' -WorkingDirectory (Split-Path $PSScriptRoot -Parent)
  Start-Sleep 5
}

Write-Host "Opening public tunnel… (copy the https://…trycloudflare.app URL it prints)"
& $exe tunnel --url http://localhost:8000
