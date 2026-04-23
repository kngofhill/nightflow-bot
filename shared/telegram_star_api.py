"""Direct Telegram Bot API calls for Stars (Flask has no async Bot)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def edit_user_star_subscription(
    bot_token: str, *, user_id: int, telegram_payment_charge_id: str, is_canceled: bool
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    https://core.telegram.org/bots/api#edituserstarsubscription
    Returns (ok, result_or_error_dict).
    """
    body: Dict[str, Any] = {
        "user_id": int(user_id),
        "telegram_payment_charge_id": str(telegram_payment_charge_id),
        "is_canceled": bool(is_canceled),
    }
    data = json.dumps(body).encode("utf-8")
    url = f"https://api.telegram.org/bot{bot_token}/editUserStarSubscription"
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8")
            raw = json.loads(err_body)
        except Exception:
            raw = {"ok": False, "description": str(e)}
        logger.warning("editUserStarSubscription HTTP %s: %s", e.code, raw)
        return False, raw
    except Exception as e:
        logger.error("editUserStarSubscription failed: %s", e)
        return False, {"ok": False, "description": str(e)}

    if not raw.get("ok"):
        return False, raw
    return True, raw


def is_telegram_charge_invalid_error(exc_or_msg: object) -> bool:
    """True when editUserStarSubscription / Stars APIs reject the charge (e.g. one-time payment)."""
    s = str(exc_or_msg).upper()
    return "CHARGE_ID_INVALID" in s or (
        "CHARGE_ID" in s and "INVALID" in s
    )


def format_telegram_cancel_subscription_error(raw_or_exc: object) -> str:
    """Human-readable explanation for failed editUserStarSubscription (for bot + API)."""
    if isinstance(raw_or_exc, Exception):
        s = str(raw_or_exc)
        name = type(raw_or_exc).__name__
    else:
        s = str(raw_or_exc)
        name = "Telegram"
    low = s.lower()
    parts = [
        f"Telegram did not accept the cancellation ({name}).",
        f"Raw: {s[:800]}",
        "",
        "Common causes:",
    ]
    if "charge" in low and ("invalid" in low or "not found" in low):
        parts.append("• The charge id is wrong, expired, or was for a one-time payment (not a subscription).")
    if "already" in low and "cancel" in low:
        parts.append("• The subscription is already cancelled in Telegram.")
    if "forbidden" in low or "403" in s:
        parts.append("• The bot may not be allowed to change this user’s Star subscription.")
    if "bad request" in low or "400" in s:
        parts.append("• Request rejected by Telegram — check BotFather: Stars + payments, and a current Bot API build.")
    parts.append("You can try /cancel in this bot chat again in a few minutes, or message support with the error above.")
    return "\n".join(parts)
