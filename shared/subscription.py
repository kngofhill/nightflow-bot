"""Pro trial / Telegram Stars subscription entitlement."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

# --- # TESTING ONLY — revert entire block before production ---
PRO_PRICE_STARS = 1
# Short trial for immediate entitlement checks (no calendar-day grace).
TRIAL_ENTITLEMENT_TIMEDELTA = timedelta(minutes=5)
# --- end TESTING ONLY ---

# Production defaults (restore when reverting TESTING block):
# PRO_PRICE_STARS = 50
# TRIAL_ENTITLEMENT_TIMEDELTA = timedelta(days=14)

REFUND_WINDOW_DAYS = 3
SUBSCRIPTION_PERIOD_SECONDS = 2592000  # Telegram Stars recurring: 30 days
INVOICE_PAYLOAD_NIGHTFLOW_PRO = "nightflow_pro_v1"


def trial_period_end(trial_started: datetime) -> datetime:
    """UTC end of trial window (trial_started + trial duration)."""
    return trial_started + TRIAL_ENTITLEMENT_TIMEDELTA


def paid_pro_period_active(user_row: Optional[Dict[str, Any]], now: Optional[datetime] = None) -> bool:
    """True if user has an unexpired paid Pro window (``pro_expires_at`` in the future)."""
    if not user_row:
        return False
    now = now or datetime.now(timezone.utc)
    pro_exp = _parse_dt(user_row.get("pro_expires_at"))
    return bool(pro_exp and now < pro_exp)


def within_refund_window(user_row: Optional[Dict[str, Any]], now: Optional[datetime] = None) -> bool:
    """True if ``last_pro_payment_at`` is within ``REFUND_WINDOW_DAYS`` (Telegram refund policy)."""
    if not user_row or not user_row.get("last_pro_payment_at"):
        return False
    now = now or datetime.now(timezone.utc)
    last_pay = _parse_dt(user_row.get("last_pro_payment_at"))
    if not last_pay:
        return False
    return now <= last_pay + timedelta(days=REFUND_WINDOW_DAYS)


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
        trial_end = trial_period_end(trial_started)
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
        trial_ends_at = trial_period_end(trial_started).isoformat()

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
        # TESTING ONLY: short trial; use trial_ends_at for truth (not this day count).
        "trial_days": int(TRIAL_ENTITLEMENT_TIMEDELTA.total_seconds() // 86400),
    }


def subscription_debug_summary(user_row: Optional[Dict[str, Any]], now: Optional[datetime] = None) -> str:
    """# TESTING ONLY — text for /status bot command."""
    if not user_row:
        return "No user record."
    now = now or datetime.now(timezone.utc)
    meta = subscription_meta_for_user(user_row, now)
    lines = [
        "Nightflow status (debug, TESTING build):",
        f"Pro features now: {'yes' if meta['has_pro_entitlement'] else 'no'}",
    ]
    ts = _parse_dt(user_row.get("trial_started_at"))
    if ts:
        te = trial_period_end(ts)
        active = "active" if now < te else "ended"
        lines.append(f"Trial: ends {te.isoformat()} UTC ({active})")
    else:
        lines.append("Trial: not started")
    pe = _parse_dt(user_row.get("pro_expires_at"))
    lines.append(f"Paid Pro expires: {pe.isoformat() if pe else 'n/a'}")
    lines.append(f"Last Stars payment: {user_row.get('last_pro_payment_at') or 'n/a'}")
    lines.append(f"Refund window (3d from payment): {'eligible' if within_refund_window(user_row, now) else 'not eligible'}")
    return "\n".join(lines)
