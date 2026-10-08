# Runs the bot from the local .venv and restarts it if it exits. Output goes to bot.log.
Set-Location $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"
while ($true) {
    "$(Get-Date -Format s) starting bot" | Add-Content -Encoding utf8 bot.log
    cmd /c ".venv\Scripts\python.exe -u main.py >> bot.log 2>&1"
    "$(Get-Date -Format s) bot exited with code $LASTEXITCODE, restarting in 10s" | Add-Content -Encoding utf8 bot.log
    Start-Sleep -Seconds 10
}
