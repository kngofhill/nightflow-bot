from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
import sys
import json

sys.path.append(".")

from shared.db import supabase_client
from shared.schedule_utils import calculate_optimal_schedule, time_to_str, str_to_time, safe_json_parse
from shared.time_utils import get_user_now_from_timezone_name, DEFAULT_TIMEZONE
from api.request_util import get_user_from_request

bp = Blueprint("schedules", __name__, url_prefix="/api/v1/schedules")


def _user_timezone(user_id: str) -> str:
    user = supabase_client.table("users").select("timezone").eq("id", user_id).execute()
    return user.data[0].get("timezone") if user.data else DEFAULT_TIMEZONE


@bp.route("/constant", methods=["GET"])
def get_constant():
    user_id, err = get_user_from_request()
    if err:
        return err

    const = (
        supabase_client.table("constant_schedules")
        .select("*")
        .eq("user_id", user_id)
        .eq("active", True)
        .execute()
    )
    if not const.data:
        return jsonify({"error": "No active schedule"}), 404

    schedule = const.data[0]
    for field in ("coffee_windows", "meal_windows", "brightness_windows"):
        schedule[field] = safe_json_parse(schedule.get(field))

    return jsonify(schedule)


@bp.route("/constant", methods=["POST"])
def create_constant():
    user_id, err = get_user_from_request()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    work_start = str_to_time(data.get("work_start"))
    work_end = str_to_time(data.get("work_end"))
    if not work_start or not work_end:
        return jsonify({"error": "Invalid work hours"}), 400

    opt_sleep_start = str_to_time(data.get("sleep_start"))
    opt_sleep_end = str_to_time(data.get("sleep_end"))
    if bool(opt_sleep_start) != bool(opt_sleep_end):
        return jsonify({"error": "Provide both sleep_start and sleep_end, or neither"}), 400

    timezone = _user_timezone(user_id)
    optimized = calculate_optimal_schedule(
        work_start,
        work_end,
        opt_sleep_start,
        opt_sleep_end,
    )

    today = str(get_user_now_from_timezone_name(timezone).date())

    supabase_client.table("constant_schedules").update({"active": False}).eq("user_id", user_id).eq(
        "active", True
    ).execute()

    insert_data = {
        "user_id": user_id,
        "work_start": time_to_str(work_start),
        "work_end": time_to_str(work_end),
        "sleep_start": optimized["sleep_start"],
        "sleep_end": optimized["sleep_end"],
        "coffee_windows": optimized["coffee_windows"],
        "meal_windows": optimized["meal_windows"],
        "brightness_windows": optimized["brightness_windows"],
        "shift_type": optimized["shift_type"],
        "active": True,
    }
    for field in ("coffee_windows", "meal_windows", "brightness_windows"):
        insert_data[field] = json.dumps(insert_data[field])
    supabase_client.table("constant_schedules").insert(insert_data).execute()

    existing = (
        supabase_client.table("daily_schedules")
        .select("id")
        .eq("user_id", user_id)
        .eq("date", today)
        .execute()
    )
    daily_payload = {
        "user_id": user_id,
        "date": today,
        "shift_type": optimized["shift_type"],
        "work_start": time_to_str(work_start),
        "work_end": time_to_str(work_end),
        "sleep_start": optimized["sleep_start"],
        "sleep_end": optimized["sleep_end"],
        "is_custom": False,
    }
    if existing.data:
        supabase_client.table("daily_schedules").update(daily_payload).eq("id", existing.data[0]["id"]).execute()
    else:
        supabase_client.table("daily_schedules").insert(daily_payload).execute()

    return jsonify(optimized)


@bp.route("/daily/today", methods=["GET"])
def today_daily():
    user_id, err = get_user_from_request()
    if err:
        return err

    timezone = _user_timezone(user_id)
    today = str(get_user_now_from_timezone_name(timezone).date())

    daily = supabase_client.table("daily_schedules").select("*").eq("user_id", user_id).eq("date", today).execute()
    if daily.data:
        row = daily.data[0]
        for field in ("coffee_windows", "meal_windows", "brightness_windows"):
            if field in row and row[field] is not None:
                row[field] = safe_json_parse(row.get(field))
        return jsonify(row)

    const = (
        supabase_client.table("constant_schedules")
        .select("*")
        .eq("user_id", user_id)
        .eq("active", True)
        .execute()
    )
    if not const.data:
        return jsonify({"error": "No schedule found"}), 404

    sched = const.data[0]
    sched["date"] = today
    for field in ("coffee_windows", "meal_windows", "brightness_windows"):
        sched[field] = safe_json_parse(sched.get(field))

    return jsonify(sched)


