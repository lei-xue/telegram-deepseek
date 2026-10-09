# telegram-deepseek
A personal AI companion you chat with on **Telegram**. It runs on the **DeepSeek API**, on **OpenRouter**, or fully self-hosted on a **local model** with [Ollama](https://ollama.com), so you can talk from your phone to an AI running on your own computer.

## Features
- **Memory:** remembers the conversation per chat and survives restarts (`data/`). When recent messages outgrow their budget (half of `CONTEXT_TOKENS`), the oldest ones are folded into a long-term memory summary. The model can also save important facts right away with its `remember` tool. `/memory` shows it, `/reset` clears it.
- **Soul and user profile:** `soul.md` describes the assistant (name, tone, principles) and `user.md` describes you (name, city and time zone, language, interests, preferred style, topics to avoid). Both are read on every message, so edits apply immediately. If `user.md` does not exist, the bot asks three quick questions in the first chat (name, city, preferred style; each can be skipped) and writes it for you. Everything else is learned as you chat, or added any time with `/profile <field> <value>` (e.g. `/profile about cats and hiking`). `/profile` shows the profile and `/setup` asks the questions again. The bot knows the current time in your time zone.
- **Web search:** the model can call `web_search` (DuckDuckGo, no API key) and `open_url` when it needs current information. Only the search query leaves your machine. Turn off with `WEB_SEARCH=off`.
- **Reliable tool use with small models:** replies that claim a search or a saved fact without calling the tool, or that refuse a factual question, are sent back once to use the tool.
- **Model buttons:** `/model` shows a button per model (`MODELS`, or everything the server lists).
- **Any language:** bot texts are English by default; add a `locale.json` for another language (see below).
- Markdown replies are rendered as Telegram formatting; long replies are split.
- `/code <question>` for one-off coding help.
- Only answers user IDs in `ALLOWED_USER_IDS`; anyone else just gets their own user ID back.

## Choose a backend
| | Needs | Set in `.env` |
| --- | --- | --- |
| **DeepSeek API** | A [DeepSeek](https://platform.deepseek.com) API key | `DEEPSEEK_API_KEY` (the default backend, model `deepseek-chat`) |
| **OpenRouter** | An [OpenRouter](https://openrouter.ai) API key; gives access to DeepSeek and many other models | `OPENAI_BASE_URL=https://openrouter.ai/api/v1`, `OPENAI_API_KEY`, `MODEL=deepseek/deepseek-v4.1-flash` |
| **Local model** | A computer with [Ollama](https://ollama.com); a GPU with 6–8 GB VRAM runs 4B models well. Nothing leaves your machine except web searches | `OPENAI_BASE_URL=http://127.0.0.1:11434/v1`, `MODEL` |

The cloud backends need no GPU, so the bot can run on any small computer or VPS. Any other OpenAI-compatible server works the same way through `OPENAI_BASE_URL`, `OPENAI_API_KEY` and `MODEL`.

For local reasoning models such as qwen3.5, `REASONING_EFFORT=none` skips the thinking phase and makes replies much faster.

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

## Setup
1. Create a bot with [@BotFather](https://t.me/BotFather) and copy its token.
2. `cp .env_sample .env`, fill in `TELEGRAM_BOT_TOKEN` and the settings for your backend. Leave `ALLOWED_USER_IDS` empty for now.
3. `cp soul.example.md soul.md` and adjust the assistant's character. Optionally `cp user.example.md user.md` and fill it in yourself, or let the bot ask on the first chat.
4. Start the bot, message it from Telegram, and put the user ID it replies with into `ALLOWED_USER_IDS`. Restart the bot.

## Language
Texts the bot shows and the phrases it uses to check replies are English by default. To use another language, create `locale.json` next to `main.py` (it is git-ignored):
```json
{
  "texts": {
    "intro": "...",
    "question_name": "...",
    "question_city": "...",
    "question_style": "...",
    "style_options": ["...", "...", "..."],
    "skip": "...",
    "done": "...",
    "profile_help": "...",
    "no_profile": "...",
    "memory_hint": "...",
    "name_hint": "... {name} ...",
    "field_aliases": {"about": ["..."]}
  },
  "patterns": {
    "claims_search": "regex",
    "claims_remember": "regex",
    "refusal": "regex",
    "question": "regex",
    "writing_request": "regex",
    "offer": "regex",
    "sentence_end": "characters"
  }
}
```
Every key is optional. `texts` replace the English defaults in `i18n.py`; `patterns` are regex alternatives added to the English ones, so the reply checks also work in your language. Write `soul.md` in the language you want the assistant to use.

## Run
**Python**
```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt   # Windows: .venv\Scripts\pip
.venv/bin/python main.py
```

**Docker**: `docker compose up -d --build`. To reach Ollama on the host from the container, use `OPENAI_BASE_URL=http://host.docker.internal:11434/v1`.

**Windows, start at logon**: `start-windows.ps1` runs the bot from `.venv`, restarts it if it exits and writes `bot.log`. Register it once in PowerShell:
```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PWD\start-windows.ps1`""
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0
Register-ScheduledTask -TaskName "telegram-ai-bot" -Action $action -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME) -Settings $settings
```
The bot is offline while the computer sleeps.
