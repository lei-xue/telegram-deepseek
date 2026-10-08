import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PERSONA_FILE = os.path.join(BASE_DIR, os.getenv("PERSONA_FILE", "persona.md"))
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "You are a helpful assistant")
TIMEZONE = os.getenv("TIMEZONE", "America/Los_Angeles")
# Context window of the model. Half of it is kept for recent messages, the rest for the
# system prompt, memory summary, web results and the reply.
CONTEXT_TOKENS = int(os.getenv("CONTEXT_TOKENS", "16384"))
HISTORY_BUDGET = CONTEXT_TOKENS // 2

SUMMARY_PROMPT = (
    "You maintain the long-term memory of a personal chat assistant. Merge the existing memory and the "
    "conversation below into one updated memory. Keep what matters for future chats: facts about the user, "
    "preferences, mood, plans, ongoing topics, important events with dates, and promises made. "
    "Drop small talk. Write concise bullet points, at most 300 words, in the language the user uses. "
    "Output only the memory."
)


def estimate_tokens(text):
    # Rough and slightly pessimistic: ~1 token per CJK character, ~4 characters per token otherwise
    ascii_chars = sum(c.isascii() for c in text)
    return (len(text) - ascii_chars) + ascii_chars // 4 + 4


def history_tokens(history):
    return sum(estimate_tokens(m["content"]) for m in history)


def persona():
    # Read on every message so edits to the persona file apply without a restart
    try:
        with open(PERSONA_FILE, encoding="utf-8") as f:
            return f.read().strip() or SYSTEM_PROMPT
    except FileNotFoundError:
        return SYSTEM_PROMPT


def system_prompt(data, extra=None):
    tz = ZoneInfo(TIMEZONE)
    parts = [persona(), f"Current time: {datetime.now(tz):%Y-%m-%d %A %H:%M} ({TIMEZONE})."]
    last = data.get("last_ts")
    if last and time.time() - last > 3600:
        parts.append(f"The previous message in this conversation was sent at {datetime.fromtimestamp(last, tz):%Y-%m-%d %A %H:%M}.")
    if extra:
        parts.append(extra)
    if data.get("summary"):
        parts.append("Memory of earlier conversations:\n" + data["summary"])
    return "\n\n".join(parts)


async def compact(data, summarize):
    """Fold the oldest messages into the memory summary once history exceeds its budget."""
    history = data.get("history", [])
    if history_tokens(history) <= HISTORY_BUDGET:
        return

    # Keep the newest messages within half the budget, starting at a user message
    keep, used = len(history), 0
    while keep > 0 and used + estimate_tokens(history[keep - 1]["content"]) <= HISTORY_BUDGET // 2:
        keep -= 1
        used += estimate_tokens(history[keep]["content"])
    while keep < len(history) and history[keep]["role"] != "user":
        keep += 1

    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in history[:keep])
    messages = [
        {"role": "system", "content": SUMMARY_PROMPT},
        {"role": "user", "content": f"Existing memory:\n{data.get('summary') or '(none)'}\n\nConversation:\n{transcript}"},
    ]
    try:
        data["summary"] = await summarize(messages)
    except Exception as e:
        print(f"Memory summary failed, dropping {keep} old messages: {e!r}", flush=True)
    data["history"] = history[keep:]