@bp.route("/full", methods=["GET"])
def full_schedule():
    user_id, err = get_user_from_request()
    if err:
        return err

    const = (
        supabase_client.table("constant_schedules")
        .select("*")
        .eq("user_id", user_id)
        .eq("active", True)
        .execute()
    )
    if not const.data:
        return jsonify({"error": "No schedule found"}), 404

    schedule = const.data[0]
    for field in ("coffee_windows", "meal_windows", "brightness_windows"):
        schedule[field] = safe_json_parse(schedule.get(field))

    return jsonify(schedule)


@bp.route("/caffeine/check", methods=["GET"])
def caffeine_check():
    user_id, err = get_user_from_request()
    if err:
        return err

    const = (
        supabase_client.table("constant_schedules")
        .select("*")
        .eq("user_id", user_id)
        .eq("active", True)
        .execute()
    )
    if not const.data:
        return jsonify({"error": "No schedule found. Please set up your schedule first."}), 404

    schedule = const.data[0]
    sleep_start = schedule.get("sleep_start")
    if not sleep_start:
        return jsonify({"error": "Sleep time not set in schedule."}), 400

    tz_name = _user_timezone(user_id)
    now = get_user_now_from_timezone_name(tz_name)

    sleep_start_str = sleep_start[:5]
    sleep_time = datetime.strptime(sleep_start_str, "%H:%M").time()
    sleep_dt = datetime.combine(now.date(), sleep_time, tzinfo=now.tzinfo)
    if sleep_dt <= now:
        sleep_dt = sleep_dt + timedelta(days=1)

    cutoff = sleep_dt - timedelta(hours=6)
    if now >= cutoff:
        minutes_until_sleep = int((sleep_dt - now).total_seconds() / 60)
        hours = minutes_until_sleep // 60
        mins = minutes_until_sleep % 60
        message = (
            f"🚫 **Caffeine window closed!**\n\nYou're within 6 hours of sleep.\n"
            f"Sleep starts at {sleep_start_str} (in {hours}h {mins}m).\nCoffee now may disrupt your sleep."
        )
    else:
        minutes_left = int((cutoff - now).total_seconds() / 60)
        hours_left = minutes_left // 60
        mins_left = minutes_left % 60
        message = (
            f"✅ **Safe for caffeine!**\n\nYou have {hours_left}h {mins_left}m left before the 6-hour sleep window closes.\n"
            f"Last call: {cutoff.strftime('%H:%M')}"
        )

    return jsonify({"message": message})


@bp.route("/dayoff", methods=["POST"])
def set_day_off():
    user_id, err = get_user_from_request()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    date_str = data.get("date")
    if not date_str:
        timezone = _user_timezone(user_id)
        date_str = str(get_user_now_from_timezone_name(timezone).date())

    existing = (
        supabase_client.table("daily_schedules")
        .select("id")
        .eq("user_id", user_id)
        .eq("date", date_str)
        .execute()
    )

    payload = {
        "user_id": user_id,
        "date": date_str,
        "shift_type": "off",
        "work_start": None,
        "work_end": None,
        "sleep_start": None,
        "sleep_end": None,
        "is_custom": True,
    }

    if existing.data:
        supabase_client.table("daily_schedules").update(payload).eq("id", existing.data[0]["id"]).execute()
    else:
        supabase_client.table("daily_schedules").insert(payload).execute()

    return jsonify({"ok": True, "message": "Day off set successfully!"})


