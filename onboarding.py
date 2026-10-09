"""First-chat questions that fill in user.md. Scripted, so small models cannot derail it.

Only the basics are asked up front; the rest can be added later with /profile <field> <value>.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import memory

SKIP = "跳过 / Skip"
# (key, label in user.md, question, button options)
STEPS = [
    ("name", "Name", "怎么称呼你？\nWhat should I call you?", []),
    ("city", "City", "你在哪个城市？我会按你那边的时间聊天。\nWhich city are you in? I'll keep track of your local time.", []),
    ("style", "Preferred style", "希望我是什么风格？\nHow would you like me to talk?", ["温柔 / Gentle", "活泼 / Playful", "简洁直接 / Brief and direct"]),
]
# Every field user.md can hold, with the names /profile accepts for it
FIELDS = [
    ("name", "Name", ("name", "称呼", "名字")),
    ("city", "City", ("city", "城市")),
    ("timezone", "Timezone", ("timezone", "时区")),
    ("language", "Language", ("language", "语言")),
    ("about", "About", ("about", "关于", "工作", "爱好")),
    ("style", "Preferred style", ("style", "风格")),
    ("avoid", "Avoid", ("avoid", "避开", "不聊")),
]

INTRO = ("你好！先简单认识一下，就 3 个问题，都可以跳过。\n"
         "Hi! Three quick questions so I can get to know you. Skip any of them.")
DONE = ("好啦 😊 其他的我们慢慢聊、慢慢了解。想补充资料可以发 /profile 查看和修改。现在想聊点什么？\n"
        "All set! I'll get to know you as we chat. Send /profile to view or add details. What's on your mind?")
PROFILE_HELP = ("修改或补充一项：/profile <字段> <内容>\n"
                "字段：称呼、城市、时区、语言、爱好、风格、不聊\n"
                "例如：/profile 爱好 猫和徒步\n"
                "Edit one item: /profile <field> <value>, e.g. /profile about cats and hiking\n"
                "/setup – answer the first questions again")


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
    # Re-running /setup keeps details added later (about, avoid, ...) unless re-answered
    save({**load(), **answers})
    await bot.send_message(chat_id=chat_id, text=DONE)


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
