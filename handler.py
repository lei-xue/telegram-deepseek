import asyncio
import contextlib
import json
import os
import re
import time
from functools import wraps
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters

import memory
import onboarding
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
# Tool results kept in the chat history so the model sees how earlier answers were found
TRACE_CHARS = 600

CLAIMS_SEARCH = re.compile(
    r"(让我|我来|我帮你|帮你|我去)(查|搜)|查一下|搜一下|查了一下|搜索结果|查询结果|根据(最新的?|刚才的?)?(搜索|查询|预报)|🔍"
    r"|let me (check|search|look)|I('ll| will) (check|search|look)|according to (the )?(search|latest)",
    re.I,
)
# Some models (e.g. Spark-X2.5) occasionally emit tool calls as GLM-style text tags
TEXT_TOOL_CALL = re.compile(r"<tool_call>\s*([\w.-]+)(.*?)</tool_call>", re.S)
TEXT_TOOL_ARG = re.compile(r"<arg_key>(.*?)</arg_key>\s*<arg_value>(.*?)</arg_value>", re.S)
CLAIMS_REMEMBER = re.compile(r"记住了|记下(来)?了|帮你记|我会记住|已经记|noted|I('ll| will) remember|I've saved", re.I)
REFUSAL = re.compile(
    r"(无法|不能|不便|不予|不会)(为你|为您|对此|就此)?(提供|回答|讨论|解答|回应|作出|评论|教你)|不适合讨论|敏感(话题|内容|问题|议题)"
    r"|违反.{0,8}(法律|法规)|不予置评|换个话题|I can(not|'t) (help|provide|discuss)",
    re.I,
)
QUESTION = re.compile(r"[？?]|什么|怎么|为什么|多少|几|谁|哪|是否|是不是|吗|how|what|why|who|which|when|is it", re.I)
WRITING_REQUEST = re.compile(r"写|编|故事|小说|剧情|扮演|角色|场景|续|write|story|roleplay", re.I)
NUDGE = {
    "refusal": "[System] The user asked a factual question. Do not refuse. Call web_search, then summarize what the "
               "sources say, presenting the main viewpoints neutrally and naming the sources. For political or "
               "international topics, also search in English and include international sources.",
    "web_search": "[System] Your last reply said you searched or would search, but you did not call web_search. "
                  "Call web_search now and answer only from its results. Do not make up data.",
    "remember": "[System] Your last reply said you saved it, but you did not call remember. "
                "Call remember now with a short fact, then reply.",
}


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


def text_tool_calls(text):
    """Parse tool calls that a model wrote as text tags and the server did not recognise."""
    calls = []
    for i, match in enumerate(TEXT_TOOL_CALL.finditer(text)):
        args = {k.strip(): v.strip() for k, v in TEXT_TOOL_ARG.findall(match.group(2))}
        calls.append(SimpleNamespace(id=f"text_call_{i}", function=SimpleNamespace(
            name=match.group(1), arguments=json.dumps(args, ensure_ascii=False))))
    return calls


def is_factual_question(text):
    return bool(text) and bool(QUESTION.search(text)) and not WRITING_REQUEST.search(text)


def missed_tool(text, used, use_tools, can_remember, question=None):
    """Name the tool a reply should have called but did not, if any."""
    # Offers such as "要不要我帮你查一下？" are fine; only statements count
    statements = " ".join(s for s in re.findall(r"[^。！？!?\n]+[。！？!?]?", text) if not re.search(r"[？?]|吗|呢", s))
    searched = bool(used & {"web_search", "open_url"})
    if use_tools and not searched and CLAIMS_SEARCH.search(statements):
        return "web_search"
    # Refusing a factual question: look it up and report what sources say instead
    if use_tools and not searched and REFUSAL.search(text[:300]) and is_factual_question(question):
        return "refusal"
    if can_remember and "remember" not in used and CLAIMS_REMEMBER.search(statements):
        return "remember"
    return None