@bp.route("/suggestions", methods=["GET"])
def weekly_suggestions():
    user_id, err = get_user_from_request()
    if err:
        return err

    timezone = _user_timezone(user_id)
    now_local = get_user_now_from_timezone_name(timezone)
    local_today = now_local.date()
    week_start = local_today - timedelta(days=local_today.weekday())
    week_end = week_start + timedelta(days=6)

    const = (
        supabase_client.table("constant_schedules")
        .select("*")
        .eq("user_id", user_id)
        .eq("active", True)
        .execute()
    )
    if not const.data:
        return jsonify({"items": []})

    schedule = const.data[0]
    schedule["coffee_windows"] = safe_json_parse(schedule.get("coffee_windows"))
    schedule["meal_windows"] = safe_json_parse(schedule.get("meal_windows"))

    coffee_slots = schedule.get("coffee_windows") or []
    meal_slots = schedule.get("meal_windows") or []

    def time_minutes(tstr):
        t = str_to_time(tstr)
        if not t:
            return 0
        return t.hour * 60 + t.minute

    coffee_slots = sorted(coffee_slots, key=lambda x: time_minutes(x.get("time")))
    meal_slots = sorted(meal_slots, key=lambda x: time_minutes(x.get("time")))

    rows = (
        supabase_client.table("shift_summaries")
        .select("local_date, energy, sleep_quality, responses")
        .eq("user_id", user_id)
        .gte("local_date", str(week_start))
        .lte("local_date", str(week_end))
        .execute()
    )

    def parse_responses(resp):
        if resp is None:
            return {}
        if isinstance(resp, str):
            try:
                return json.loads(resp)
            except Exception:
                return {}
        if isinstance(resp, dict):
            return resp
        return {}

    summaries_by_date = {}
    for r in rows.data or []:
        summaries_by_date[str(r.get("local_date"))] = r

    def slot_missed_count(slot_time, kind):
        missed = 0
        for i in range(7):
            d = week_start + timedelta(days=i)
            r = summaries_by_date.get(str(d))
            if not r:
                missed += 1
                continue
            resp = parse_responses(r.get("responses"))
            arr = resp.get(kind) or []
            rating = None
            for item in arr:
                if item and item.get("time") == slot_time:
                    rating = item.get("rating")
                    break
            if rating is None:
                missed += 1
            elif int(rating) <= 1:
                missed += 1
        return missed

    def shift_time_hhmm(tstr, delta_minutes):
        t = str_to_time(tstr)
        if not t:
            return tstr
        mins = (t.hour * 60 + t.minute + delta_minutes) % (24 * 60)
        hh = mins // 60
        mm = mins % 60
        return f"{hh:02d}:{mm:02d}"

    suggestions = []

    if coffee_slots:
        coffee_misses = [(s.get("time"), slot_missed_count(s.get("time"), "coffee")) for s in coffee_slots if s.get("time")]
        coffee_misses.sort(key=lambda x: x[1], reverse=True)
        top_time, top_missed = coffee_misses[0]
        if top_missed >= 2:
            suggestions.append(
                {
                    "title": f"☕ {top_time} COFFEE",
                    "body": f"Missed {top_missed} times this week.",
                    "action": f"MOVE TO {shift_time_hhmm(top_time, -30)}",
                }
            )

    if meal_slots:
        meal_misses = [(s.get("time"), slot_missed_count(s.get("time"), "meals")) for s in meal_slots if s.get("time")]
        meal_misses.sort(key=lambda x: x[1], reverse=True)
        top_time, top_missed = meal_misses[0]
        if top_missed >= 2:
            suggestions.append(
                {
                    "title": f"🍽️ {top_time} MEAL",
                    "body": f"Missed {top_missed} times this week.",
                    "action": f"MOVE TO {shift_time_hhmm(top_time, -30)}",
                }
            )

    sleep_vals = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        r = summaries_by_date.get(str(d))
        if r and r.get("sleep_quality") is not None:
            sleep_vals.append(int(r.get("sleep_quality")))
    if sleep_vals:
        avg_sleep = sum(sleep_vals) / len(sleep_vals)
        if avg_sleep <= 2:
            deficit_hours = int(round(max(0, 2.5 - avg_sleep) * 16))
            if deficit_hours <= 0:
                deficit_hours = 8
            suggestions.append(
                {
                    "title": "😴 SLEEP WINDOW",
                    "body": f"Deficit: {deficit_hours} hours this week.",
                    "action": "ADD 30 MINUTES",
                }
            )

    return jsonify({"items": suggestions})
