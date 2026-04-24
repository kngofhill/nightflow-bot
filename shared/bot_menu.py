"""Bottom reply keyboard (2×2 grid) + shared WebApp URL.

Labels must stay in sync with ``on_reply_menu_button`` in ``bot/main.py``.
"""

import os
import re

from telegram import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from telegram.ext import filters


def webapp_url() -> str:
    return os.getenv("WEBAPP_URL", "https://nightflow-bot-production.up.railway.app").strip()


# Reply keyboard — tapping sends this exact text (except web_app buttons, which open the Mini App).
REPLY_BTN_MINI_APP = "📱 Mini App"
REPLY_BTN_SUBSCRIBE = "⭐ Subscribe"
REPLY_BTN_CANCEL = "⛔ Cancel"
REPLY_BTN_REFUND = "💸 Refund"

REPLY_MENU_TEXT_BUTTONS = (
    REPLY_BTN_SUBSCRIBE,
    REPLY_BTN_CANCEL,
    REPLY_BTN_REFUND,
)


def reply_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Large bottom keys (resize + persistent), similar to common bot menus."""
    wu = webapp_url()
    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton(REPLY_BTN_MINI_APP, web_app=WebAppInfo(url=wu)),
                KeyboardButton(REPLY_BTN_SUBSCRIBE),
            ],
            [
                KeyboardButton(REPLY_BTN_CANCEL),
                KeyboardButton(REPLY_BTN_REFUND),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Message",
    )


def reply_menu_text_filter():
    """PTB filter: only messages that match a non-web menu label."""
    pattern = "^(" + "|".join(re.escape(t) for t in REPLY_MENU_TEXT_BUTTONS) + ")$"
    return filters.TEXT & ~filters.COMMAND & filters.Regex(pattern)
