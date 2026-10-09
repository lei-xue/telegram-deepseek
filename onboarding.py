"""First-chat questions that fill in user.md. Scripted, so small models cannot derail it."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import memory

SKIP = "跳过 / Skip"
# (key, label in user.md, question, button options)
STEPS = [
    ("name", "Name", "怎么称呼你？\nWhat should I call you?", []),
    ("city", "City", "你在哪个城市？我会按你那边的时间聊天。\nWhich city are you in? I'll keep track of your local time.", []),
    ("language", "Language", "想用什么语言聊？\nWhich language should we chat in?", ["中文", "English", "都行 / Either"]),
    ("about", "About", "简单说说你做什么工作、平时喜欢什么？\nWhat do you do, and what do you enjoy?", []),
    ("style", "Preferred style", "希望我是什么风格？\nHow would you like me to talk?", ["温柔 / Gentle", "活泼 / Playful", "简洁直接 / Brief and direct"]),
    ("avoid", "Avoid", "有没有不想聊的话题，或者需要我注意的事？\nAnything I should avoid or keep in mind?", []),
]
FIELDS = [("name", "Name"), ("city", "City"), ("timezone", "Timezone")] + [(k, label) for k, label, _, _ in STEPS[2:]]

INTRO = ("你好！开始之前想先认识你一下，一共 6 个问题，每个都可以跳过。\n"
         "Hi! Six quick questions so I can get to know you. Skip any of them.")
DONE = ("好啦，记住了 😊 随时可以用 /profile 查看、/setup 重新填写。现在想聊点什么？\n"
        "All set! Use /profile to view this or /setup to redo it. What's on your mind?")


def active(data):
    return "onboarding" in data


def keyboard(step):
    rows = [[InlineKeyboardButton(option, callback_data=f"ob:{step}:{i}")] for i, option in enumerate(STEPS[step][3])]
    rows.append([InlineKeyboardButton(SKIP, callback_data=f"ob:{step}:skip")])
    return InlineKeyboardMarkup(rows)


async def ask(bot, chat_id, step):
    await bot.send_message(chat_id=chat_id, text=f"({step + 1}/{len(STEPS)}) {STEPS[step][2]}", reply_markup=keyboard(step))


async def start(bot, chat_id, data):
    data["onboarding"] = {"step": 0, "answers": {}}
    await bot.send_message(chat_id=chat_id, text=INTRO)
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
    save(answers)
    await bot.send_message(chat_id=chat_id, text=DONE)


def save(answers):
    lines = ["# About the user", ""] + [f"- {label}: {answers[key]}" for key, label in FIELDS if answers.get(key)]
    with open(memory.USER_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
