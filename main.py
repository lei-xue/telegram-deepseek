import os
import asyncio
from dotenv import load_dotenv
from telegram.ext import Application
from handler import setup_handlers
from openai import OpenAI
from teleCtrl import set_commands

load_dotenv()

async def main():
    client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
    teletoken = os.getenv("TELEGRAM_BOT_TOKEN")
    application = Application.builder().token(teletoken).build()
    

    try:
        await application.initialize()
        setup_handlers(application, client)

        # Set commands for the bot if not already set
        await set_commands(application.bot)

        # Run the bot until Ctrl-C is pressed or the process receives SIGINT, SIGTERM, or SIGABRT
        await application.start()
        await application.updater.start_polling()
        await asyncio.Event().wait()
    finally:
        # Gracefully shutdown the application
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        await application.updater.shutdown()

if __name__ == '__main__':
    asyncio.run(main())