"""Pro trial / Telegram Stars subscription entitlement."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from shared.schedule_utils import safe_json_parse

# --- # TESTING ONLY — 1 Star price + short trial; production: set PRO_PRICE_STARS = 50
PRO_PRICE_STARS = 1
TRIAL_ENTITLEMENT_TIMEDELTA = timedelta(minutes=5)
# --- end TESTING ONLY ---
# For a normal 14-day trial instead: TRIAL_ENTITLEMENT_TIMEDELTA = timedelta(days=14)

REFUND_WINDOW_DAYS = 3
"""Max completed Pro (Stars) refunds per UTC calendar month — stored under ``notification_prefs``."""
MAX_PRO_REFUNDS_PER_UTC_MONTH = 3
PRO_REFUND_COUNTS_BY_MONTH_KEY = "pro_refund_counts_by_month"
"""Recent ``telegram_payment_charge_id`` values already counted toward the monthly cap (dedupe bot + Telegram updates)."""
PRO_REFUND_RECORDED_CHARGE_IDS_KEY = "pro_refund_recorded_charge_ids"
SUBSCRIPTION_PERIOD_SECONDS = 2592000  # 30 days — Telegram Stars recurring
PRO_SUBSCRIPTION_DAYS = 30
INVOICE_PAYLOAD_NIGHTFLOW_PRO = "nightflow_pro_v1"

# Shown when /cancel or app cancel works without Telegram (one-time XTR, or API fallback)
MSG_CANCEL_ONETIME_EXPLANATION = (
    "Your last payment was a one-time Stars purchase (Telegram could not use a recurring subscription for this payment — "
    "e.g. Subscription_export_missing, or the invoice was sent without subscription_period). "
    "There is no subscription in Telegram to cancel. "
    "Nightflow is updated: you will not be charged again unless you pay again. "
    "You keep Pro until {pro_exp}."
)
MSG_CANCEL_TELEGRAM_CHARGE_INVALID_FALLBACK = (
    "Telegram does not accept this charge for subscription cancellation (CHARGE_ID_INVALID). "
    "That usually means the payment was one-time, not a recurring Stars subscription. "
    "Nightflow is updated: auto-renewal is off in the app. You keep Pro until {pro_exp}."
)


def should_skip_telegram_star_cancel(user_row: Optional[Dict[str, Any]]) -> bool:
    """True when the last payment was one-time — ``editUserStarSubscription`` does not apply."""
    if not user_row:
        return False
    return user_row.get("last_payment_is_recurring") is False


def _parse_telegram_subscription_expiration(value: Any) -> Optional[datetime]:
    """``SuccessfulPayment.subscription_expiration_date`` may be unix (int) or ``datetime`` (PTB 21+)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return _parse_dt(value)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    if isinstance(value, str):
        return _parse_dt(value)
    return None


def compute_pro_expires_after_payment(
    user_row: Optional[Dict[str, Any]],
    now: datetime,
    subscription_expiration: Optional[Any] = None,
) -> datetime:
    """After a successful Stars payment, extend Pro by 30 days from current paid expiry or from now.

    If Telegram sends ``subscription_expiration_date`` (unix or datetime), the later of (computed, Telegram) is used
    so renewals are never shorter than the invoice period.
    """
    now = now.astimezone(timezone.utc)
    current = _parse_dt((user_row or {}).get("pro_expires_at")) if user_row else None
    if current and current > now:
        new_exp = current + timedelta(days=PRO_SUBSCRIPTION_DAYS)
    else:
        new_exp = now + timedelta(days=PRO_SUBSCRIPTION_DAYS)
    from_telegram = _parse_telegram_subscription_expiration(subscription_expiration)
    if from_telegram is not None and from_telegram > new_exp:
        new_exp = from_telegram
    return new_exp


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


