"""Bottom reply keyboard + profile / commands copy for Telegram."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from telegram import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from telegram.ext import filters

from shared.subscription import (
    subscription_meta_for_user,
    trial_period_end,
    _parse_dt,
)
from shared.time_utils import DEFAULT_TIMEZONE

# Reply keyboard — labels must match handlers in ``bot/main.py``.
REPLY_BTN_PROFILE = "👤 Profile"
REPLY_BTN_MINI_APP = "📱 Mini App"
REPLY_BTN_SUPPORT = "💬 Support"
REPLY_BTN_COMMANDS = "📋 Commands"

SUPPORT_TELEGRAM_URL = "https://t.me/nightflowadmin"

REPLY_MENU_TEXT_BUTTONS = (
    REPLY_BTN_PROFILE,
    REPLY_BTN_COMMANDS,
)


BOT_COMMANDS_HELP = """\
<b>Bot commands</b>

/start — Welcome & menu keyboard
/profile — Same as the Profile button (account summary)

<b>Billing (Stars)</b>
/subscribe — Pay for Nightflow Pro (30 days)
/cancel — Turn off auto-renewal (you keep Pro until the end date)
/refund — Refund within 3 days of purchase (limits apply)

<b>Reminders</b>
/pause — Stop shift reminder messages
/resume — Turn reminders back on

<b>Other</b>
/status — Debug timestamps (testing)
/lang — Language info (English only)

Tip: schedules and check-ins live in the <b>Mini App</b> (📱 button or menu).

<b>Support</b> — tap 💬 Support or message @nightflowadmin
"""


def webapp_url() -> str:
    return os.getenv("WEBAPP_URL", "https://nightflow-bot-production.up.railway.app").strip()


def _fmt_local(dt: Optional[datetime], tz_name: str) -> str:
    if not dt:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        loc = dt.astimezone(ZoneInfo(tz_name))
    except Exception:
        loc = dt.astimezone(timezone.utc)
    return loc.strftime("%b %d, %Y %H:%M %Z").strip()


def format_telegram_profile(user_row: Optional[Dict[str, Any]]) -> str:
    """Short account summary for the Profile button (plain text, no HTML)."""
    if not user_row:
        return (
            "No Nightflow account yet.\n"
            "Send /start, then open the mini app once to finish setup."
        )

    tz = (user_row.get("timezone") or DEFAULT_TIMEZONE or "UTC").strip() or "UTC"
    now_utc = datetime.now(timezone.utc)
    meta = subscription_meta_for_user(user_row, now_utc)
    paid = bool(meta.get("active_paid_pro"))
    has_pro = bool(meta.get("has_pro_entitlement"))

    lines = ["<b>Your Nightflow profile</b>", ""]

    st = (user_row.get("shift_type") or "").strip() or "not set"
    if st == "not set":
        st_disp = "Not set yet — choose in the mini app (Settings)."
    else:
        st_disp = st.replace("_", " ").title()

    lines.append(f"<b>Schedule type</b>: {st_disp}")
    lines.append(f"<b>Timezone</b>: {tz}")

    rem = user_row.get("notification_enabled")
    if rem is None:
        rem_txt = "On (default)"
    else:
        rem_txt = "On" if rem else "Off"
    lines.append(f"<b>Shift reminders</b>: {rem_txt}")

    lines.append("")
    lines.append("<b>Subscription</b>")

    pe = _parse_dt(user_row.get("pro_expires_at"))
    ts = _parse_dt(user_row.get("trial_started_at"))

    if paid and pe and now_utc < pe:
        lines.append(f"• Paid <b>Nightflow Pro</b> — access until {_fmt_local(pe, tz)}.")
        if meta.get("subscription_cancelled"):
            lines.append("• Auto-renewal: <b>off</b> (no further Star charges for this plan).")
        elif meta.get("subscription_active") is False:
            lines.append("• Billing: inactive (e.g. after refund).")
        else:
            lines.append("• Auto-renewal: <b>on</b> until you /cancel.")
    elif has_pro and ts:
        te = trial_period_end(ts)
        if now_utc < te:
            lines.append(f"• <b>Free trial</b> — ends {_fmt_local(te, tz)}.")
        else:
            lines.append("• Trial has ended. Use /subscribe for Pro.")
    elif pe and now_utc >= pe:
        lines.append("• Paid period ended. Use /subscribe to renew.")
    else:
        lines.append("• No active Pro or trial. Open the app or use /subscribe.")

    if paid and user_row.get("last_pro_payment_at") and meta.get("refund_eligible_until"):
        rd = _parse_dt(meta["refund_eligible_until"])
        if rd and now_utc <= rd:
            lines.append(f"• Refund window (if eligible): until {_fmt_local(rd, tz)}.")

    lines.append("")
    lines.append("Change schedule & prefs in the mini app · Billing: /subscribe /cancel /refund")

    return "\n".join(lines)


def reply_main_menu_keyboard() -> ReplyKeyboardMarkup:
    wu = webapp_url()
    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton(REPLY_BTN_PROFILE),
                KeyboardButton(REPLY_BTN_MINI_APP, web_app=WebAppInfo(url=wu)),
            ],
            [
                KeyboardButton(REPLY_BTN_SUPPORT, url=SUPPORT_TELEGRAM_URL),
                KeyboardButton(REPLY_BTN_COMMANDS),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Message",
    )


def reply_menu_text_filter():
    pattern = "^(" + "|".join(re.escape(t) for t in REPLY_MENU_TEXT_BUTTONS) + ")$"
    return filters.TEXT & ~filters.COMMAND & filters.Regex(pattern)
