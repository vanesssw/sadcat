# Restore Telegram session from local backup into Docker container
# Usage: .\restore_session.ps1

$SESSION_FILE = "$PSScriptRoot\.sessions\sadcat_session.session"
$CONTAINER = "sadcat-backend-1"

if (-not (Test-Path $SESSION_FILE)) {
    Write-Host "[!] Session backup not found: $SESSION_FILE" -ForegroundColor Red
    exit 1
}

Write-Host "[*] Copying session to container..." -ForegroundColor Cyan
docker cp $SESSION_FILE "${CONTAINER}:/app/sessions/sadcat_session.session"

if ($LASTEXITCODE -eq 0) {
    Write-Host "[+] Session restored!" -ForegroundColor Green
} else {
    Write-Host "[!] Failed to copy session" -ForegroundColor Red
    exit 1
}
