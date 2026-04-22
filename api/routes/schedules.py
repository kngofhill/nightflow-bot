from flask import Blueprint, request, jsonify
from datetime import date, datetime, timedelta
import sys
import json

sys.path.append(".")

from shared.db import supabase_client
from shared.schedule_utils import (
    calculate_optimal_schedule,
    time_to_str,
    str_to_time,
    safe_json_parse,
    classify_shift_type_from_work_start,
)
from shared.time_utils import get_user_now_from_timezone_name, DEFAULT_TIMEZONE
from shared.rotating_engine import build_rotating_day_from_pattern_row, pattern_includes_day_work
from api.request_util import get_user_from_request
from api.subscription_access import fetch_user_row_by_id, require_pro_access, user_has_active_constant_schedule
from shared.subscription import has_pro_entitlement

bp = Blueprint("schedules", __name__, url_prefix="/api/v1/schedules")


def _user_timezone(user_id: str) -> str:
    user = supabase_client.table("users").select("timezone").eq("id", user_id).execute()
    return user.data[0].get("timezone") if user.data else DEFAULT_TIMEZONE


def _shift_type_from_work_start(work_start) -> str:
    return classify_shift_type_from_work_start(work_start)


def _sync_today_daily_from_times(
    user_id: str,
    shift_type: str,
    work_start: str,
    work_end: str,
    sleep_start,
    sleep_end,
):
    timezone = _user_timezone(user_id)
    today = str(get_user_now_from_timezone_name(timezone).date())
    existing = (
        supabase_client.table("daily_schedules")
        .select("id")
        .eq("user_id", user_id)
        .eq("date", today)
        .execute()
    )
    daily_payload = {
        "shift_type": shift_type,
        "work_start": work_start,
        "work_end": work_end,
        "sleep_start": sleep_start,
        "sleep_end": sleep_end,
        "is_custom": False,
    }
    if existing.data:
        supabase_client.table("daily_schedules").update(daily_payload).eq("id", existing.data[0]["id"]).execute()
    else:
        daily_payload["user_id"] = user_id
        daily_payload["date"] = today
        supabase_client.table("daily_schedules").insert(daily_payload).execute()


def _valid_rotating_pattern_id(pid: str) -> bool:
    return pid in (
        "pitman_2_2_3",
        "block_rotation",
        "pat_4n4o4d4o",
        "pat_4n4o",
    )


def _cycle_len_for_shifts(data: dict) -> int:
    pid = str(data.get("pattern_id", ""))
    if pid == "pitman_2_2_3":
        return 14
    if pid == "pat_4n4o4d4o":
        return 16
    if pid == "pat_4n4o":
        return 8
    n = int(data.get("block_nights", 0) or 0)
    m = int(data.get("block_days", 0) or 0)
    o = int(data.get("block_off", 0) or 0)
    c = n + m + o
    return c if c > 0 else 7


@bp.route("/rotating", methods=["GET"])
def get_rotating():
    user_id, err = get_user_from_request()
    if err:
        return err
    r = (
        supabase_client.table("rotating_patterns")
        .select("*")
        .eq("user_id", user_id)
        .eq("active", True)
        .limit(1)
        .execute()
    )
    if not r.data:
        return jsonify({"error": "No active rotating pattern"}), 404
    row = dict(r.data[0])
    for k in ("shifts",):
        if isinstance(row.get(k), str):
            try:
                row[k] = json.loads(row[k])
            except (json.JSONDecodeError, TypeError, ValueError):
                row[k] = {}
    return jsonify(row)


