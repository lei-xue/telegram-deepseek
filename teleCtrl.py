
from telegram import BotCommand

async def set_commands(bot):
    commands = (
        BotCommand("start", "Start the bot and get a welcome message"),
        BotCommand("help", "Show available commands"),
        BotCommand("model", "Switch the AI model"),
        BotCommand("memory", "Show what the bot remembers"),
        BotCommand("profile", "What the bot knows about you"),
        BotCommand("setup", "Answer the get-to-know-you questions again"),
        BotCommand("code", "Use this to get coding help"),
        BotCommand("reset", "Forget the conversation and memory"),
    )
    existing_commands = await bot.get_my_commands()
    if existing_commands != commands:
        await bot.set_my_commands(commands=commands)
        print("Commands set successfully.")
    else:
        print("Commands are already set.")
