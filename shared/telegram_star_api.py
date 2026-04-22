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
