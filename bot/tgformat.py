import html
import re

# Telegram's limit is 4096 characters; leave room for the HTML tags added by to_html
CHUNK_LIMIT = 3500

CODE_BLOCK = re.compile(r"```[^\n`]*\n?(.*?)```", re.S)
INLINE_CODE = re.compile(r"`([^`\n]+)`")
LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
SLOT = re.compile(r"\x00(\d+)\x00")


def split_message(text, limit=CHUNK_LIMIT):
    """Split text into chunks of at most `limit` characters, preferring line breaks."""
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


def to_html(text):
    """Convert the Markdown that models usually write into Telegram's HTML subset."""
    slots = []

    def stash(fragment):
        slots.append(fragment)
        return f"\x00{len(slots) - 1}\x00"

    # Code and links are converted first and protected from the inline rules below
    text = CODE_BLOCK.sub(lambda m: stash(f"<pre>{html.escape(m.group(1).rstrip())}</pre>"), text)
    text = INLINE_CODE.sub(lambda m: stash(f"<code>{html.escape(m.group(1))}</code>"), text)
    text = LINK.sub(lambda m: stash(f'<a href="{html.escape(m.group(2))}">{html.escape(m.group(1))}</a>'), text)

    text = html.escape(text, quote=False)
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.M)
    text = re.sub(r"^(\s*)[-*]\s+", r"\1• ", text, flags=re.M)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
    text = re.sub(r"(?<![*\w])\*(?![\s*])(.+?)(?<![\s*])\*(?![*\w])", r"<i>\1</i>", text)

    return SLOT.sub(lambda m: slots[int(m.group(1))], text)