@bp.route("/rotating", methods=["POST", "PUT"])
def upsert_rotating():
    user_id, err = get_user_from_request()
    if err:
        return err
    denied = require_pro_access(user_id)
    if denied:
        return denied

    data = request.get_json(silent=True) or {}
    sh = data.get("shifts")
    if not isinstance(sh, dict):
        sh = {}
    for k in ("pattern_id", "block_nights", "block_days", "block_off", "night", "day"):
        if k in data and data[k] is not None:
            sh[k] = data[k]
    pid = str(sh.get("pattern_id") or data.get("pattern_id", ""))
    if not _valid_rotating_pattern_id(pid):
        return jsonify({"error": "Invalid pattern_id", "code": "invalid_pattern"}), 400

    start = data.get("pattern_start_date") or data.get("patternStartDate")
    if not start:
        return jsonify({"error": "pattern_start_date required (YYYY-MM-DD)"}), 400
    if isinstance(start, str) and len(start) >= 10:
        start = start[:10]
    name = (data.get("pattern_name") or sh.get("patternName") or pid)[:200]
    c_len = int(data.get("cycle_days") or sh.get("cycleLen") or _cycle_len_for_shifts({**sh, "pattern_id": pid}))

    sh = {**sh, "pattern_id": pid}
    if "night" in sh and isinstance(sh["night"], dict):
        for k, v in list(sh["night"].items()):
            if v is not None and k in ("work_start", "work_end", "sleep_start", "sleep_end") and v != "":
                t = str_to_time(str(v)[:8])
                if t:
                    sh["night"][k] = time_to_str(t)
    if "day" in sh and isinstance(sh.get("day"), dict):
        for k, v in sh["day"].items():
            if v is not None and k in ("work_start", "work_end", "sleep_start", "sleep_end") and v != "":
                t = str_to_time(str(v)[:8])
                if t:
                    sh["day"][k] = time_to_str(t)
    if not pattern_includes_day_work(pid, int(sh.get("block_days", 14) or 0), sh):
        if "day" in sh:
            sh["day"] = None

    payload = {
        "user_id": user_id,
        "pattern_name": name,
        "cycle_days": c_len,
        "pattern_start_date": start,
        "shifts": sh,
        "active": True,
    }

    supabase_client.table("rotating_patterns").update({"active": False}).eq("user_id", user_id).eq(
        "active", True
    ).execute()
    supabase_client.table("constant_schedules").update({"active": False}).eq("user_id", user_id).eq(
        "active", True
    ).execute()
    supabase_client.table("rotating_patterns").insert(payload).execute()
    supabase_client.table("users").update({"shift_type": "rotating"}).eq("id", user_id).execute()
    r = (
        supabase_client.table("rotating_patterns")
        .select("*")
        .eq("user_id", user_id)
        .eq("active", True)
        .limit(1)
        .execute()
    )
    row = r.data[0] if r.data else payload
    return jsonify(row)


@bp.route("/rotating", methods=["PATCH"])
def patch_rotating():
    user_id, err = get_user_from_request()
    if err:
        return err
    denied = require_pro_access(user_id)
    if denied:
        return denied

    r0 = (
        supabase_client.table("rotating_patterns")
        .select("*")
        .eq("user_id", user_id)
        .eq("active", True)
        .limit(1)
        .execute()
    )
    if not r0.data:
        return jsonify({"error": "No active rotating pattern"}), 404

    data = request.get_json(silent=True) or {}
    row = dict(r0.data[0])
    sh = row.get("shifts") or {}
    if isinstance(sh, str):
        sh = safe_json_parse(sh) or {}
    if not isinstance(sh, dict):
        sh = {}
    if "shifts" in data and isinstance(data["shifts"], dict):
        sh = {**sh, **data["shifts"]}
    else:
        for k in (
            "pattern_id",
            "block_nights",
            "block_days",
            "block_off",
            "night",
            "day",
        ):
            if k in data:
                sh[k] = data[k]

    for sec in ("night", "day"):
        if sec in sh and sh[sec] is not None and not isinstance(sh[sec], dict):
            return jsonify({"error": f"shifts.{sec} must be an object or null"}), 400
        if isinstance(sh.get(sec), dict):
            for k, v in sh[sec].items():
                if v is not None and k in ("work_start", "work_end", "sleep_start", "sleep_end") and v != "":
                    t = str_to_time(str(v)[:8])
                    if t:
                        sh[sec][k] = time_to_str(t)
    if "pattern_start_date" in data and data["pattern_start_date"]:
        pstart = str(data["pattern_start_date"])[:10]
    else:
        pstart = row.get("pattern_start_date")

    old_sh = row.get("shifts") or {}
    if isinstance(old_sh, str):
        old_sh = safe_json_parse(old_sh) or {}
    if not isinstance(old_sh, dict):
        old_sh = {}
    pid = str(sh.get("pattern_id") or old_sh.get("pattern_id") or "pitman_2_2_3")
    if not _valid_rotating_pattern_id(pid):
        return jsonify({"error": "Invalid pattern_id", "code": "invalid_pattern"}), 400
    sh["pattern_id"] = pid

    if not pattern_includes_day_work(pid, int(sh.get("block_days", 14) or 0), sh) and "day" in sh:
        sh["day"] = None

    upd = {
        "shifts": sh,
        "pattern_start_date": pstart,
    }
    if "pattern_name" in data and data.get("pattern_name") is not None:
        upd["pattern_name"] = str(data.get("pattern_name", ""))[:200]
    if "pattern_id" in sh:
        c_len = _cycle_len_for_shifts({**sh, "pattern_id": sh["pattern_id"]})
        upd["cycle_days"] = c_len
    if data.get("cycle_days") is not None:
        upd["cycle_days"] = int(data["cycle_days"])
    supabase_client.table("rotating_patterns").update(upd).eq("id", row["id"]).execute()
    r2 = (
        supabase_client.table("rotating_patterns")
        .select("*")
        .eq("id", row["id"])
        .limit(1)
        .execute()
    )
    return jsonify(r2.data[0] if r2.data else row)


