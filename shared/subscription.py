"""Pro trial / Telegram Stars subscription entitlement."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

TRIAL_DAYS = 14
REFUND_WINDOW_DAYS = 3
SUBSCRIPTION_PERIOD_SECONDS = 2592000  # Telegram Stars recurring: 30 days
PRO_PRICE_STARS = 50
INVOICE_PAYLOAD_NIGHTFLOW_PRO = "nightflow_pro_v1"


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def has_pro_entitlement(user_row: Optional[Dict[str, Any]], now: Optional[datetime] = None) -> bool:
    """True if user should get Pro features (paid period or active trial)."""
    if not user_row:
        return False
    now = now or datetime.now(timezone.utc)

    pro_exp = _parse_dt(user_row.get("pro_expires_at"))
    if pro_exp and now < pro_exp:
        return True

    trial_started = _parse_dt(user_row.get("trial_started_at"))
    if trial_started:
        trial_end = trial_started + timedelta(days=TRIAL_DAYS)
        if now < trial_end:
            return True

    return False


def subscription_meta_for_user(user_row: Optional[Dict[str, Any]], now: Optional[datetime] = None) -> Dict[str, Any]:
    """Fields merged into GET /users/me for the mini-app."""
    now = now or datetime.now(timezone.utc)
    has_pro = has_pro_entitlement(user_row, now)

    trial_started = _parse_dt(user_row.get("trial_started_at")) if user_row else None
    trial_ends_at = None
    if trial_started:
        trial_ends_at = (trial_started + timedelta(days=TRIAL_DAYS)).isoformat()

    pro_expires_at = None
    if user_row and user_row.get("pro_expires_at"):
        pe = _parse_dt(user_row.get("pro_expires_at"))
        if pe:
            pro_expires_at = pe.isoformat()

    refund_deadline = None
    last_pay = _parse_dt(user_row.get("last_pro_payment_at")) if user_row else None
    if last_pay:
        refund_deadline = (last_pay + timedelta(days=REFUND_WINDOW_DAYS)).isoformat()

    return {
        "has_pro_entitlement": has_pro,
        "trial_ends_at": trial_ends_at,
        "pro_expires_at": pro_expires_at,
        "refund_eligible_until": refund_deadline,
        "pro_price_stars": PRO_PRICE_STARS,
        "trial_days": TRIAL_DAYS,
    }
