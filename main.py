import os
from dotenv import load_dotenv
from telegram.ext import Application
from handler import setup_handlers
from openai import AsyncOpenAI
from teleCtrl import set_commands

load_dotenv()


def main():
    # Works with any OpenAI-compatible endpoint: DeepSeek (default) or a local Ollama server
    # (OPENAI_BASE_URL=http://127.0.0.1:11434/v1). Ollama ignores the key but the client needs one.
    client = AsyncOpenAI(
        api_key=os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or "ollama",
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com"),
        timeout=float(os.getenv("REQUEST_TIMEOUT", "300")),
    )
    teletoken = os.getenv("TELEGRAM_BOT_TOKEN")

    async def post_init(application):
        # Set commands for the bot if not already set
        await set_commands(application.bot)

    application = Application.builder().token(teletoken).post_init(post_init).build()
    setup_handlers(application, client)

    # Run the bot until Ctrl-C is pressed or the process receives SIGINT, SIGTERM, or SIGABRT
    print(f"Bot started. Model: {os.getenv('MODEL', 'deepseek-chat')}", flush=True)
    application.run_polling()


if __name__ == '__main__':
    main()
