"""Bot copy for /start, language pick, and welcome-back. Kept short for night-shift users."""

# When language not set yet — trilingual, very short
PICK_LANGUAGE = "🌙 Nightflow\nEN · choose language / RU / UZ — tap below"

# After /lang — same as start without language
LANG_TITLE = "🌙 Nightflow\nChoose a language / Выберите язык / Tilni tanlang"

# Short confirmation after changing language (when it was already set)
def msg_language_saved(code: str) -> str:
    if code == "ru":
        return "✅ Язык: русский. Мини‑приложение откроется на выбранном языке."
    if code == "uz":
        return "✅ Til: oʻzbekcha. Ilova tanlangan tilda ochiladi."
    return "✅ Language: English. The mini app will use this from now on."


def welcome_back(name: str, code: str) -> str:
    n = name or "there"
    if code == "ru":
        return (
            f"👋 Снова привет, {n}.\n"
            f"Мини‑приложение — кнопка меню ⬇️\n"
            f"Команды: /subscribe · /cancel · /pause · /resume · /lang — смена языка"
        )
    if code == "uz":
        return (
            f"👋 Yana salom, {n}.\n"
            f"Ilova — menyu tugmasi ⬇️\n"
            f"Buyruqlar: /subscribe · /cancel · /pause · /resume · /lang — til"
        )
    return (
        f"👋 Welcome back, {n}.\n"
        f"Open the app with the menu button ⬇️\n"
        f"Commands: /subscribe · /cancel · /pause · /resume · /lang — change language"
    )


# After first language pick (HTML)
INTRO: dict[str, str] = {
    "en": (
        "✨ <b>What you get</b>\n\n"
        "<b>App (menu ⬇️)</b>\n"
        "• <b>Home</b> — today, next alert, end‑of‑shift check‑in\n"
        "• <b>Schedule</b> — your plan (Pro)\n"
        "• <b>Week</b> — report (Pro)\n"
        "• <b>Ideas</b> — small tweaks (Pro)\n"
        "• <b>Settings</b> — time zone, alerts, Pro\n\n"
        "<b>Bot</b> — /subscribe (Pro) · /cancel (stop renew) · /pause · /resume\n\n"
        "Short trial, then Pro or Free. Only fill what you can — the rest is optional."
    ),
    "ru": (
        "✨ <b>Что внутри</b>\n\n"
        "<b>Приложение (меню ⬇️)</b>\n"
        "• <b>Главная</b> — день, напоминание, чек‑ин после смены\n"
        "• <b>Расписание</b> — план (Pro)\n"
        "• <b>Неделя</b> — отчёт (Pro)\n"
        "• <b>Идеи</b> — подсказки (Pro)\n"
        "• <b>Настройки</b> — пояс, уведомления, Pro\n\n"
        "<b>Бот</b> — /subscribe (Pro) · /cancel · /pause · /resume\n\n"
        "Короткий триал, потом Pro или бесплатно. Устали — пропустите лишнее."
    ),
    "uz": (
        "✨ <b>Nimalar bor</b>\n\n"
        "<b>Ilova (menyu ⬇️)</b>\n"
        "• <b>Bosh</b> — kun, eslatma, smena cheki\n"
        "• <b>Jadval</b> — reja (Pro)\n"
        "• <b>Hafta</b> — hisobot (Pro)\n"
        "• <b>G‘oyalar</b> — tavsiya (Pro)\n"
        "• <b>Sozlamalar</b> — zona, bildirishnoma, Pro\n\n"
        "<b>Bot</b> — /subscribe (Pro) · /cancel · /pause · /resume\n\n"
        "Qisqa sinov, keyin Pro yoki bepul. Charchasangiz — o‘tkazib yuboring."
    ),
}
