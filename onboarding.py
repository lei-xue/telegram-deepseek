"""First-chat questions that fill in user.md. Scripted, so small models cannot derail it.

Only the basics are asked up front; the rest can be added later with /profile <field> <value>.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import memory
from i18n import T

# (key, label in user.md, question text key, button options)
STEPS = [
    ("name", "Name", "question_name", []),
    ("city", "City", "question_city", []),
    ("style", "Preferred style", "question_style", T["style_options"]),
]
# Every field user.md can hold, with the names /profile accepts for it (plus the locale's aliases)
FIELDS = [
    (key, label, (key, *aliases, *T["field_aliases"].get(key, [])))
    for key, label, aliases in [
        ("name", "Name", ()),
        ("city", "City", ()),
        ("timezone", "Timezone", ("tz",)),
        ("language", "Language", ()),
        ("about", "About", ("hobbies", "work")),
        ("style", "Preferred style", ()),
        ("avoid", "Avoid", ()),
    ]
]


def active(data):
    return "onboarding" in data


def keyboard(step):
    rows = [[InlineKeyboardButton(option, callback_data=f"ob:{step}:{i}")] for i, option in enumerate(STEPS[step][3])]
    rows.append([InlineKeyboardButton(T["skip"], callback_data=f"ob:{step}:skip")])
    return InlineKeyboardMarkup(rows)


async def ask(bot, chat_id, step):
    await bot.send_message(chat_id=chat_id, text=f"({step + 1}/{len(STEPS)}) {T[STEPS[step][2]]}", reply_markup=keyboard(step))


async def start(bot, chat_id, data):
    data["onboarding"] = {"step": 0, "answers": {}}
    await bot.send_message(chat_id=chat_id, text=T["intro"])
    await ask(bot, chat_id, 0)


def option(data, step, choice):
    """Value of a tapped button, or None for Skip or a button from an earlier question."""
    if step != data["onboarding"]["step"] or choice == "skip":
        return None
    options = STEPS[step][3]
    index = int(choice)
    return options[index] if index < len(options) else None


async def answer(bot, chat_id, data, value, resolve_timezone):
    """Record the answer to the current question (None = skipped) and ask the next one."""
    state = data["onboarding"]
    if value and value.strip():
        state["answers"][STEPS[state["step"]][0]] = value.strip()
    state["step"] += 1
    if state["step"] < len(STEPS):
        await ask(bot, chat_id, state["step"])
        return

    answers = data.pop("onboarding")["answers"]
    if answers.get("city"):
        answers["timezone"] = await resolve_timezone(answers["city"])
    # Re-running /setup keeps details added later (about, avoid, ...) unless re-answered
    save({**load(), **answers})
    await bot.send_message(chat_id=chat_id, text=T["done"])


def load():
    """Fields of user.md as {key: value}."""
    labels = {label: key for key, label, _ in FIELDS}
    answers = {}
    for line in memory.user_profile().splitlines():
        label, sep, value = line.removeprefix("- ").partition(": ")
        if line.startswith("- ") and sep and label in labels:
            answers[labels[label]] = value.strip()
    return answers


def field_key(name):
    return next((key for key, _, aliases in FIELDS if name.lower() in aliases), None)


def save(answers):
    lines = ["# About the user", ""] + [f"- {label}: {answers[key]}" for key, label, _ in FIELDS if answers.get(key)]
    with open(memory.USER_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
