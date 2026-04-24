"""Bot copy for /start and welcome. English only."""

# Reply when user uses legacy /lang or menu (English only; no switching).
LANG_ONLY = "🌙 Nightflow is <b>English only</b>. Open the mini app from the ⋮ menu or the 📱 key below."


def msg_language_saved(_code: str) -> str:
    return "✅ Language: English. Refresh the mini app if it was open."


def welcome_back(name: str, _code: str) -> str:
    n = name or "there"
    return f"👋 {n}, back. Use the keys below · /start"


# First /start (HTML) — minimal
INTRO: str = (
    "✨ <b>App</b> (⋮ menu): <b>Home</b> · <b>Plan</b> · <b>Week</b> · <b>Ideas</b> · <b>Settings</b> — Pro features need Pro.\n"
    "<b>Bot</b>: use the <b>large keys below</b>, or /subscribe /cancel /pause /resume."
)