async def complete(context, chat_id, model, messages, use_tools=False, data=None, trace=None, question=None):
    """Run the model, letting it call tools for up to MAX_TOOL_ROUNDS rounds.

    use_tools offers the web tools; passing the chat's data also offers the remember tool.
    Tool calls and their (shortened) results are appended to `trace` when given.
    """
    client = context.bot_data["client"]
    extra = {"reasoning_effort": REASONING_EFFORT} if REASONING_EFFORT else None
    specs = ([memory.REMEMBER_SCHEMA] if data is not None else []) + (tools.SCHEMAS if use_tools else [])
    messages = list(messages)
    status = None
    used, nudged = set(), False
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
            content = message.content or ""
            calls = message.tool_calls or (text_tool_calls(content) if offer_tools else [])
            content = TEXT_TOOL_CALL.sub("", content).strip()
            if not calls:
                text = content
                # Small models sometimes say "let me check" or "noted" and then make the answer up.
                # Send it back once and ask for the real tool call.
                missed = offer_tools and not nudged and missed_tool(text, used, use_tools, data is not None, question)
                if not missed:
                    return text or "(empty response)"
                nudged = True
                print(f"Reply claimed {missed} without calling it; asking again", flush=True)
                messages += [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": NUDGE[missed]},
                ]
                continue

            step = [{
                "role": "assistant",
                "content": content,
                "tool_calls": [
                    {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
                    for c in calls
                ],
            }]
            for call in calls:
                name, arguments = call.function.name, call.function.arguments
                used.add(name)
                if name == "remember" and data is not None:
                    result = memory.remember(data, arguments)
                else:
                    status = await show_status(context.bot, chat_id, status, tools.describe(name, arguments))
                    result = await tools.run(name, arguments)
                step.append({"role": "tool", "tool_call_id": call.id, "content": result})
            messages += step
            if trace is not None:
                trace += [dict(m, content=m["content"][:TRACE_CHARS]) for m in step]
        return "(no answer after several tool calls)"
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


async def resolve_timezone(context, model, place):
    """IANA time zone for a city (or a time zone typed directly); falls back to TIMEZONE."""
    def valid(name):
        try:
            ZoneInfo(name)
            return True
        except Exception:
            return False

    if valid(place.strip()):
        return place.strip()
    try:
        text = await complete(context, None, model, [{"role": "user", "content":
            f"What is the IANA time zone name for this place: {place}? Reply with only the name, e.g. America/Los_Angeles."}])
        match = re.search(r"[A-Za-z]+(?:/[A-Za-z0-9_+-]+)+", text)
        if match and valid(match.group(0)):
            return match.group(0)
    except Exception as e:
        print(f"Time zone lookup failed: {e!r}", flush=True)
    return memory.TIMEZONE


async def onboarding_answer(context, chat_id, value):
    model = context.chat_data.get("model", MODEL)
    await onboarding.answer(context.bot, chat_id, context.chat_data, value,
                            lambda place: resolve_timezone(context, model, place))


@authorized
async def start(update, context):
    chat_id = update.effective_chat.id
    if not memory.has_profile() and not onboarding.active(context.chat_data):
        await onboarding.start(context.bot, chat_id, context.chat_data)
        return
    await context.bot.send_message(chat_id=chat_id, text="Hello! I'm an AI-powered chatbot. Type /help to see available commands")


@authorized
async def chat(update, context):
    chat_id = update.effective_chat.id
    user_message = message_text(update, context)
    if not user_message:
        await context.bot.send_message(chat_id=chat_id, text="Send me a message to chat.")
        return

    data = context.chat_data
    if onboarding.active(data):
        await onboarding_answer(context, chat_id, user_message)
        return
    if not memory.has_profile():
        await onboarding.start(context.bot, chat_id, data)
        return

    model = data.get("model", MODEL)
    async with typing(context.bot, chat_id):
        try:
            await memory.compact(data, lambda messages: complete(context, chat_id, model, messages))
            hints = [f"You are running on the local model {model}.", memory.MEMORY_HINT]
            if WEB_SEARCH:
                hints.append(tools.PROMPT_HINT)
            messages = [
                {"role": "system", "content": memory.system_prompt(data, hints)},
                *data.get("history", []),
                {"role": "user", "content": user_message},
            ]
            trace = []
            ai_response = await complete(context, chat_id, model, messages, use_tools=WEB_SEARCH, data=data,
                                         trace=trace, question=user_message)
        except Exception as e:
            await send_error(context, chat_id, e)
            return

    # Keep the tool calls in the history: a history of answers without them teaches
    # small models to answer "searched" questions from memory
    data.setdefault("history", []).extend([
        {"role": "user", "content": user_message},
        *trace,
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
async def onboarding_button(update, context):
    query = update.callback_query
    _, step, choice = query.data.split(":")
    if not onboarding.active(context.chat_data) or int(step) != context.chat_data["onboarding"]["step"]:
        await query.answer("This question is already answered")
        return
    await query.answer()
    with contextlib.suppress(BadRequest):
        await query.edit_message_reply_markup(reply_markup=None)
    await onboarding_answer(context, update.effective_chat.id, onboarding.option(context.chat_data, int(step), choice))


@authorized
async def setup(update, context):
    await onboarding.start(context.bot, update.effective_chat.id, context.chat_data)


@authorized
async def profile(update, context):
    chat_id = update.effective_chat.id
    if context.args:
        key = onboarding.field_key(context.args[0])
        value = " ".join(context.args[1:]).strip()
        if not key or not value:
            await context.bot.send_message(chat_id=chat_id, text=onboarding.PROFILE_HELP)
            return
        answers = onboarding.load()
        answers[key] = value
        if key == "city":
            answers["timezone"] = await resolve_timezone(context, context.chat_data.get("model", MODEL), value)
        onboarding.save(answers)
    text = memory.user_profile() or "还没有资料。No profile yet."
    await context.bot.send_message(chat_id=chat_id, text=f"{text}\n\n{onboarding.PROFILE_HELP}")


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
             "/profile – what I know about you (/setup to change it)\n"
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
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("setup", setup))
    application.add_handler(CallbackQueryHandler(model_button, pattern=r"^model:\d+$"))
    application.add_handler(CallbackQueryHandler(onboarding_button, pattern=r"^ob:\d+:(\d+|skip)$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    application.bot_data["client"] = client
