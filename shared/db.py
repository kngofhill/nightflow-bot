import os
import logging
from typing import Optional, Dict, Any
from dotenv import load_dotenv
import supabase

load_dotenv()
logger = logging.getLogger(__name__)

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


def upsert_user(telegram_id: int, username: str, first_name: str, shift_type: str):
    return (
        supabase_client.table("users")
        .upsert({
            "telegram_id": telegram_id,
            "username": username,
            "first_name": first_name,
            "shift_type": shift_type,
        })
        .execute()
    )


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