@bp.route("/switch-to-constant", methods=["POST"])
def switch_to_constant():
    """End rotating mode: deactivate rotating pattern and set user to permanent (constant) schedule. User must then create a constant schedule."""
    user_id, err = get_user_from_request()
    if err:
        return err
    denied = require_pro_access(user_id)
    if denied:
        return denied
    supabase_client.table("rotating_patterns").update({"active": False}).eq("user_id", user_id).eq(
        "active", True
    ).execute()
    supabase_client.table("users").update({"shift_type": "constant"}).eq("id", user_id).execute()
    return jsonify({"ok": True, "shift_type": "constant"})


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

    urow = fetch_user_row_by_id(user_id)
    if urow and not has_pro_entitlement(urow):
        schedule["coffee_windows"] = []
        schedule["meal_windows"] = []
        schedule["brightness_windows"] = []

    return jsonify(schedule)


@bp.route("/constant", methods=["PATCH"])
def patch_constant():
    user_id, err = get_user_from_request()
    if err:
        return err

    denied = require_pro_access(user_id)
    if denied:
        return denied

    data = request.get_json(silent=True) or {}
    const = (
        supabase_client.table("constant_schedules")
        .select("*")
        .eq("user_id", user_id)
        .eq("active", True)
        .execute()
    )
    if not const.data:
        return jsonify({"error": "No active schedule"}), 404

    row = dict(const.data[0])
    row_id = row["id"]
    updates = {}

    for field in ("coffee_windows", "meal_windows", "brightness_windows"):
        if field not in data:
            continue
        val = data[field]
        if val is None:
            val = []
        if not isinstance(val, list):
            return jsonify({"error": f"{field} must be a list"}), 400
        updates[field] = json.dumps(val)

    time_keys = ("work_start", "work_end", "sleep_start", "sleep_end")
    time_patch = {k: data[k] for k in time_keys if k in data}

    if time_patch:
        merged = {**row, **time_patch}
        ws = str_to_time(merged.get("work_start"))
        we = str_to_time(merged.get("work_end"))
        if not ws or not we:
            return jsonify({"error": "Invalid work hours"}), 400

        ss = str_to_time(merged.get("sleep_start")) if merged.get("sleep_start") not in (None, "") else None
        se = str_to_time(merged.get("sleep_end")) if merged.get("sleep_end") not in (None, "") else None
        if bool(ss) != bool(se):
            return jsonify({"error": "Provide both sleep_start and sleep_end, or neither"}), 400

        for f in time_keys:
            if f not in time_patch:
                continue
            raw = time_patch[f]
            if f in ("work_start", "work_end"):
                t = str_to_time(raw)
                if not t:
                    return jsonify({"error": f"Invalid {f}"}), 400
                updates[f] = time_to_str(t)
            else:
                t = str_to_time(raw) if raw not in (None, "") else None
                updates[f] = time_to_str(t) if t else None

        if "work_start" in time_patch or "work_end" in time_patch:
            updates["shift_type"] = _shift_type_from_work_start(ws)

    if not updates:
        return jsonify({"error": "No updatable fields provided"}), 400

    supabase_client.table("constant_schedules").update(updates).eq("id", row_id).execute()

    refreshed = (
        supabase_client.table("constant_schedules")
        .select("*")
        .eq("id", row_id)
        .execute()
    )
    schedule = refreshed.data[0]
    for field in ("coffee_windows", "meal_windows", "brightness_windows"):
        schedule[field] = safe_json_parse(schedule.get(field))

    if time_patch:
        _sync_today_daily_from_times(
            user_id,
            schedule.get("shift_type") or row.get("shift_type"),
            schedule.get("work_start"),
            schedule.get("work_end"),
            schedule.get("sleep_start"),
            schedule.get("sleep_end"),
        )

    return jsonify(schedule)


