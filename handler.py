import asyncio
import contextlib
import os
import time
from functools import wraps

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters

import memory
import tools
from tgformat import split_message, to_html

load_dotenv()

AUTHORIZED_USERS = [int(x) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip().isdigit()]
MODEL = os.getenv("MODEL", "deepseek-chat")
CODE_MODEL = os.getenv("CODE_MODEL") or MODEL
# Models offered by /model; when empty, every model the server lists (except embedding models)
MODELS = [m.strip() for m in os.getenv("MODELS", "").split(",") if m.strip()]
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2048"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "1.0"))
# Optional. "none" turns off the thinking phase of local reasoning models (e.g. qwen3.5 on Ollama).
REASONING_EFFORT = os.getenv("REASONING_EFFORT", "").strip()
WEB_SEARCH = os.getenv("WEB_SEARCH", "on").lower() in ("on", "true", "1", "yes")
MAX_TOOL_ROUNDS = 4


def authorized(func):
    @wraps(func)
    async def wrapper(update, context):
        user_id = update.effective_user.id
        if user_id not in AUTHORIZED_USERS:
            print(f"Unauthorized user {user_id} (@{update.effective_user.username})", flush=True)
            if update.callback_query:
                await update.callback_query.answer()
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


@contextlib.asynccontextmanager
async def typing(bot, chat_id):
    task = asyncio.create_task(keep_typing(bot, chat_id))
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


async def show_status(bot, chat_id, status, text):
    if status is None:
        return await bot.send_message(chat_id=chat_id, text=text, link_preview_options=LinkPreviewOptions(is_disabled=True))
    with contextlib.suppress(BadRequest):
        await status.edit_text(text, link_preview_options=LinkPreviewOptions(is_disabled=True))
    return status


async def complete(context, chat_id, model, messages, use_tools=False, data=None):
    """Run the model, letting it call tools for up to MAX_TOOL_ROUNDS rounds.

    use_tools offers the web tools; passing the chat's data also offers the remember tool.
    """
    client = context.bot_data["client"]
    extra = {"reasoning_effort": REASONING_EFFORT} if REASONING_EFFORT else None
    specs = ([memory.REMEMBER_SCHEMA] if data is not None else []) + (tools.SCHEMAS if use_tools else [])
    messages = list(messages)
    status = None
    try:
        for round_ in range(MAX_TOOL_ROUNDS + 1):
            offer_tools = specs and round_ < MAX_TOOL_ROUNDS
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                stream=False,
                extra_body=extra,
                **({"tools": specs} if offer_tools else {}),
            )
            message = response.choices[0].message
            if not message.tool_calls:
                return (message.content or "").strip() or "(empty response)"

            messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
                    for c in message.tool_calls
                ],
            })
            for call in message.tool_calls:
                name, arguments = call.function.name, call.function.arguments
                if name == "remember" and data is not None:
                    result = memory.remember(data, arguments)
                else:
                    status = await show_status(context.bot, chat_id, status, tools.describe(name, arguments))
                    result = await tools.run(name, arguments)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
    finally:
        if status is not None:
            with contextlib.suppress(BadRequest):
                await status.delete()


async def send_reply(bot, chat_id, text):
    for chunk in split_message(text):
        try:
            await bot.send_message(chat_id=chat_id, text=to_html(chunk), parse_mode=ParseMode.HTML,
                                   link_preview_options=LinkPreviewOptions(is_disabled=True))
        except BadRequest:
            # Unbalanced formatting: fall back to plain text
            await bot.send_message(chat_id=chat_id, text=chunk)


async def send_error(context, chat_id, error):
    print(f"Model error: {error!r}", flush=True)
    await context.bot.send_message(chat_id=chat_id, text=f"Model error: {error}")


@authorized
async def start(update, context):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Hello! I'm an AI-powered chatbot. Type /help to see available commands")


