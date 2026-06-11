# Exemple uniquement: ne pas executer sans revue humaine.
# Les variables ORACLE_ALLOW_NETWORK et ORACLE_ALLOW_TELEGRAM_SEND restent dans l'environnement Windows.

$ProjectRoot = Split-Path -Parent $PSScriptRoot

# Matin 09:00
# $morningAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ProjectRoot\scripts\oracle_daily_morning.ps1`""
# $morningTrigger = New-ScheduledTaskTrigger -Daily -At 09:00
# Register-ScheduledTask -TaskName "OracleFootballBotMorning" -Action $morningAction -Trigger $morningTrigger -Description "Oracle morning live scan dry-run by default"

# Pre-close toutes les heures
# $preCloseAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ProjectRoot\scripts\oracle_pre_close.ps1`""
# $preCloseTrigger = New-ScheduledTaskTrigger -Once -At 09:00 -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Hours 14)
# Register-ScheduledTask -TaskName "OracleFootballBotPreClose" -Action $preCloseAction -Trigger $preCloseTrigger -Description "Oracle pre-close dry-run by default"

# Post-match 23:30
# $postMatchAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ProjectRoot\scripts\oracle_post_match.ps1`""
# $postMatchTrigger = New-ScheduledTaskTrigger -Daily -At 23:30
# Register-ScheduledTask -TaskName "OracleFootballBotPostMatch" -Action $postMatchAction -Trigger $postMatchTrigger -Description "Oracle post-match dry-run by default"

Write-Host "Exemples de taches Windows prets. Rien n'a ete enregistre automatiquement."