@bp.route("/constant", methods=["POST"])
def create_constant():
    user_id, err = get_user_from_request()
    if err:
        return err

    urow = fetch_user_row_by_id(user_id)
    if user_has_active_constant_schedule(user_id) and urow and not has_pro_entitlement(urow):
        return (
            jsonify(
                {
                    "error": "Changing your full schedule requires Nightflow Pro. Free tier keeps work & sleep for today.",
                    "code": "pro_required",
                }
            ),
            403,
        )

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

    const = (
        supabase_client.table("constant_schedules")
        .select("*")
        .eq("user_id", user_id)
        .eq("active", True)
        .execute()
    )

    urow = fetch_user_row_by_id(user_id)

    def _strip_free_windows(row_dict):
        if urow and not has_pro_entitlement(urow):
            row_dict = dict(row_dict)
            row_dict["coffee_windows"] = []
            row_dict["meal_windows"] = []
            row_dict["brightness_windows"] = []
        return row_dict

    if daily.data:
        drow = daily.data[0]
        if drow.get("shift_type") == "off":
            o = dict(drow)
            for f in ("coffee_windows", "meal_windows", "brightness_windows"):
                o[f] = safe_json_parse(o.get(f)) or []
            return jsonify(_strip_free_windows(o))

    if urow and urow.get("shift_type") == "rotating":
        rpat = (
            supabase_client.table("rotating_patterns")
            .select("*")
            .eq("user_id", user_id)
            .eq("active", True)
            .limit(1)
            .execute()
        )
        if rpat.data:
            local = get_user_now_from_timezone_name(timezone).date()
            comp = build_rotating_day_from_pattern_row(dict(rpat.data[0]), local)
            if comp is not None:
                return jsonify(_strip_free_windows(comp))
        return jsonify({"error": "No active rotating pattern"}), 404

    if daily.data:
        row = daily.data[0]
        if const.data:
            const_row = const.data[0]
            for field in ("coffee_windows", "meal_windows", "brightness_windows"):
                row[field] = safe_json_parse(const_row.get(field))
        return jsonify(_strip_free_windows(row))

    if not const.data:
        return jsonify({"error": "No schedule found"}), 404

    sched = const.data[0]
    sched["date"] = today
    for field in ("coffee_windows", "meal_windows", "brightness_windows"):
        sched[field] = safe_json_parse(sched.get(field))

    return jsonify(_strip_free_windows(sched))


@bp.route("/full", methods=["GET"])
def full_schedule():
    user_id, err = get_user_from_request()
    if err:
        return err

    denied = require_pro_access(user_id)
    if denied:
        return denied

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


def _add_minutes_to_time_hhmm(tstr: str, delta_minutes: int) -> str:
    t = str_to_time(tstr)
    if not t:
        return tstr
    base = datetime.combine(date.today(), t) + timedelta(minutes=delta_minutes)
    return time_to_str(base.time())


def _build_weekly_suggestion_items(user_id) -> list:
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
        return []

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
        coffee_misses = [
            (s.get("time"), slot_missed_count(s.get("time"), "coffee")) for s in coffee_slots if s.get("time")
        ]
        coffee_misses.sort(key=lambda x: x[1], reverse=True)
        top_time, top_missed = coffee_misses[0]
        if top_missed >= 2:
            new_t = shift_time_hhmm(top_time, -30)
            suggestions.append(
                {
                    "title": f"☕ {top_time} COFFEE",
                    "body": f"Missed {top_missed} times this week.",
                    "action": f"MOVE TO {new_t}",
                    "apply": {"op": "shift_coffee", "from": top_time, "to": new_t},
                }
            )

    if meal_slots:
        meal_misses = [
            (s.get("time"), slot_missed_count(s.get("time"), "meals")) for s in meal_slots if s.get("time")
        ]
        meal_misses.sort(key=lambda x: x[1], reverse=True)
        top_time, top_missed = meal_misses[0]
        if top_missed >= 2:
            new_t = shift_time_hhmm(top_time, -30)
            suggestions.append(
                {
                    "title": f"🍽️ {top_time} MEAL",
                    "body": f"Missed {top_missed} times this week.",
                    "action": f"MOVE TO {new_t}",
                    "apply": {"op": "shift_meal", "from": top_time, "to": new_t},
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
                    "apply": {"op": "extend_sleep", "delta_minutes": 30},
                }
            )

    return suggestions


