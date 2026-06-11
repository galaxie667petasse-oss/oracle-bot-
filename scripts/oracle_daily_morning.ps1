Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$today = Get-Date -Format "yyyy-MM-dd"
$networkArgs = @()
if ($env:ORACLE_ALLOW_NETWORK -eq "true") {
    $networkArgs += "--allow-network"
}

git status --short
python daily_operations_runner.py --date $today --morning @networkArgs

if ($env:ORACLE_ALLOW_TELEGRAM_SEND -eq "true") {
    python telegram_daily_reporter.py --date $today --allow-send
} else {
    python telegram_daily_reporter.py --date $today --dry-run
}
