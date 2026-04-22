import os
import logging
from typing import Any, Optional, Dict
from dotenv import load_dotenv
import supabase

load_dotenv()
logger = logging.getLogger(__name__)


def _is_missing_telegram_charge_column_error(exc: BaseException) -> bool:
    """PostgREST PGRST204 or similar when `telegram_payment_charge_id` is not in the DB yet."""
    text = str(exc).lower()
    return "pgrst204" in text or (
        "telegram_payment_charge_id" in text and "column" in text and "find" in text
    )


def _is_missing_telegram_charge_in_keys(upd: Dict[str, Any]) -> bool:
    return "telegram_payment_charge_id" in upd


def _is_missing_last_recurring_error(exc: BaseException) -> bool:
    t = str(exc).lower()
    if "last_payment_is_recurring" in t and (
        "pgrst204" in t
        or "schema cache" in t
        or ("column" in t and ("not find" in t or "unknown" in t or "missing" in t))
    ):
        return True
    return "pgrst204" in t and "last_payment_is_recurring" in t


def _could_be_missing_last_recurring_column(exc: BaseException) -> bool:
    t = str(exc).lower()
    return (
        "last_payment_is_recurring" in t
        or "pgrst204" in t
        or "schema cache" in t
    )


def _is_missing_subscription_flags_error(exc: BaseException) -> bool:
    t = str(exc).lower()
    return "pgrst204" in t and (
        "subscription_cancelled" in t or "subscription_active" in t or "telegram_subscription_id" in t
    )


supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

if not supabase_url or not supabase_key:
    raise ValueError("SUPABASE_URL or SUPABASE_KEY is missing")

supabase_client = supabase.create_client(supabase_url, supabase_key)


def test_connection():
    try:
        supabase_client.table("users").select("id", count="exact").limit(1).execute()
        logger.info("✅ Supabase connected successfully")
    except Exception as e:
        logger.error(f"❌ Supabase connection failed: {e}")


def get_user_id(telegram_id: int) -> Optional[str]:
    try:
        result = (
            supabase_client.table("users")
            .select("id")
            .eq("telegram_id", telegram_id)
            .execute()
        )
        if result.data:
            return result.data[0]["id"]
        return None
    except Exception as e:
        logger.error(f"Error getting user ID: {e}")
        return None


def get_user_by_telegram_id(telegram_id: int) -> Optional[Dict[str, Any]]:
    try:
        result = (
            supabase_client.table("users")
            .select("*")
            .eq("telegram_id", telegram_id)
            .execute()
        )
        if result.data:
            return result.data[0]
        return None
    except Exception as e:
        logger.error(f"Error getting user by telegram ID: {e}")
        return None


def upsert_user(telegram_id: int, username: str, first_name: str, shift_type: Optional[str] = None):
    """Insert or update user by telegram_id. Preserves trial / subscription fields on update.
    If ``shift_type`` is omitted (None), existing ``shift_type`` is not changed on update.
    """
    existing = get_user_by_telegram_id(telegram_id)
    if existing:
        update_payload: Dict[str, Any] = {
            "username": username,
            "first_name": first_name,
        }
        if shift_type is not None:
            update_payload["shift_type"] = shift_type
        return supabase_client.table("users").update(update_payload).eq("telegram_id", telegram_id).execute()
    ins: Dict[str, Any] = {
        "telegram_id": telegram_id,
        "username": username,
        "first_name": first_name,
    }
    if shift_type is not None:
        ins["shift_type"] = shift_type
    return supabase_client.table("users").insert(ins).execute()


def apply_pro_subscription_from_payment(
    telegram_id: int,
    subscription_expiration: Any = None,
    telegram_payment_charge_id: Optional[str] = None,
    is_recurring: Optional[bool] = None,
):
    """Extend Pro access from a successful Telegram Stars payment (recurring or one-time).

    ``subscription_expiration`` is ``SuccessfulPayment.subscription_expiration_date`` (int unix or datetime).
    """
    from datetime import datetime, timezone

    from shared.subscription import compute_pro_expires_after_payment

    now = datetime.now(timezone.utc)
    row = get_user_by_telegram_id(telegram_id) or {}
    new_exp = compute_pro_expires_after_payment(row, now, subscription_expiration)

    upd: Dict[str, Any] = {
        "last_pro_payment_at": now.isoformat(),
        "pro_expires_at": new_exp.isoformat(),
        "subscription_active": True,
        "subscription_cancelled": False,
    }
    if telegram_payment_charge_id:
        ch = str(telegram_payment_charge_id)
        upd["telegram_payment_charge_id"] = ch
        upd["telegram_subscription_id"] = ch
    if is_recurring is not None:
        upd["last_payment_is_recurring"] = bool(is_recurring)

    def _try_update(payload: Dict[str, Any]):
        return supabase_client.table("users").update(payload).eq("telegram_id", int(telegram_id)).execute()

    err: Optional[BaseException] = None
    try:
        return _try_update(upd)
    except Exception as e:
        err = e
        if "last_payment_is_recurring" in upd and _could_be_missing_last_recurring_column(
            e
        ):
            logger.warning(
                "Pro subscription update failed; retrying without last_payment_is_recurring: %s", e
            )
            try:
                return _try_update(
                    {k: v for k, v in upd.items() if k != "last_payment_is_recurring"}
                )
            except Exception as e2:
                err = e2

    if _is_missing_subscription_flags_error(err):
        logger.warning(
            "subscription columns missing; apply migration 20260422120000. Saving without them."
        )
        upd = {
            k: v
            for k, v in upd.items()
            if k
            not in (
                "subscription_active",
                "subscription_cancelled",
                "telegram_subscription_id",
            )
        }
        try:
            return _try_update(upd)
        except Exception as e:
            err = e

    if _is_missing_telegram_charge_column_error(err):
        logger.warning("telegram_payment_charge_id column missing; apply migration 20260421180000.")
        upd2 = {k: v for k, v in upd.items() if k not in ("telegram_payment_charge_id", "telegram_subscription_id")}
        return _try_update(upd2)

    if _is_missing_last_recurring_error(err):
        logger.warning("last_payment_is_recurring column missing; apply migration 20260422130000.")
        upd3 = {k: v for k, v in upd.items() if k != "last_payment_is_recurring"}
        return _try_update(upd3)

    raise err


