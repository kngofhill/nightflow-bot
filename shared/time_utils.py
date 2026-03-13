from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from typing import Optional
from .schedule_utils import str_to_time

DEFAULT_TIMEZONE = "Asia/Tashkent"

def get_timezone_name_from_user_row(user_row: dict) -> str:
    return user_row.get("timezone", DEFAULT_TIMEZONE)

def get_user_now_from_timezone_name(timezone_name: str) -> datetime:
    try:
        return datetime.now(ZoneInfo(timezone_name))
    except Exception:
        return datetime.now(ZoneInfo(DEFAULT_TIMEZONE))

def combine_local_date_and_time(local_date: date, time_value, timezone_name: str) -> Optional[datetime]:
    t = str_to_time(str(time_value)) if time_value else None
    if not t:
        return None
    return datetime.combine(local_date, t, tzinfo=ZoneInfo(timezone_name))

def get_next_local_time_occurrence(time_str: str, timezone_name: str, now_local: datetime) -> Optional[datetime]:
    t = str_to_time(time_str)
    if not t:
        return None
    candidate = datetime.combine(now_local.date(), t, tzinfo=ZoneInfo(timezone_name))
    if candidate < now_local:
        candidate += timedelta(days=1)
    return candidate