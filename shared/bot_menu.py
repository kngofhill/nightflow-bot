"""Inline keyboard: quick actions (subscribe, pause, resume, language, web app)."""

import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def webapp_url() -> str:
    return os.getenv("WEBAPP_URL", "https://nightflow-bot-production.up.railway.app").strip()


def command_menu_markup() -> InlineKeyboardMarkup:
    wu = webapp_url()
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⭐ Pro", callback_data="menu:sub"),
                InlineKeyboardButton("⏸", callback_data="menu:pause"),
                InlineKeyboardButton("▶️", callback_data="menu:resume"),
            ],
            [
                InlineKeyboardButton("🌐 Lang", callback_data="menu:lang"),
                InlineKeyboardButton("📱 App", url=wu),
            ],
        ]
    )
