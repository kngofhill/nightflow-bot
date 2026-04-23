"""Bot copy for /start, language pick, and welcome-back. Kept short for night-shift users."""

# First message: one line
PICK_LANGUAGE = "🌙 Nightflow — pick language 👇"

# /lang /language /setlang
LANG_TITLE = "🌙 Language · EN / RU / UZ 👇"


def msg_language_saved(code: str) -> str:
    if code == "ru":
        return "✅ RU — обновите мини‑приложение."
    if code == "uz":
        return "✅ UZ — ilvani yangilang."
    return "✅ EN — refresh the mini app."


def welcome_back(name: str, code: str) -> str:
    n = name or "there"
    if code == "ru":
        return f"👋 {n}, снова здесь. Меню ⬇️ · кнопки ниже · /lang"
    if code == "uz":
        return f"👋 {n}, yana xush. Menyu ⬇️ · tugmalar · /lang"
    return f"👋 {n}, back. Menu ⬇️ · buttons below · /lang /language /setlang"


# After first language pick (HTML) — minimal
INTRO: dict[str, str] = {
    "en": (
        "✨ <b>App</b> (menu ⬇️): <b>Home</b> · <b>Plan</b> · <b>Week</b> · <b>Ideas</b> · <b>Settings</b> — Pro features need Pro.\n"
        "<b>Bot</b>: buttons below or /subscribe /cancel /pause /resume · <b>Lang</b>: /lang /language /setlang"
    ),
    "ru": (
        "✨ <b>Приложение</b>: <b>Главная</b> · <b>План</b> · <b>Неделя</b> · <b>Идеи</b> · <b>Настройки</b> — Pro отдельно.\n"
        "<b>Бот</b>: кнопки ниже или /subscribe /cancel /pause /resume · язык: /lang /language /setlang"
    ),
    "uz": (
        "✨ <b>Ilova</b>: <b>Bosh</b> · <b>Reja</b> · <b>Hafta</b> · <b>Fikr</b> · <b>Sozlama</b> — Pro alohida.\n"
        "<b>Bot</b>: tugmalar yoki /subscribe /cancel /pause /resume · til: /lang /language /setlang"
    ),
}
