import asyncio
import contextlib
import os
from functools import wraps

from dotenv import load_dotenv
from telegram.constants import ChatAction
from telegram.ext import CommandHandler, MessageHandler, filters

load_dotenv()

AUTHORIZED_USERS = [int(x) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip().isdigit()]
MODEL = os.getenv("MODEL", "deepseek-chat")
CODE_MODEL = os.getenv("CODE_MODEL") or MODEL
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "You are a helpful assistant")
HISTORY_TURNS = int(os.getenv("HISTORY_TURNS", "20"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2048"))
# Optional. "none" turns off the thinking phase of local reasoning models (e.g. qwen3.5 on Ollama).
REASONING_EFFORT = os.getenv("REASONING_EFFORT", "").strip()

TELEGRAM_LIMIT = 4096


def authorized(func):
    @wraps(func)
    async def wrapper(update, context):
        user_id = update.effective_user.id
        if user_id not in AUTHORIZED_USERS:
            print(f"Unauthorized user {user_id} (@{update.effective_user.username})", flush=True)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Sorry, you are not authorized to use this bot.\nYour user ID: {user_id}",
            )
            return
        await func(update, context)
    return wrapper


def message_text(update, context):
    # "/chat hello" -> "hello"; plain messages pass through unchanged
    if context.args is not None:
        return " ".join(context.args)
    return update.message.text


async def keep_typing(bot, chat_id):
    # Telegram clears the "typing…" status after ~5s, so refresh it until the reply is ready
    while True:
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        await asyncio.sleep(4)


async def complete(context, model, messages):
    extra = {"reasoning_effort": REASONING_EFFORT} if REASONING_EFFORT else None
    response = await context.bot_data["client"].chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=MAX_TOKENS,
        temperature=1.0,
        stream=False,
        extra_body=extra,
    )
    return (response.choices[0].message.content or "").strip() or "(empty response)"


async def reply(update, context, model, messages):
    chat_id = update.effective_chat.id
    typing = asyncio.create_task(keep_typing(context.bot, chat_id))
    try:
        ai_response = await complete(context, model, messages)
    finally:
        typing.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await typing

    for i in range(0, len(ai_response), TELEGRAM_LIMIT):
        await context.bot.send_message(chat_id=chat_id, text=ai_response[i:i + TELEGRAM_LIMIT])
    return ai_response


async def send_error(update, context, error):
    print(f"Model error: {error!r}", flush=True)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Model error: {error}")


@authorized
async def start(update, context):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Hello! I'm an AI-powered chatbot. Type /help to see available commands")


@authorized
async def chat(update, context):
    user_message = message_text(update, context)
    if not user_message:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Send me a message to chat.")
        return

    history = context.chat_data.setdefault("history", [])
    model = context.chat_data.get("model", MODEL)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history, {"role": "user", "content": user_message}]
    try:
        ai_response = await reply(update, context, model, messages)
    except Exception as e:
        await send_error(update, context, e)
        return

    history += [{"role": "user", "content": user_message}, {"role": "assistant", "content": ai_response}]
    del history[:-HISTORY_TURNS * 2]


@authorized
async def code(update, context):
    user_message = message_text(update, context)
    if not user_message:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Usage: /code <your question>")
        return

    messages = [
        {"role": "system", "content": "You are a code assistant"},
        {"role": "user", "content": user_message},
    ]
    try:
        await reply(update, context, CODE_MODEL, messages)
    except Exception as e:
        await send_error(update, context, e)


@authorized
async def model(update, context):
    chat_id = update.effective_chat.id
    if context.args:
        context.chat_data["model"] = context.args[0]
        await context.bot.send_message(chat_id=chat_id, text=f"Model switched to {context.args[0]}")
        return

    current = context.chat_data.get("model", MODEL)
    try:
        available = [m.id async for m in context.bot_data["client"].models.list()]
    except Exception as e:
        available = [f"(could not list models: {e})"]
    lines = [f"Current model: {current}", "", "Available:", *available, "", "Switch with /model <name>"]
    await context.bot.send_message(chat_id=chat_id, text="\n".join(lines))


@authorized
async def reset(update, context):
    context.chat_data.clear()
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Conversation has been reset. Let's start over!")


@authorized
async def help_command(update, context):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Just send a message to chat — I remember the conversation.\n\n"
             "/code <question> – one-off coding help\n"
             "/model – show or switch the model\n"
             "/reset – forget the conversation",
    )


def setup_handlers(application, client):
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("code", code))
    application.add_handler(CommandHandler("chat", chat))
    application.add_handler(CommandHandler("model", model))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    application.bot_data["client"] = client