@authorized
async def chat(update, context):
    chat_id = update.effective_chat.id
    user_message = message_text(update, context)
    if not user_message:
        await context.bot.send_message(chat_id=chat_id, text="Send me a message to chat.")
        return

    data = context.chat_data
    model = data.get("model", MODEL)
    async with typing(context.bot, chat_id):
        try:
            await memory.compact(data, lambda messages: complete(context, chat_id, model, messages))
            hints = [memory.MEMORY_HINT] + ([tools.PROMPT_HINT] if WEB_SEARCH else [])
            messages = [
                {"role": "system", "content": memory.system_prompt(data, hints)},
                *data.get("history", []),
                {"role": "user", "content": user_message},
            ]
            ai_response = await complete(context, chat_id, model, messages, use_tools=WEB_SEARCH, data=data)
        except Exception as e:
            await send_error(context, chat_id, e)
            return

    data.setdefault("history", []).extend([
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": ai_response},
    ])
    data["last_ts"] = time.time()
    await send_reply(context.bot, chat_id, ai_response)


@authorized
async def code(update, context):
    chat_id = update.effective_chat.id
    user_message = message_text(update, context)
    if not user_message:
        await context.bot.send_message(chat_id=chat_id, text="Usage: /code <your question>")
        return

    messages = [
        {"role": "system", "content": "You are a code assistant"},
        {"role": "user", "content": user_message},
    ]
    async with typing(context.bot, chat_id):
        try:
            ai_response = await complete(context, chat_id, CODE_MODEL, messages)
        except Exception as e:
            await send_error(context, chat_id, e)
            return
    await send_reply(context.bot, chat_id, ai_response)


def model_keyboard(models, current):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(("✅ " if name == current else "") + name, callback_data=f"model:{i}")]
        for i, name in enumerate(models)
    ])


@authorized
async def model(update, context):
    chat_id = update.effective_chat.id
    if context.args:
        context.chat_data["model"] = context.args[0]
        await context.bot.send_message(chat_id=chat_id, text=f"Model switched to {context.args[0]}")
        return

    current = context.chat_data.get("model", MODEL)
    try:
        models = MODELS or sorted([m.id async for m in context.bot_data["client"].models.list() if "embed" not in m.id])
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"Current model: {current}\n\nCould not list models: {e}")
        return
    # Buttons carry an index (callback data is limited to 64 bytes), so remember the list
    context.chat_data["model_choices"] = models
    await context.bot.send_message(chat_id=chat_id, text=f"Current model: {current}\nTap to switch:",
                                   reply_markup=model_keyboard(models, current))


@authorized
async def model_button(update, context):
    query = update.callback_query
    choices = context.chat_data.get("model_choices", [])
    index = int(query.data.split(":", 1)[1])
    if index >= len(choices):
        await query.answer("This list is out of date, send /model again")
        return
    context.chat_data["model"] = choices[index]
    await query.answer(f"Switched to {choices[index]}")
    with contextlib.suppress(BadRequest):
        await query.edit_message_text(f"Current model: {choices[index]}\nTap to switch:",
                                      reply_markup=model_keyboard(choices, choices[index]))


@authorized
async def show_memory(update, context):
    data = context.chat_data
    history = data.get("history", [])
    text = (f"Recent messages: {len(history)} (~{memory.history_tokens(history)} of {memory.HISTORY_BUDGET} tokens)\n\n"
            f"Long-term memory:\n{data.get('summary') or '(nothing yet)'}")
    for chunk in split_message(text):
        await context.bot.send_message(chat_id=update.effective_chat.id, text=chunk)


@authorized
async def reset(update, context):
    for key in ("history", "summary", "last_ts"):
        context.chat_data.pop(key, None)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Conversation and memory have been reset. Let's start over!")


@authorized
async def help_command(update, context):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Just send a message to chat — I remember the conversation"
             + (" and can search the web" if WEB_SEARCH else "") + ".\n\n"
             "/model – switch the model\n"
             "/memory – show what I remember\n"
             "/code <question> – one-off coding help\n"
             "/reset – forget the conversation and memory",
    )


def setup_handlers(application, client):
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("code", code))
    application.add_handler(CommandHandler("chat", chat))
    application.add_handler(CommandHandler("model", model))
    application.add_handler(CommandHandler("memory", show_memory))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CallbackQueryHandler(model_button, pattern=r"^model:\d+$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    application.bot_data["client"] = client
