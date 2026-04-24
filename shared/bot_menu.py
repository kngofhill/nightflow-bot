"""Inline keyboard: quick actions (subscribe, pause, resume, language, web app)."""

import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo


def webapp_url() -> str:
    return os.getenv("WEBAPP_URL", "https://nightflow-bot-production.up.railway.app").strip()


def command_menu_markup() -> InlineKeyboardMarkup:
    wu = webapp_url()
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⭐ Subscribe", callback_data="menu:sub"),
                InlineKeyboardButton("⏸", callback_data="menu:pause"),
                InlineKeyboardButton("▶️", callback_data="menu:resume"),
            ],
            [
                InlineKeyboardButton("⛔ Cancel", callback_data="menu:cancel"),
                InlineKeyboardButton("💸 Refund", callback_data="menu:refund"),
            ],
            [
                InlineKeyboardButton("🌐 Lang", callback_data="menu:lang"),
                # url= would open a browser; web_app= opens the Mini App inside Telegram.
                InlineKeyboardButton("📱 Open app", web_app=WebAppInfo(url=wu)),
            ],
        ]
    )
