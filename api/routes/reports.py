from flask import Blueprint, request, jsonify
from datetime import date, timedelta
import sys
import json

sys.path.append(".")

from shared.db import supabase_client
from shared.time_utils import get_user_now_from_timezone_name, DEFAULT_TIMEZONE
from shared.schedule_utils import safe_json_parse, str_to_time
from api.request_util import get_user_from_request
from api.subscription_access import require_pro_access

bp = Blueprint("reports", __name__, url_prefix="/api/v1/reports")


def _parse_responses(resp):
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


def _time_to_minutes(tstr):
    t = str_to_time(tstr)
    if not t:
        return 0
    return t.hour * 60 + t.minute


EMOJI_ENERGY = {1: "😴", 2: "😐", 3: "😊", 4: "⚡"}


@bp.route("/weekly", methods=["GET"])
def weekly_report():
    user_id, err = get_user_from_request()
    if err:
        return err

    denied = require_pro_access(user_id)
    if denied:
        return denied

    user = supabase_client.table("users").select("timezone").eq("id", user_id).execute()
    tz = user.data[0].get("timezone") if user.data else DEFAULT_TIMEZONE
    now_local = get_user_now_from_timezone_name(tz)
    local_today = now_local.date()

    start_q = request.args.get("start_date")
    end_q = request.args.get("end_date")
    if start_q and end_q:
        try:
            week_start = date.fromisoformat(start_q)
            week_end = date.fromisoformat(end_q)
            if week_end < week_start:
                return jsonify({"error": "end_date must be on or after start_date"}), 400
        except ValueError:
            return jsonify({"error": "Invalid start_date or end_date"}), 400
    else:
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
        return jsonify({"error": "No active schedule"}), 404

    schedule = const.data[0]
    schedule["coffee_windows"] = safe_json_parse(schedule.get("coffee_windows"))
    schedule["meal_windows"] = safe_json_parse(schedule.get("meal_windows"))

    coffee_slots = schedule.get("coffee_windows") or []
    meal_slots = schedule.get("meal_windows") or []
    coffee_slots = sorted(coffee_slots, key=lambda x: _time_to_minutes(x.get("time")))
    meal_slots = sorted(meal_slots, key=lambda x: _time_to_minutes(x.get("time")))

    rows = (
        supabase_client.table("shift_summaries")
        .select("local_date, energy, sleep_quality, responses")
        .eq("user_id", user_id)
        .gte("local_date", str(week_start))
        .lte("local_date", str(week_end))
        .execute()
    )
    summaries_by_date = {}
    for r in rows.data or []:
        summaries_by_date[str(r.get("local_date"))] = r

    energy_emojis = []
    energy_numeric = [None] * 7
    sleep_vals = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        r = summaries_by_date.get(str(d))
        if r and r.get("energy") is not None:
            ev = int(r.get("energy"))
            energy_emojis.append(EMOJI_ENERGY.get(ev, "—"))
            if 1 <= ev <= 4:
                energy_numeric[i] = ev
        else:
            energy_emojis.append("—")

        if r and r.get("sleep_quality") is not None:
            sleep_vals.append(int(r.get("sleep_quality")))

    def _week_energy_trend(nums):
        early = [nums[i] for i in (0, 1, 2) if nums[i] is not None]
        late = [nums[i] for i in (4, 5, 6) if nums[i] is not None]
        if len(early) < 1 or len(late) < 1:
            flat = [x for x in nums if x is not None]
            if len(flat) < 3:
                return None
            m = len(flat) // 2
            a = sum(flat[:m]) / m
            b = sum(flat[m:]) / (len(flat) - m)
        else:
            a = sum(early) / len(early)
            b = sum(late) / len(late)
        if b - a > 0.35:
            return "up"
        if a - b > 0.35:
            return "down"
        return "steady"

    energy_count = {1: 0, 2: 0, 3: 0, 4: 0}
    for n in energy_numeric:
        if n in energy_count:
            energy_count[n] += 1
    days_with_energy = sum(energy_count.values())

    def slot_pct(slot_time, kind):
        ok = 0
        total = 7
        for i in range(7):
            d = week_start + timedelta(days=i)
            r = summaries_by_date.get(str(d))
            rating = None
            if r:
                resp = _parse_responses(r.get("responses"))
                arr = resp.get(kind) or []
                for item in arr:
                    if item and item.get("time") == slot_time:
                        rating = item.get("rating")
                        break
            if rating is not None and int(rating) >= 3:
                ok += 1
        return int(round((ok / total) * 100))

    coffee = [{"label": s.get("time"), "pct": slot_pct(s.get("time"), "coffee")} for s in coffee_slots]
    meals = [{"label": s.get("time"), "pct": slot_pct(s.get("time"), "meals")} for s in meal_slots]

    if sleep_vals:
        avg_sleep = sum(sleep_vals) / len(sleep_vals)
        sleep_pct = int(round((avg_sleep / 4.0) * 100))
    else:
        sleep_pct = 0

    coffee_pcts = [c["pct"] for c in coffee] if coffee else []
    meal_pcts = [m["pct"] for m in meals] if meals else []
    avg_coffee = int(round(sum(coffee_pcts) / len(coffee_pcts))) if coffee_pcts else 0
    avg_meal = int(round(sum(meal_pcts) / len(meal_pcts))) if meal_pcts else 0

    range_label = f"{week_start.strftime('%b')} {week_start.day} – {week_end.strftime('%b')} {week_end.day}, {week_end.year}"

    report_data = {
        "range": range_label,
        "energy": energy_emojis,
        "coffee": coffee,
        "meals": meals,
        "sleepPct": sleep_pct,
        "energy_trend": _week_energy_trend(energy_numeric),
        "energy_breakdown": {
            "drained": energy_count[1],
            "low": energy_count[2],
            "ok": energy_count[3],
            "great": energy_count[4],
            "days_logged": days_with_energy,
        },
        "habits": {
            "avg_coffee_adherence_pct": avg_coffee,
            "avg_meal_adherence_pct": avg_meal,
        },
    }

    return jsonify(report_data)
