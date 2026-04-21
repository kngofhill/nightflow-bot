from flask import Blueprint, request, jsonify
from datetime import date
import sys
import json

sys.path.append(".")

from shared.db import supabase_client
from shared.time_utils import get_user_now_from_timezone_name, DEFAULT_TIMEZONE
from api.request_util import get_user_from_request
from api.subscription_access import require_pro_access

bp = Blueprint("summaries", __name__, url_prefix="/api/v1")


def _parse_json_or_obj(v, default):
    if v is None:
        return default
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return default
    if isinstance(v, dict):
        return v
    return default


@bp.route("/summaries", methods=["POST"])
def post_shift_summary():
    user_id, err = get_user_from_request()
    if err:
        return err

    denied = require_pro_access(user_id)
    if denied:
        return denied

    payload = request.get_json(silent=True) or {}

    date_str = payload.get("date") or payload.get("local_date")
    if not date_str:
        user = supabase_client.table("users").select("timezone").eq("id", user_id).execute()
        tz = user.data[0].get("timezone") if user.data else DEFAULT_TIMEZONE
        date_str = str(get_user_now_from_timezone_name(tz).date())

    try:
        local_date = date.fromisoformat(str(date_str))
        local_date_str = str(local_date)
    except Exception:
        return jsonify({"error": "Invalid date; expected YYYY-MM-DD"}), 400

    energy = payload.get("energy")
    sleep_quality = payload.get("sleep_quality")
    responses = _parse_json_or_obj(payload.get("responses"), default={})

    existing = (
        supabase_client.table("shift_summaries")
        .select("id")
        .eq("user_id", user_id)
        .eq("local_date", local_date_str)
        .execute()
    )

    row_payload = {
        "user_id": user_id,
        "local_date": local_date_str,
        "energy": energy,
        "sleep_quality": sleep_quality,
        "responses": responses,
    }

    if existing.data:
        supabase_client.table("shift_summaries").update(row_payload).eq("id", existing.data[0]["id"]).execute()
    else:
        supabase_client.table("shift_summaries").insert(row_payload).execute()

    return jsonify({"ok": True, "message": "Summary saved successfully"})


def _as_bool(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(int(v))
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return None


def _as_int(v, default=None):
    if v is None or v == "":
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _norm_time_str(v):
    if not v:
        return None
    s = str(v).strip()
    if not s:
        return None
    parts = s.split(":")
    if len(parts) >= 2:
        h = int(parts[0])
        m = int(parts[1])
        return f"{h:02d}:{m:02d}:00"
    return None


def _pick(body, *keys):
    for k in keys:
        if k in body and body[k] is not None:
            return body[k]
    return None


@bp.route("/summaries/detailed", methods=["POST"])
def post_shift_detailed():
    user_id, err = get_user_from_request()
    if err:
        return err

    denied = require_pro_access(user_id)
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    date_str = _pick(body, "date", "local_date")
    if not date_str:
        user = supabase_client.table("users").select("timezone").eq("id", user_id).execute()
        tz = user.data[0].get("timezone") if user.data else DEFAULT_TIMEZONE
        date_str = str(get_user_now_from_timezone_name(tz).date())

    try:
        local_date_str = str(date.fromisoformat(str(date_str)))
    except Exception:
        return jsonify({"error": "Invalid date; expected YYYY-MM-DD"}), 400

    night_wakings = _as_int(_pick(body, "night_wakings", "nightWakings"), 0)
    if night_wakings is None:
        night_wakings = 0
    night_wakings = max(0, min(99, night_wakings))

    screens_yes = _as_bool(_pick(body, "screens_before_bed", "screensBeforeBed"))
    screens_minutes = _as_int(_pick(body, "screens_minutes", "screensMinutes"), None)
    if screens_yes is False:
        screens_minutes = None
    elif screens_yes is True and screens_minutes is None:
        screens_minutes = 0

    stress_yes = _as_bool(_pick(body, "stress", "stressUnusual"))
    stress_note = _pick(body, "stress_note", "stressNote")
    if not stress_yes:
        stress_note = None
    elif stress_note is not None:
        stress_note = str(stress_note).strip()[:2000] or None

    cups = _as_int(_pick(body, "caffeine_cups", "caffeineCups"), 0)
    if cups is not None:
        cups = max(0, min(4, cups))

    row_payload = {
        "user_id": user_id,
        "local_date": local_date_str,
        "bed_time": _norm_time_str(_pick(body, "bed_time", "bedTime")),
        "wake_time": _norm_time_str(_pick(body, "wake_time", "wakeTime")),
        "sleep_latency": _pick(body, "sleep_latency", "sleepLatency"),
        "night_wakings": night_wakings,
        "room_darkness": _pick(body, "room_darkness", "roomDarkness"),
        "temperature": _pick(body, "temperature", "temperatureFeel"),
        "caffeine_cups": cups,
        "last_caffeine_time": _norm_time_str(_pick(body, "last_caffeine_time", "lastCaffeineTime")),
        "caffeine_after_6pm": _as_bool(_pick(body, "caffeine_after_6pm", "caffeineAfter6pm")),
        "screens_before_bed": screens_yes,
        "screens_minutes": screens_minutes,
        "bright_light_morning": _as_bool(_pick(body, "bright_light_morning", "brightLightMorning")),
        "dim_lights_before_sleep": _as_bool(_pick(body, "dim_lights_before_sleep", "dimLightsBeforeSleep")),
        "last_meal_time": _norm_time_str(_pick(body, "last_meal_time", "lastMealTime")),
        "ate_near_bedtime": _as_bool(_pick(body, "ate_near_bedtime", "ateNearBedtime")),
        "hungry_during_sleep": _as_bool(_pick(body, "hungry_during_sleep", "hungryDuringSleep")),
        "tired_at": _norm_time_str(_pick(body, "tired_at", "tiredAt")),
        "took_breaks": _as_bool(_pick(body, "took_breaks", "tookBreaks")),
        "stress": stress_yes,
        "stress_note": stress_note,
    }

    existing = (
        supabase_client.table("shift_details")
        .select("id")
        .eq("user_id", user_id)
        .eq("local_date", local_date_str)
        .execute()
    )

    if existing.data:
        upd = {k: v for k, v in row_payload.items() if k not in ("user_id", "local_date")}
        supabase_client.table("shift_details").update(upd).eq("id", existing.data[0]["id"]).execute()
    else:
        supabase_client.table("shift_details").insert(row_payload).execute()

    return jsonify({"ok": True, "message": "Detailed log saved"})
