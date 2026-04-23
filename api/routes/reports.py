from flask import Blueprint, request, jsonify
from datetime import date, timedelta
import sys
import json

sys.path.append(".")

from shared.db import supabase_client
from shared.time_utils import get_user_now_from_timezone_name, DEFAULT_TIMEZONE
from shared.schedule_utils import safe_json_parse, str_to_time, time_to_str
from shared.insights import get_habits_effective_from_date, week_query_start
from shared.rotating_engine import build_rotating_day_from_pattern_row, pattern_includes_day_work
from api.request_util import get_user_from_request
from api.subscription_access import require_pro_access, fetch_user_row_by_id

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

    urow = fetch_user_row_by_id(user_id) or {}
    tz = urow.get("timezone") or DEFAULT_TIMEZONE
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

    eff = get_habits_effective_from_date(urow.get("notification_prefs"))
    q0 = week_query_start(week_start, eff)

    rows = (
        supabase_client.table("shift_summaries")
        .select("local_date, energy, sleep_quality, responses")
        .eq("user_id", user_id)
        .gte("local_date", str(q0))
        .lte("local_date", str(week_end))
        .execute()
    )
    summaries_by_date = {str(r.get("local_date")): r for r in (rows.data or [])}

    st = urow.get("shift_type")
    is_rot = st == "rotating"
    rpatd = None
    if is_rot:
        rpat = (
            supabase_client.table("rotating_patterns")
            .select("*")
            .eq("user_id", user_id)
            .eq("active", True)
            .limit(1)
            .execute()
        )
        if not rpat or not rpat.data:
            return jsonify({"error": "No active schedule"}), 404
        rpatd = dict(rpat.data[0])

    def _norm_t(tt):
        if not tt:
            return ""
        tc = str_to_time(str(tt)[:8])
        return time_to_str(tc) if tc else str(tt)[:5]

    def _slot_pct_rotating(slot_time, kind, pslot):
        arrk = "meals" if kind == "meals" else "coffee"
        tkey = _norm_t(slot_time)
        if not tkey or not rpatd:
            return 0
        ok = 0
        ntot = 0
        d0 = week_start
        while d0 <= week_end:
            if eff and d0 < eff:
                d0 += timedelta(days=1)
                continue
            comp = build_rotating_day_from_pattern_row(rpatd, d0)
            if not comp or comp.get("pattern_slot") != pslot or comp.get("shift_type") == "off":
                d0 += timedelta(days=1)
                continue
            wkey = "meal_windows" if kind == "meals" else "coffee_windows"
            if not any(_norm_t(w.get("time")) == tkey for w in (comp.get(wkey) or [])):
                d0 += timedelta(days=1)
                continue
            ntot += 1
            r = summaries_by_date.get(str(d0))
            good = False
            if r:
                resp = _parse_responses(r.get("responses"))
                for item in (resp.get(arrk) or []):
                    if item and _norm_t(item.get("time")) == tkey and int(item.get("rating") or 0) >= 3:
                        good = True
                        break
            if good:
                ok += 1
            d0 += timedelta(days=1)
        if ntot < 1:
            return 0
        return int(round(100.0 * ok / ntot))

    def _slot_pct_constant(slot_time, kind):
        tkey = _norm_t(slot_time)
        if not tkey:
            return 0
        ok = 0
        ntot = 0
        for i in range(7):
            d = week_start + timedelta(days=i)
            if eff and d < eff:
                continue
            ntot += 1
            r = summaries_by_date.get(str(d))
            rating = None
            if r:
                arr = _parse_responses(r.get("responses")).get("meals" if kind == "meals" else "coffee")
                for item in arr or []:
                    if item and _norm_t(item.get("time")) == tkey:
                        rating = item.get("rating")
                        break
            if rating is not None and int(rating) >= 3:
                ok += 1
        if ntot < 1:
            return 0
        return int(round(100.0 * ok / ntot))

    coffee = []
    meals = []
    if is_rot and rpatd:
        sh0 = rpatd.get("shifts") or {}
        if isinstance(sh0, str):
            sh0 = safe_json_parse(sh0) or {}
        ntpl = (sh0.get("night") or {}) if isinstance(sh0, dict) else {}
        dtpl = (sh0.get("day") or {}) if isinstance(sh0, dict) else {}
        for t in sorted(
            (safe_json_parse(ntpl.get("coffee_windows")) or ntpl.get("coffee_windows") or []),
            key=lambda x: _time_to_minutes((x or {}).get("time")),
        ):
            tt = (t or {}).get("time")
            if not tt:
                continue
            coffee.append(
                {
                    "label": f"🌙 Night · {tt}",
                    "pct": _slot_pct_rotating(tt, "coffee", "night"),
                }
            )
        if pattern_includes_day_work(
            str(sh0.get("pattern_id") or "pitman_2_2_3"), int((sh0.get("block_days") or 0) or 0), sh0
        ) and isinstance(dtpl, dict):
            for t in sorted(
                (safe_json_parse(dtpl.get("coffee_windows")) or dtpl.get("coffee_windows") or []),
                key=lambda x: _time_to_minutes((x or {}).get("time")),
            ):
                tt = (t or {}).get("time")
                if not tt:
                    continue
                coffee.append(
                    {
                        "label": f"☀️ Day · {tt}",
                        "pct": _slot_pct_rotating(tt, "coffee", "day"),
                    }
                )
        for t in sorted(
            (safe_json_parse(ntpl.get("meal_windows")) or ntpl.get("meal_windows") or []),
            key=lambda x: _time_to_minutes((x or {}).get("time")),
        ):
            tt = (t or {}).get("time")
            if not tt:
                continue
            meals.append(
                {
                    "label": f"🌙 Night · {tt}",
                    "pct": _slot_pct_rotating(tt, "meals", "night"),
                }
            )
        if pattern_includes_day_work(
            str(sh0.get("pattern_id") or "pitman_2_2_3"), int((sh0.get("block_days") or 0) or 0), sh0
        ) and isinstance(dtpl, dict):
            for t in sorted(
                (safe_json_parse(dtpl.get("meal_windows")) or dtpl.get("meal_windows") or []),
                key=lambda x: _time_to_minutes((x or {}).get("time")),
            ):
                tt = (t or {}).get("time")
                if not tt:
                    continue
                meals.append(
                    {
                        "label": f"☀️ Day · {tt}",
                        "pct": _slot_pct_rotating(tt, "meals", "day"),
                    }
                )
    else:
        const = (
            supabase_client.table("constant_schedules")
            .select("*")
            .eq("user_id", user_id)
            .eq("active", True)
            .execute()
        )
        if not const.data:
            return jsonify({"error": "No active schedule"}), 404
        schedule = dict(const.data[0])
        for f in ("coffee_windows", "meal_windows"):
            v = schedule.get(f)
            if isinstance(v, str):
                schedule[f] = safe_json_parse(v) or []
            elif v is None:
                schedule[f] = []
        coffee_slots = sorted(
            (schedule.get("coffee_windows") or []), key=lambda x: _time_to_minutes(x.get("time"))
        )
        meal_slots = sorted(
            (schedule.get("meal_windows") or []), key=lambda x: _time_to_minutes(x.get("time"))
        )
        for s in coffee_slots:
            tt = s.get("time")
            if tt:
                coffee.append({"label": str(tt), "pct": _slot_pct_constant(tt, "coffee")})
        for s in meal_slots:
            tt = s.get("time")
            if tt:
                meals.append({"label": str(tt), "pct": _slot_pct_constant(tt, "meals")})

    energy_emojis = []
    energy_numeric = [None] * 7
    sleep_vals = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        if eff and d < eff:
            energy_emojis.append("—")
            continue
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
