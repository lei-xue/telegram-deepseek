# Runs the bot from the local .venv and restarts it if it exits. Output goes to bot.log.
#
# To start it at logon, register a scheduled task once (PowerShell, in the repository folder):
#   $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PWD\start-windows.ps1`""
#   $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0
#   Register-ScheduledTask -TaskName "telegram-ai-bot" -Action $action -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME) -Settings $settings
# The bot is offline while the computer sleeps.
Set-Location $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"
while ($true) {
    "$(Get-Date -Format s) starting bot" | Add-Content -Encoding utf8 bot.log
    cmd /c ".venv\Scripts\python.exe -u main.py >> bot.log 2>&1"
    "$(Get-Date -Format s) bot exited with code $LASTEXITCODE, restarting in 10s" | Add-Content -Encoding utf8 bot.log
    Start-Sleep -Seconds 10
}
