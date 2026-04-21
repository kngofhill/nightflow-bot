"""Call Telegram Bot API createInvoiceLink (used by Flask mini-app)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def create_invoice_link(
    bot_token: str,
    *,
    title: str,
    description: str,
    payload: str,
    currency: str,
    prices: list,
    provider_token: str = "",
    subscription_period: Optional[int] = None,
) -> Optional[str]:
    """Returns HTTPS invoice URL or None on failure."""
    body: Dict[str, Any] = {
        "title": title,
        "description": description,
        "payload": payload,
        "provider_token": provider_token,
        "currency": currency,
        "prices": prices,
    }
    if subscription_period is not None:
        body["subscription_period"] = subscription_period

    data = json.dumps(body).encode("utf-8")
    url = f"https://api.telegram.org/bot{bot_token}/createInvoiceLink"
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8")
        except Exception:
            err_body = str(e)
        logger.error("createInvoiceLink HTTP error: %s %s", e.code, err_body)
        return None
    except Exception as e:
        logger.error("createInvoiceLink failed: %s", e)
        return None

    if not raw.get("ok"):
        logger.error("createInvoiceLink API error: %s", raw)
        return None
    return raw.get("result")
