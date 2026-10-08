# deepseek-telegram
This is an hobby project based using deepseek **AI API** to chat at **Telegram Bot** and host it using **Docker**

It also works with any OpenAI-compatible server, including a **local [Ollama](https://ollama.com)** model, so you can chat from your phone with an AI running on your own computer.

## Features
- Remembers the conversation per chat (last `HISTORY_TURNS` exchanges); `/reset` forgets it
- `/model` lists the server's models and switches the model for the current chat
- `/code <question>` for one-off coding help
- Shows "typing…" while the model works and splits replies longer than Telegram's 4096-character limit
- Only answers user IDs in `ALLOWED_USER_IDS`; anyone else just gets their own user ID back

## Setup
1. Create a bot with [@BotFather](https://t.me/BotFather) and copy its token.
2. `cp .env_sample .env` and fill in `TELEGRAM_BOT_TOKEN`. Leave `ALLOWED_USER_IDS` empty for now.
3. Pick a backend in `.env`:
   - **DeepSeek:** set `DEEPSEEK_API_KEY`.
   - **Local Ollama:** set `OPENAI_BASE_URL=http://127.0.0.1:11434/v1` and `MODEL` to a model from `ollama list`. For reasoning models such as qwen3.5, `REASONING_EFFORT=none` skips the thinking phase and makes replies much faster.
4. Start the bot, message it from Telegram, and put the user ID it replies with into `ALLOWED_USER_IDS`. Restart the bot.

## Run
**Python**
```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt   # Windows: .venv\Scripts\pip
.venv/bin/python main.py
```

**Docker** (DeepSeek): `docker compose up -d --build`. To reach Ollama on the host from the container, use `OPENAI_BASE_URL=http://host.docker.internal:11434/v1`.

**Windows, start at logon**: `start-windows.ps1` runs the bot from `.venv`, restarts it if it exits and writes `bot.log`. Register it once in PowerShell:
```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PWD\start-windows.ps1`""
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0
Register-ScheduledTask -TaskName "telegram-ai-bot" -Action $action -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME) -Settings $settings
```
The bot is offline while the computer sleeps.