def revoke_pro_subscription(telegram_id: int):
    """Immediately revoke paid Pro (e.g. Stars refund)."""
    full = {
        "pro_expires_at": None,
        "last_pro_payment_at": None,
        "telegram_payment_charge_id": None,
        "telegram_subscription_id": None,
        "subscription_cancelled": False,
        "subscription_active": False,
        "last_payment_is_recurring": None,
    }
    try:
        return supabase_client.table("users").update(full).eq("telegram_id", int(telegram_id)).execute()
    except Exception as e:
        if _is_missing_telegram_charge_column_error(e):
            logger.warning(
                "users.telegram_payment_charge_id column missing; revoking with Pro fields only. "
                "Apply migration 20260421180000_telegram_payment_charge_id.sql in Supabase."
            )
            subset = {k: v for k, v in full.items() if k != "telegram_payment_charge_id"}
            return supabase_client.table("users").update(subset).eq("telegram_id", int(telegram_id)).execute()
        if _is_missing_subscription_flags_error(e):
            subset = {
                k: v
                for k, v in full.items()
                if k
                not in (
                    "subscription_cancelled",
                    "subscription_active",
                    "telegram_subscription_id",
                )
            }
            return supabase_client.table("users").update(subset).eq("telegram_id", int(telegram_id)).execute()
        if _is_missing_last_recurring_error(e):
            subset = {k: v for k, v in full.items() if k != "last_payment_is_recurring"}
            return supabase_client.table("users").update(subset).eq("telegram_id", int(telegram_id)).execute()
        raise


def mark_star_subscription_cancelled(telegram_id: int):
    """User cancelled auto-renewal; Pro remains until pro_expires_at."""
    upd = {"subscription_cancelled": True, "subscription_active": False}
    try:
        return supabase_client.table("users").update(upd).eq("telegram_id", int(telegram_id)).execute()
    except Exception as e:
        if _is_missing_subscription_flags_error(e):
            logger.warning("subscription_cancelled / subscription_active columns missing; run migration 20260422120000")
            return None
        raise

def update_last_active(telegram_id: int, timestamp_iso: str):
    return (
        supabase_client.table("users")
        .update({"last_active": timestamp_iso})
        .eq("telegram_id", telegram_id)
        .execute()
    )


def get_active_constant_schedule(user_id: str):
    return (
        supabase_client.table("constant_schedules")
        .select("*")
        .eq("user_id", user_id)
        .eq("active", True)
        .execute()
    )


def deactivate_constant_schedules(user_id: str):
    return (
        supabase_client.table("constant_schedules")
        .update({"active": False})
        .eq("user_id", user_id)
        .eq("active", True)
        .execute()
    )


def insert_constant_schedule(payload: Dict[str, Any]):
    return supabase_client.table("constant_schedules").insert(payload).execute()


def get_daily_schedule(user_id: str, target_date: str):
    return (
        supabase_client.table("daily_schedules")
        .select("*")
        .eq("user_id", user_id)
        .eq("date", target_date)
        .execute()
    )


def insert_daily_schedule(payload: Dict[str, Any]):
    return supabase_client.table("daily_schedules").insert(payload).execute()


def update_daily_schedule(schedule_id: str, payload: Dict[str, Any]):
    return (
        supabase_client.table("daily_schedules")
        .update(payload)
        .eq("id", schedule_id)
        .execute()
    )


def get_notification_enabled(user_id: str) -> Optional[bool]:
    try:
        result = (
            supabase_client.table("users")
            .select("notification_enabled")
            .eq("id", user_id)
            .execute()
        )
        if result.data:
            return result.data[0].get("notification_enabled", True)
        return None
    except Exception as e:
        logger.error(f"Error getting notification setting: {e}")
        return None


def set_notification_enabled(user_id: str, enabled: bool):
    return (
        supabase_client.table("users")
        .update({"notification_enabled": enabled})
        .eq("id", user_id)
        .execute()
    )


def get_users_with_notifications_enabled():
    return (
        supabase_client.table("users")
        .select("id")
        .eq("notification_enabled", True)
        .execute()
    )


def insert_notification(payload: Dict[str, Any]):
    return supabase_client.table("notifications").insert(payload).execute()