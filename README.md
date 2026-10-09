# deepseek-telegram
This is an hobby project based using deepseek **AI API** to chat at **Telegram Bot** and host it using **Docker**

It also works with any OpenAI-compatible server, including a **local [Ollama](https://ollama.com)** model, so you can chat from your phone with an AI running on your own computer.

## Features
- **Memory:** remembers the conversation per chat and survives restarts (`data/`). When recent messages outgrow their budget (half of `CONTEXT_TOKENS`), the oldest ones are folded into a long-term memory summary. The model can also save important facts right away with its `remember` tool. `/memory` shows it, `/reset` clears it.
- **Soul and user profile:** `soul.md` describes the assistant (name, tone, principles) and `user.md` describes you (name, city and time zone, language, interests, preferred style, topics to avoid). Both are read on every message, so edits apply immediately. If `user.md` does not exist, the bot asks six quick questions in the first chat (each can be skipped) and writes it for you; `/profile` shows it and `/setup` asks again. The bot knows the current time in your time zone.
- **Web search:** the model can call `web_search` (DuckDuckGo, no API key) and `open_url` when it needs current information. Only the search query leaves your machine. Turn off with `WEB_SEARCH=off`.
- **Model buttons:** `/model` shows a button per model (`MODELS`, or everything the server lists).
- Markdown replies are rendered as Telegram formatting; long replies are split.
- `/code <question>` for one-off coding help.
- Only answers user IDs in `ALLOWED_USER_IDS`; anyone else just gets their own user ID back.

## Setup
1. Create a bot with [@BotFather](https://t.me/BotFather) and copy its token.
2. `cp .env_sample .env` and fill in `TELEGRAM_BOT_TOKEN`. Leave `ALLOWED_USER_IDS` empty for now.
3. `cp soul.example.md soul.md` and adjust the assistant's character. Optionally `cp user.example.md user.md` and fill it in yourself, or let the bot ask on the first chat.
4. Pick a backend in `.env`:
   - **DeepSeek:** set `DEEPSEEK_API_KEY`.
   - **Local Ollama:** set `OPENAI_BASE_URL=http://127.0.0.1:11434/v1` and `MODEL`. For reasoning models such as qwen3.5, `REASONING_EFFORT=none` skips the thinking phase and makes replies much faster.
5. Start the bot, message it from Telegram, and put the user ID it replies with into `ALLOWED_USER_IDS`. Restart the bot.

### Ollama context size
Ollama's OpenAI-compatible endpoint runs models with a 4096-token context by default and silently drops the oldest text beyond that. Create a variant with a larger window and set `CONTEXT_TOKENS` to match:
```
# Modelfile
FROM qwen3.5:4b
PARAMETER num_ctx 32768
```
```bash
ollama create qwen3.5-chat:4b -f Modelfile
```
If you offer several models, set `CONTEXT_TOKENS` to the smallest window among them.

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
