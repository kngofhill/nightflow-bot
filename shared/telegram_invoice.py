"""Call Telegram Bot API createInvoiceLink (used by Flask mini-app)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _post_create_invoice_link(bot_token: str, body: Dict[str, Any]) -> Optional[str]:
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
        logger.warning("createInvoiceLink API error: %s", raw)
        return None
    return raw.get("result")


def create_invoice_link(
    bot_token: str,
    *,
    title: str,
    description: str,
    payload: str,
    currency: str,
    prices: list,
    provider_token: Optional[str] = None,
    subscription_period: Optional[int] = None,
) -> Optional[str]:
    """Returns HTTPS invoice URL or None on failure.

    For XTR, omit ``provider_token`` from the request when unset/empty (some clients reject "").
    If ``subscription_period`` is set but Telegram rejects it, retries as a one-time invoice.
    """
    body: Dict[str, Any] = {
        "title": title,
        "description": description,
        "payload": payload,
        "currency": currency,
        "prices": prices,
    }
    if provider_token:
        body["provider_token"] = provider_token

    if subscription_period is not None:
        with_sub = {**body, "subscription_period": subscription_period}
        result = _post_create_invoice_link(bot_token, with_sub)
        if result:
            return result
        logger.warning("createInvoiceLink: recurring invoice rejected; retrying one-time XTR")

    return _post_create_invoice_link(bot_token, body)