def _notification_prefs_dict(user_row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = (user_row or {}).get("notification_prefs")
    p = safe_json_parse(raw) if raw is not None else {}
    return p if isinstance(p, dict) else {}


def pro_refunds_this_utc_month(user_row: Optional[Dict[str, Any]], now: Optional[datetime] = None) -> int:
    """How many Pro Stars refunds were recorded this calendar month (UTC)."""
    now = now or datetime.now(timezone.utc)
    ym = now.astimezone(timezone.utc).strftime("%Y-%m")
    prefs = _notification_prefs_dict(user_row)
    d = prefs.get(PRO_REFUND_COUNTS_BY_MONTH_KEY)
    if not isinstance(d, dict):
        return 0
    try:
        return int(d.get(ym) or 0)
    except (TypeError, ValueError):
        return 0


def pro_refund_month_limit_reached(user_row: Optional[Dict[str, Any]], now: Optional[datetime] = None) -> bool:
    """True if the user cannot start another /refund this UTC month (abuse prevention)."""
    return pro_refunds_this_utc_month(user_row, now) >= MAX_PRO_REFUNDS_PER_UTC_MONTH


def merge_notification_prefs_increment_pro_refund(raw_prefs: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Return a full ``notification_prefs`` dict with this month's refund count bumped by 1."""
    now = now or datetime.now(timezone.utc)
    ym = now.astimezone(timezone.utc).strftime("%Y-%m")
    prefs = safe_json_parse(raw_prefs) if raw_prefs is not None else {}
    if not isinstance(prefs, dict):
        prefs = {}
    out = dict(prefs)
    d0 = out.get(PRO_REFUND_COUNTS_BY_MONTH_KEY)
    d: Dict[str, int] = {}
    if isinstance(d0, dict):
        for k, v in d0.items():
            ks = str(k)
            if not _is_year_month_key(ks):
                continue
            try:
                d[ks] = int(v)
            except (TypeError, ValueError):
                continue
    d[ym] = int(d.get(ym) or 0) + 1
    # Keep a small window of months so the JSON does not grow forever.
    keep = sorted([k for k in d if _is_year_month_key(k)], reverse=True)[:6]
    out[PRO_REFUND_COUNTS_BY_MONTH_KEY] = {k: d[k] for k in keep if k in d}
    return out


def try_record_pro_refund_count(
    raw_prefs: Any, charge_id: Optional[str] = None
) -> tuple[Dict[str, Any], bool]:
    """
    Bump monthly refund count unless ``charge_id`` was already recorded (prevents double count when
    both ``/refund`` and a Telegram ``refunded_payment`` message refer to the same charge).

    Returns ``(new notification_prefs dict, did_increment)``.
    """
    prefs = safe_json_parse(raw_prefs) if raw_prefs is not None else {}
    if not isinstance(prefs, dict):
        prefs = {}
    out = dict(prefs)
    recorded = out.get(PRO_REFUND_RECORDED_CHARGE_IDS_KEY)
    if not isinstance(recorded, list):
        recorded = []
    rec_set = {str(x) for x in recorded if x is not None and str(x).strip() != ""}
    ch = (charge_id or "").strip()
    if ch and ch in rec_set:
        return out, False
    out = merge_notification_prefs_increment_pro_refund(out)
    if ch:
        rec = list(recorded) + [ch]
        out[PRO_REFUND_RECORDED_CHARGE_IDS_KEY] = rec[-100:]
    return out, True


def _is_year_month_key(s: str) -> bool:
    if len(s) != 7 or s[4] != "-":
        return False
    try:
        y, m = int(s[:4]), int(s[5:7])
        return 2000 <= y <= 2100 and 1 <= m <= 12
    except ValueError:
        return False


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
    pro_expires_dt = None
    if user_row and user_row.get("pro_expires_at"):
        pro_expires_dt = _parse_dt(user_row.get("pro_expires_at"))
        if pro_expires_dt:
            pro_expires_at = pro_expires_dt.isoformat()

    refund_deadline = None
    last_pay = _parse_dt(user_row.get("last_pro_payment_at")) if user_row else None
    if last_pay:
        refund_deadline = (last_pay + timedelta(days=REFUND_WINDOW_DAYS)).isoformat()

    sub_cancel = bool((user_row or {}).get("subscription_cancelled")) if user_row else False
    sub_active = (user_row or {}).get("subscription_active")
    if sub_active is None:
        sub_active = True
    else:
        sub_active = bool(sub_active)

    last_pay_exists = bool(last_pay)
    ch_id = (user_row or {}).get("telegram_payment_charge_id") if user_row else None
    is_onetime = (user_row or {}).get("last_payment_is_recurring") is False
    # One-time: no Telegram subscription to cancel — DB-only. Recurring/unknown: need charge id to call Telegram (or try + fallback).
    can_cancel = (
        has_pro
        and last_pay_exists
        and not sub_cancel
        and sub_active
        and pro_expires_dt is not None
        and now < pro_expires_dt
        and (is_onetime or bool(ch_id))
    )

    return {
        "has_pro_entitlement": has_pro,
        "active_paid_pro": paid_pro_period_active(user_row, now),
        "trial_ends_at": trial_ends_at,
        "pro_expires_at": pro_expires_at,
        "refund_eligible_until": refund_deadline,
        "pro_price_stars": PRO_PRICE_STARS,
        # TESTING ONLY: short trial; use trial_ends_at for truth (not this day count).
        "trial_days": int(TRIAL_ENTITLEMENT_TIMEDELTA.total_seconds() // 86400),
        "subscription_cancelled": sub_cancel,
        "subscription_active": sub_active,
        "last_payment_is_recurring": user_row.get("last_payment_is_recurring")
        if user_row
        else None,
        "can_cancel_star_subscription": can_cancel,
    }


def explain_cannot_cancel_star_subscription(
    user_row: Optional[Dict[str, Any]], meta: Optional[Dict[str, Any]] = None, now: Optional[datetime] = None
) -> str:
    """Long-form reason when ``can_cancel_star_subscription`` is false (for /cancel and support)."""
    now = now or datetime.now(timezone.utc)
    meta = meta or (subscription_meta_for_user(user_row, now) if user_row else {})
    if not user_row:
        return (
            "Cannot stop auto-renewal: there is no Nightflow account in the database yet. "
            "Send /start, open the mini-app once, then try /cancel again."
        )
    lines = [
        "Cannot stop auto-renewal with /cancel right now.",
        "Details:",
    ]
    if not user_row.get("last_pro_payment_at"):
        lines.append(
            "• No completed Stars payment is stored. This command only applies to paid Pro (not the free trial). "
            "Use /subscribe or pay from the mini-app first."
        )
    is_onetime = user_row.get("last_payment_is_recurring") is False
    if not user_row.get("telegram_payment_charge_id") and not is_onetime:
        lines.append(
            "• No `telegram_payment_charge_id` in the database — apply the Supabase migration, then complete a new payment. "
            "(If your last payment was one-time, `last_payment_is_recurring` should be false and charge id is optional for cancel.)"
        )
    if user_row.get("subscription_cancelled"):
        lines.append(
            "• You already cancelled: no further auto-charges. You keep Pro until the end date shown in /status."
        )
    if user_row.get("subscription_active") is False and not user_row.get("subscription_cancelled"):
        lines.append("• Subscription is marked inactive (for example after a full refund).")
    if not meta.get("has_pro_entitlement"):
        lines.append("• You do not have active Pro entitlement (trial may have ended without a paid plan).")
    pro_expires_dt = _parse_dt(user_row.get("pro_expires_at")) if user_row else None
    if pro_expires_dt and now >= pro_expires_dt:
        lines.append("• Your paid Pro period has already ended.")
    if len(lines) == 2:
        lines.append(
            "• Auto-renewal can only be stopped from this bot chat: send /cancel here (not from the mini app)."
        )
    return "\n".join(lines)


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
    rec = user_row.get("last_payment_is_recurring")
    lines.append(
        f"Last payment recurring (Telegram): {rec if rec is not None else 'unknown (null — old row)'}"
    )
    lines.append(f"Refund window (3d from payment): {'eligible' if within_refund_window(user_row, now) else 'not eligible'}")
    n = pro_refunds_this_utc_month(user_row, now)
    lines.append(
        f"Pro refunds this UTC month: {n}/{MAX_PRO_REFUNDS_PER_UTC_MONTH} "
        f"({'limit reached' if n >= MAX_PRO_REFUNDS_PER_UTC_MONTH else 'under cap'})"
    )
    return "\n".join(lines)
