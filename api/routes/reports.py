from flask import Blueprint, request
from datetime import date, datetime, timedelta
import sys
import json

sys.path.append('.')

from shared.db import supabase_client, get_user_id
from shared.time_utils import get_user_now_from_timezone_name, DEFAULT_TIMEZONE
from shared.schedule_utils import safe_json_parse, str_to_time, time_to_str
from shared.auth import get_user_id_from_request
from shared.error_handling import success_response, APIError, validate_request_data
from shared.validation import WeeklySummaryRequest

bp = Blueprint('reports', __name__, url_prefix='/api/v1/reports')


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


def _shift_time(tstr, delta_minutes):
    t = str_to_time(tstr)
    if not t:
        return tstr
    mins = (t.hour * 60 + t.minute + delta_minutes) % (24 * 60)
    hh = mins // 60
    mm = mins % 60
    return f"{hh:02d}:{mm:02d}"


EMOJI_ENERGY = {1: '😴', 2: '😐', 3: '😊', 4: '⚡'}


@bp.route('/weekly', methods=['GET'])
@validate_request_data(WeeklySummaryRequest)
def weekly_report():
    """Generate weekly report."""
    user_id, err = get_user_id_from_request()
    if err:
        raise APIError(err, 401)
    
    validated_data = request.validated_data
    
    user = supabase_client.table('users').select('timezone').eq('id', user_id).execute()
    tz = user.data[0].get('timezone') if user.data else DEFAULT_TIMEZONE
    now_local = get_user_now_from_timezone_name(tz)
    local_today = now_local.date()

    # Use validated dates or default to current week
    if validated_data.start_date and validated_data.end_date:
        week_start = validated_data.start_date
        week_end = validated_data.end_date
    else:
        week_start = local_today - timedelta(days=local_today.weekday())
        week_end = week_start + timedelta(days=6)

    # Constant schedule gives coffee + meal "slots"
    const = (
        supabase_client.table('constant_schedules')
        .select('*')
        .eq('user_id', user_id)
        .eq('active', True)
        .execute()
    )
    if not const.data:
        raise APIError("No active schedule", 404)

    schedule = const.data[0]
    schedule['coffee_windows'] = safe_json_parse(schedule.get('coffee_windows'))
    schedule['meal_windows'] = safe_json_parse(schedule.get('meal_windows'))

    coffee_slots = (schedule.get('coffee_windows') or [])
    meal_slots = (schedule.get('meal_windows') or [])
    coffee_slots = sorted(coffee_slots, key=lambda x: _time_to_minutes(x.get('time')))
    meal_slots = sorted(meal_slots, key=lambda x: _time_to_minutes(x.get('time')))

    # Pull recorded summaries for this week
    rows = (
        supabase_client.table('shift_summaries')
        .select('local_date, energy, sleep_quality, responses')
        .eq('user_id', user_id)
        .gte('local_date', str(week_start))
        .lte('local_date', str(week_end))
        .execute()
    )
    summaries_by_date = {}
    for r in rows.data or []:
        summaries_by_date[str(r.get('local_date'))] = r

    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    energy_emojis = []

    sleep_vals = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        r = summaries_by_date.get(str(d))
        if r and r.get('energy') is not None:
            ev = int(r.get('energy'))
            energy_emojis.append(EMOJI_ENERGY.get(ev, '—'))
        else:
            energy_emojis.append('—')

        if r and r.get('sleep_quality') is not None:
            sleep_vals.append(int(r.get('sleep_quality')))

    # Helper: percentage of days where rating >= 3 (✅)
    def slot_pct(slot_time, kind):
        ok = 0
        total = 7
        for i in range(7):
            d = week_start + timedelta(days=i)
            r = summaries_by_date.get(str(d))
            rating = None
            if r:
                resp = _parse_responses(r.get('responses'))
                key = kind
                # UI saves arrays: [{time, rating}]
                arr = resp.get(key) or []
                for item in arr:
                    if item and item.get('time') == slot_time:
                        rating = item.get('rating')
                        break
            if rating is not None and int(rating) >= 3:
                ok += 1
        return int(round((ok / total) * 100))

    coffee = [{'label': s.get('time'), 'pct': slot_pct(s.get('time'), 'coffee')} for s in coffee_slots]
    meals = [{'label': s.get('time'), 'pct': slot_pct(s.get('time'), 'meals')} for s in meal_slots]

    if sleep_vals:
        avg_sleep = sum(sleep_vals) / len(sleep_vals)
        sleep_pct = int(round((avg_sleep / 4.0) * 100))
    else:
        sleep_pct = 0

    # Range label for the mini-app
    range_label = f"{week_start.strftime('%b')} {week_start.day} – {week_end.strftime('%b')} {week_end.day}, {week_end.year}"
    
    report_data = {
        "range": range_label,
        "energy": energy_emojis,
        "coffee": coffee,
        "meals": meals,
        "sleepPct": sleep_pct,
    }
    
    return success_response(report_data, "Weekly report generated")

