Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$today = Get-Date -Format "yyyy-MM-dd"
$networkArgs = @()
if ($env:ORACLE_ALLOW_NETWORK -eq "true") {
    $networkArgs += "--allow-network"
}

python daily_operations_runner.py --date $today --pre-close @networkArgs

if ($env:ORACLE_ALLOW_TELEGRAM_SEND -eq "true") {
    python telegram_ops_runner.py --date $today --pre-close --allow-send
} else {
    python telegram_ops_runner.py --date $today --pre-close --dry-run
}
