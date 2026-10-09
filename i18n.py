"""Bot texts and reply patterns. English is built in; an optional locale.json adds another language.

locale.json (git-ignored) may override any text below and add regex alternatives to any pattern,
so the checks in handler.py also recognise replies written in that language. See README.
"""
import json
import os
import re

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCALE_FILE = os.path.join(BASE_DIR, os.getenv("LOCALE_FILE", "locale.json"))

TEXTS = {
    "intro": "Hi! Three quick questions so I can get to know you. Skip any of them.",
    "done": "All set! I'll get to know you as we chat. Send /profile to view or add details. What's on your mind?",
    "skip": "Skip",
    "question_name": "What should I call you?",
    "question_city": "Which city are you in? I'll keep track of your local time.",
    "question_style": "How would you like me to talk?",
    "style_options": ["Gentle", "Playful", "Brief and direct"],
    "profile_help": ("Edit one item: /profile <field> <value>\n"
                     "Fields: name, city, timezone, language, about, style, avoid\n"
                     "Example: /profile about cats and hiking\n"
                     "/setup – answer the first questions again"),
    "no_profile": "No profile yet.",
    "memory_hint": (
        "When the user shares something worth remembering long-term (personal details, preferences, plans, "
        "important events, or asks you to remember something), you must call the remember tool with a short fact "
        "before replying. Only saying \"noted\" without calling the tool does nothing and you will forget it. "
        "Do not save small talk or anything already in memory. Learn details missing from the user profile "
        "(work, interests, topics to avoid) naturally over time without interrogating, and save them with remember too."
    ),
    "name_hint": ("The user's name is {name}; it is not your name. When the user asks what their name is "
                  "or who they are, answer that they are {name}."),
    # Extra names /profile accepts for each field, e.g. {"about": ["hobbies"]}
    "field_aliases": {},
}

PATTERNS = {
    # A reply that says it searched (or will) without calling web_search
    "claims_search": r"let me (check|search|look)|I('ll| will) (check|search|look)|according to (the )?(search|latest)|search results|🔍",
    # A reply that says it saved something without calling remember
    "claims_remember": r"\bnoted\b|I('ll| will) remember|I've (saved|noted)|I'll keep that in mind",
    # A refusal at the start of a reply
    "refusal": r"I can(not|'t|'m not able to) (help|provide|discuss|answer|share)|I('m| am) (not able|unable) to (help|provide|discuss|answer)|sensitive (topic|subject)",
    # The user's message is a question (only factual questions are looked up after a refusal)
    "question": r"\?|\b(how|what|why|who|which|when|where|is it|are there|does|do)\b",
    # The user's message asks for writing or role play, which is never looked up
    "writing_request": r"\b(write|story|novel|poem|roleplay|role-play|pretend|scene)\b",
    # A sentence that is a question or an offer ("Want me to look it up?") rather than a claim
    "offer": r"\?",
    # Characters that end a sentence
    "sentence_end": r".!?",
}


def _load():
    try:
        with open(LOCALE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


_locale = _load()
T = {**TEXTS, **_locale.get("texts", {})}
_extra = _locale.get("patterns", {})


def pattern(name):
    """Built-in pattern plus the locale's alternatives, compiled case-insensitively."""
    if name == "sentence_end":
        return re.escape(PATTERNS[name] + _extra.get(name, ""))
    extra = _extra.get(name)
    return re.compile(PATTERNS[name] + (f"|{extra}" if extra else ""), re.I)