@bp.route("/suggestions/apply", methods=["POST"])
def apply_weekly_suggestion():
    user_id, err = get_user_from_request()
    if err:
        return err

    denied = require_pro_access(user_id)
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    try:
        idx = int(body.get("suggestion_index", body.get("index", -1)))
    except (TypeError, ValueError):
        idx = -1
    if idx < 0:
        return jsonify({"error": "suggestion_index required"}), 400

    const = (
        supabase_client.table("constant_schedules")
        .select("*")
        .eq("user_id", user_id)
        .eq("active", True)
        .execute()
    )
    if not const.data:
        return jsonify({"error": "No active schedule"}), 404

    row = dict(const.data[0])
    row_id = row["id"]
    items = _build_weekly_suggestion_items(user_id)
    if idx >= len(items):
        return jsonify({"error": "That suggestion is no longer available. Refresh the list."}), 400
    apply_op = (items[idx] or {}).get("apply")
    if not apply_op or not apply_op.get("op"):
        return jsonify({"error": "No apply action for this item"}), 400

    op = apply_op["op"]
    updates = {}
    if op == "shift_coffee":
        from_t = str(apply_op.get("from") or "").strip()
        to_t = str(apply_op.get("to") or "").strip()
        ws = str_to_time(from_t)
        wt = str_to_time(to_t)
        if not ws or not wt:
            return jsonify({"error": "Invalid time"}), 400
        from_key = time_to_str(ws)
        to_key = time_to_str(wt)
        cwin = safe_json_parse(row.get("coffee_windows")) or []
        cwin = [dict(x) for x in cwin]
        hit = False
        for it in cwin:
            cur = it.get("time")
            tc = str_to_time(str(cur)[:8] if cur is not None else "")
            if tc and time_to_str(tc) == from_key:
                it["time"] = to_key
                hit = True
                break
        if not hit:
            return jsonify({"error": "That coffee time was not found (schedule may have changed)."}), 400
        updates["coffee_windows"] = json.dumps(cwin)
    elif op == "shift_meal":
        from_t = str(apply_op.get("from") or "").strip()
        to_t = str(apply_op.get("to") or "").strip()
        ws = str_to_time(from_t)
        wt = str_to_time(to_t)
        if not ws or not wt:
            return jsonify({"error": "Invalid time"}), 400
        from_key = time_to_str(ws)
        to_key = time_to_str(wt)
        mwin = safe_json_parse(row.get("meal_windows")) or []
        mwin = [dict(x) for x in mwin]
        hit = False
        for it in mwin:
            cur = it.get("time")
            tc = str_to_time(str(cur)[:8] if cur is not None else "")
            if tc and time_to_str(tc) == from_key:
                it["time"] = to_key
                hit = True
                break
        if not hit:
            return jsonify({"error": "That meal time was not found (schedule may have changed)."}), 400
        updates["meal_windows"] = json.dumps(mwin)
    elif op == "extend_sleep":
        delta = int(apply_op.get("delta_minutes") or 0)
        if delta < 0 or delta > 180:
            return jsonify({"error": "Invalid delta"}), 400
        ss = row.get("sleep_start")
        if not ss:
            return jsonify({"error": "Set sleep times first in Settings."}), 400
        t = str_to_time(str(ss)[:8] if isinstance(ss, str) else str(ss))
        if not t:
            return jsonify({"error": "Invalid sleep time"}), 400
        # Add sleep duration by moving bed earlier (e.g. 30 min = sleep_start 30m earlier)
        new_ss = _add_minutes_to_time_hhmm(time_to_str(t), -delta)
        updates["sleep_start"] = new_ss
    else:
        return jsonify({"error": "Unknown op"}), 400

    if not updates:
        return jsonify({"error": "Nothing to update"}), 400

    supabase_client.table("constant_schedules").update(updates).eq("id", row_id).execute()

    refreshed = (
        supabase_client.table("constant_schedules")
        .select("*")
        .eq("id", row_id)
        .execute()
    )
    if not refreshed.data:
        return jsonify({"error": "Update failed"}), 500
    out = dict(refreshed.data[0])
    for f in ("coffee_windows", "meal_windows", "brightness_windows"):
        out[f] = safe_json_parse(out.get(f))

    time_key_set = ("work_start", "work_end", "sleep_start", "sleep_end")
    if any(k in time_key_set for k in updates):
        _sync_today_daily_from_times(
            user_id,
            out.get("shift_type") or row.get("shift_type"),
            out.get("work_start"),
            out.get("work_end"),
            out.get("sleep_start"),
            out.get("sleep_end"),
        )

    return jsonify(out)


@bp.route("/suggestions", methods=["GET"])
def weekly_suggestions():
    user_id, err = get_user_from_request()
    if err:
        return err

    denied = require_pro_access(user_id)
    if denied:
        return denied

    return jsonify({"items": _build_weekly_suggestion_items(user_id)})
