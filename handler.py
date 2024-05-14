from telegram.ext import CommandHandler, MessageHandler, filters
import os
from dotenv import load_dotenv
load_dotenv()

AUTHORIZED_USERS = list(map(int, os.environ["ALLOWED_USER_IDS"].split(",")))

async def start(update, context):
    user_id = update.effective_user.id
    if user_id not in AUTHORIZED_USERS:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Sorry, you are not authorized to use this bot.")
        return
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Hello! I'm an AI-powered chatbot. Type /help to see available commands")

async def chat(update, context):
    user_id = update.effective_user.id
    if user_id not in AUTHORIZED_USERS:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Sorry, you are not authorized to use this bot.")
        return
    
    user_message = update.message.text
    client = context.bot_data["client"]
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": user_message},
        ],
        max_tokens=1024,
        temperature=1.0,
        stream=False
    )
    ai_response = response.choices[0].message.content
    await context.bot.send_message(chat_id=update.effective_chat.id, text=ai_response)

async def code(update, context):
    user_id = update.effective_user.id
    if user_id not in AUTHORIZED_USERS:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Sorry, you are not authorized to use this bot.")
        return
    
    user_message = update.message.text[len('/code '):]
    client = context.bot_data["client"]
    response = client.chat.completions.create(
        model="deepseek-coder",
        messages=[
            {"role": "system", "content": "You are a code assistant"},
            {"role": "user", "content": user_message},
        ],
        max_tokens=1024,
        stream=False,
    )
    ai_response = response.choices[0].message.content
    await context.bot.send_message(chat_id=update.effective_chat.id, text=ai_response)

async def reset(update, context):
    user_id = update.effective_user.id
    if user_id not in AUTHORIZED_USERS:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Sorry, you are not authorized to use this bot.")
        return
    
    chat_id = update.effective_chat.id
    bot_messages = context.user_data.get("bot_messages", [])

    for message_id in bot_messages:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            print(f"Failed to delete message {message_id}: {str(e)}")

    
    context.user_data.clear()

    await context.bot.send_message(chat_id=chat_id, text="User data has been reset. Let's start over!")


def setup_handlers(application, client):
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("code", code))
    application.add_handler(CommandHandler("chat", chat))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    
    application.bot_data["client"] = client