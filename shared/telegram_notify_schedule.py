"""Bot-side schedule resolution + notification dedupe (mirrors /schedules/daily/today for Pro)."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional, Set, Tuple
from shared.db import supabase_client
from shared.schedule_utils import safe_json_parse, str_to_time
from shared.time_utils import get_user_now_from_timezone_name, combine_local_date_and_time

logger = logging.getLogger(__name__)


def format_hhmm(value: Any) -> Optional[str]:
    """DB may return 22:00, 22:00:00, time, or datetime — normalize to HH:MM for comparisons."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%H:%M")
    if hasattr(value, "hour") and hasattr(value, "minute") and not isinstance(value, datetime):
        t = value
    else:
        t = str_to_time(str(value)[:8])
    if not t:
        return None
    return t.strftime("%H:%M")


def parse_notification_prefs(user_row: Dict[str, Any]) -> Dict[str, bool]:
    raw = user_row.get("notification_prefs")
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
    if not isinstance(raw, dict):
        return {}
    return {
        "notifCoffee": bool(raw.get("notifCoffee", True)),
        "notifMeal": bool(raw.get("notifMeal", True)),
        "notifLight": bool(raw.get("notifLight", True)),
        "notifSleep": bool(raw.get("notifSleep", True)),
        "notifSummary": bool(raw.get("notifSummary", True)),
        "notifWork": bool(raw.get("notifWork", True)),
    }


def fetch_today_sent_dedup_keys(user_id: str, local_today: date) -> Set[Tuple[str, str, str, str]]:
    """
    (db_type, kind, slot, local_date) for rows we already sent.
    `kind` matches metadata['kind'] (for custom: work_start, work_end, summary) or same as type for first-class types.
    """
    keys: Set[Tuple[str, str, str, str]] = set()
    today_s = str(local_today)
    try:
        r = (
            supabase_client.table("notifications")
            .select("type, metadata")
            .eq("user_id", user_id)
            .eq("sent", True)
            .limit(500)
            .execute()
        )
    except Exception as e:
        logger.warning("dedup query failed: %s", e)
        return keys

    for row in r.data or []:
        m = row.get("metadata") or {}
        if str(m.get("local_date", "")) != today_s:
            continue
        t = str(row.get("type") or "")
        slot = str(m.get("slot") or "")
        kind = m.get("kind")
        if kind is None or kind is True:
            kind = t
        k = (t, str(kind), slot, today_s)
        keys.add(k)
    return keys


def fetch_effective_schedule_today(user_id: str, today_str: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    `status` is 'ok', 'off', or 'no_constant'.
    Same merge as /schedules/daily/today: daily row wins work/sleep; coffee/meal/bright from constant.
    Pro-only windows are not stripped here — caller is Pro-only.
    """
    const = (
        supabase_client.table("constant_schedules")
        .select("*")
        .eq("user_id", user_id)
        .eq("active", True)
        .limit(1)
        .execute()
    )
    if not const.data:
        return "no_constant", None

    c0 = dict(const.data[0])
    for f in ("coffee_windows", "meal_windows", "brightness_windows"):
        c0[f] = safe_json_parse(c0.get(f))

    daily = (
        supabase_client.table("daily_schedules")
        .select("*")
        .eq("user_id", user_id)
        .eq("date", today_str)
        .limit(1)
        .execute()
    )

    if daily.data:
        row = dict(daily.data[0])
        if row.get("shift_type") == "off":
            return "off", None
        for field in ("coffee_windows", "meal_windows", "brightness_windows"):
            row[field] = c0[field]
        return "ok", row

    c0["date"] = today_str
    for field in ("coffee_windows", "meal_windows", "brightness_windows"):
        c0[field] = safe_json_parse(c0.get(field))
    return "ok", c0


def sleep_window_reminder_hhmm(sleep_str: str, local_date: date, tz: str) -> Optional[str]:
    """
    30 minutes before the next local sleep time (tonight or tomorrow) — as HH:MM in user's TZ.
    Matches prior bot logic, but returns normalized string for the tick minute.
    """
    now_local = get_user_now_from_timezone_name(tz)
    sleep_dt = combine_local_date_and_time(local_date, sleep_str, tz)
    if not sleep_dt:
        return None
    if sleep_dt <= now_local:
        sleep_dt = sleep_dt + timedelta(days=1)
    t30 = sleep_dt - timedelta(minutes=30)
    return t30.strftime("%H:%M")
