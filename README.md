# telegram-deepseek
A personal AI companion on **Telegram**, powered by the **DeepSeek API**, **OpenRouter**, or a **local model** via [Ollama](https://ollama.com).

## Features
- **Memory:** per-chat history that survives restarts (`data/`); older messages are folded into a long-term summary, and the model saves key facts with its `remember` tool.
- **Soul and user profile:** `soul.md` is the assistant's character, `user.md` is you. Without `user.md`, the first chat asks 3 skippable questions (name, city, style) and writes it.
- **Web search:** DuckDuckGo search and page reading when needed, no API key. Turn off with `WEB_SEARCH=off`.
- **Any language:** English by default; `locale.json` translates the bot texts and reply checks.
- **Private:** only answers `ALLOWED_USER_IDS`; anyone else gets their own user ID back.

## Commands
| Command | What it does |
| --- | --- |
| `/model` | Pick a model from buttons (`MODELS`, or all models the server lists) |
| `/memory` | Show recent-message usage and long-term memory |
| `/profile [field value]` | Show `user.md`, or set one field, e.g. `/profile about cats and hiking` |
| `/setup` | Ask the first-chat questions again |
| `/code <question>` | One-off coding help (`CODE_MODEL`, defaults to `MODEL`) |
| `/reset` | Forget the conversation and memory |

## Choose a backend
| | Needs | Set in `.env` |
| --- | --- | --- |
| **DeepSeek API** | A [DeepSeek](https://platform.deepseek.com) API key | `DEEPSEEK_API_KEY` (the default backend, model `deepseek-chat`) |
| **OpenRouter** | An [OpenRouter](https://openrouter.ai) API key; gives access to DeepSeek and many other models | `OPENAI_BASE_URL=https://openrouter.ai/api/v1`, `OPENAI_API_KEY`, `MODEL=deepseek/deepseek-v4.1-flash` |
| **Local model** | A computer with [Ollama](https://ollama.com); a GPU with 6–8 GB VRAM runs 4B models well. Nothing leaves your machine except web searches | `OPENAI_BASE_URL=http://127.0.0.1:11434/v1`, `MODEL` |

Any other OpenAI-compatible server works through `OPENAI_BASE_URL`, `OPENAI_API_KEY` and `MODEL`.

**Ollama tip:** Ollama's default context is 4096 tokens. Create a variant with a Modelfile (`FROM qwen3.5:4b` + `PARAMETER num_ctx 32768`, then `ollama create qwen3.5-chat:4b -f Modelfile`) and set `CONTEXT_TOKENS=32768` to match. For reasoning models, `REASONING_EFFORT=none` makes replies much faster.

## Setup
1. Create a bot with [@BotFather](https://t.me/BotFather) and copy its token.
2. `cp .env_sample .env`, fill in `TELEGRAM_BOT_TOKEN` and your backend. Leave `ALLOWED_USER_IDS` empty for now.
3. `cp soul.example.md soul.md` and adjust the character. Optionally `cp user.example.md user.md`.
4. Start the bot, message it, put the user ID it replies with into `ALLOWED_USER_IDS`, and restart.

Optional, for another language: `cp locale.example.json locale.json` and translate the `texts`. `patterns` take regex alternatives for your language (empty = English only). Write `soul.md` in that language too.

## Run
**Python**
```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt   # Windows: .venv\Scripts\pip
.venv/bin/python main.py
```

**Docker:** `docker compose up -d --build`. To reach Ollama on the host, use `OPENAI_BASE_URL=http://host.docker.internal:11434/v1`.

**Windows, start at logon:** `start-windows.ps1` runs the bot from `.venv`, restarts it if it exits and writes `bot.log`. The command to register it as a scheduled task is in the header comment of that file.
