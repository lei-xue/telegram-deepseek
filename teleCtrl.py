
from telegram import BotCommand

async def set_commands(bot):
    commands = (
        BotCommand("start", "Start the bot and get a welcome message"),
        BotCommand("help", "Show available commands"),
        BotCommand("chat", "Send this to start chatting with the bot"),
        BotCommand("code", "Use this to get coding help"),
        BotCommand("model", "Show or switch the AI model"),
        BotCommand("reset", "Forget the conversation"),
    )
    existing_commands = await bot.get_my_commands()
    if existing_commands != commands:
        await bot.set_my_commands(commands=commands)
        print("Commands set successfully.")
    else:
        print("Commands are already set.")
