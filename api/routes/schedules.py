from flask import Blueprint, request, jsonify
from datetime import date, datetime, timedelta
import sys
import json  
sys.path.append('.')

from shared.db import supabase_client, get_user_id
from shared.schedule_utils import calculate_optimal_schedule, time_to_str, str_to_time, safe_json_parse
from shared.time_utils import get_user_now_from_timezone_name, DEFAULT_TIMEZONE

bp = Blueprint('schedules', __name__, url_prefix='/api/v1/schedules')

def get_user_from_request():
    telegram_id = request.args.get('telegram_id')
    if not telegram_id:
        return None, "telegram_id required"
    user_id = get_user_id(int(telegram_id))
    if not user_id:
        return None, "User not found"
    return user_id, None

@bp.route('/constant', methods=['GET'])
def get_constant():
    user_id, err = get_user_from_request()
    if err:
        return jsonify({"error": err}), 400
    const = supabase_client.table('constant_schedules').select('*').eq('user_id', user_id).eq('active', True).execute()
    if not const.data:
        return jsonify({"error": "No active schedule"}), 404
    schedule = const.data[0]
    # Parse JSON fields
    for field in ['coffee_windows', 'meal_windows', 'brightness_windows']:
        schedule[field] = safe_json_parse(schedule.get(field))
    return jsonify(schedule)

@bp.route('/constant', methods=['POST'])
def create_constant():
    user_id, err = get_user_from_request()
    if err:
        return jsonify({"error": err}), 400
    data = request.get_json()
    work_start = str_to_time(data.get('work_start'))
    work_end = str_to_time(data.get('work_end'))
    if not work_start or not work_end:
        return jsonify({"error": "Invalid work hours"}), 400

    # Get user timezone
    user = supabase_client.table('users').select('timezone').eq('id', user_id).execute()
    timezone = user.data[0].get('timezone') if user.data else DEFAULT_TIMEZONE

    # Calculate optimal schedule
    optimized = calculate_optimal_schedule(work_start, work_end)

    # Deactivate old active schedule
    supabase_client.table('constant_schedules').update({'active': False}).eq('user_id', user_id).eq('active', True).execute()

    # Insert new
    insert_data = {
        'user_id': user_id,
        'work_start': time_to_str(work_start),
        'work_end': time_to_str(work_end),
        'sleep_start': optimized['sleep_start'],
        'sleep_end': optimized['sleep_end'],
        'coffee_windows': optimized['coffee_windows'],
        'meal_windows': optimized['meal_windows'],
        'brightness_windows': optimized['brightness_windows'],
        'shift_type': optimized['shift_type'],
        'active': True
    }
    # Convert lists to JSON for Supabase
    for field in ['coffee_windows', 'meal_windows', 'brightness_windows']:
        insert_data[field] = json.dumps(insert_data[field])
    supabase_client.table('constant_schedules').insert(insert_data).execute()

    # Also update today's daily schedule
    today = str(date.today())
    existing = supabase_client.table('daily_schedules').select('id').eq('user_id', user_id).eq('date', today).execute()
    daily_payload = {
        'user_id': user_id,
        'date': today,
        'shift_type': optimized['shift_type'],
        'work_start': time_to_str(work_start),
        'work_end': time_to_str(work_end),
        'sleep_start': optimized['sleep_start'],
        'sleep_end': optimized['sleep_end'],
        'is_custom': False
    }
    if existing.data:
        supabase_client.table('daily_schedules').update(daily_payload).eq('id', existing.data[0]['id']).execute()
    else:
        supabase_client.table('daily_schedules').insert(daily_payload).execute()

    return jsonify({"success": True, "schedule": optimized})

@bp.route('/daily/today', methods=['GET'])
def today_daily():
    user_id, err = get_user_from_request()
    if err:
        return jsonify({"error": err}), 400
    # Get user timezone
    user = supabase_client.table('users').select('timezone').eq('id', user_id).execute()
    timezone = user.data[0].get('timezone') if user.data else DEFAULT_TIMEZONE
    today = str(get_user_now_from_timezone_name(timezone).date())

    # Check daily override
    daily = supabase_client.table('daily_schedules').select('*').eq('user_id', user_id).eq('date', today).execute()
    if daily.data:
        sched = daily.data[0]
        return jsonify(sched)

    # Fallback to constant schedule
    const = supabase_client.table('constant_schedules').select('*').eq('user_id', user_id).eq('active', True).execute()
    if not const.data:
        return jsonify({"error": "No schedule"}), 404
    sched = const.data[0]
    sched['date'] = today
    # Parse JSON fields for response
    for field in ['coffee_windows', 'meal_windows', 'brightness_windows']:
        sched[field] = safe_json_parse(sched.get(field))
    return jsonify(sched)

# ==================== NEW ENDPOINTS ====================

@bp.route('/full', methods=['GET'])
def full_schedule():
    """Get complete schedule with all windows."""
    user_id, err = get_user_from_request()
    if err:
        return jsonify({"error": err}), 400
    
    const = supabase_client.table('constant_schedules').select('*').eq('user_id', user_id).eq('active', True).execute()
    if not const.data:
        return jsonify({"error": "No schedule found"}), 404
    
    schedule = const.data[0]
    
    # Parse JSON fields
    for field in ['coffee_windows', 'meal_windows', 'brightness_windows']:
        schedule[field] = safe_json_parse(schedule.get(field))
    
    return jsonify(schedule)

@bp.route('/caffeine/check', methods=['GET'])
def caffeine_check():
    """Check if it's safe to drink coffee."""
    user_id, err = get_user_from_request()
    if err:
        return jsonify({"error": err}), 400
    
    # Get user's schedule
    const = supabase_client.table('constant_schedules').select('*').eq('user_id', user_id).eq('active', True).execute()
    if not const.data:
        return jsonify({"message": "No schedule found. Please set up your schedule first."}), 404
    
    schedule = const.data[0]
    sleep_start = schedule.get('sleep_start')
    
    if not sleep_start:
        return jsonify({"message": "Sleep time not set in schedule."}), 400
    
    # Calculate if within 6 hours of sleep
    now = datetime.now()
    
    # Parse sleep time
    sleep_time = datetime.strptime(sleep_start, "%H:%M")
    sleep_dt = datetime(now.year, now.month, now.day, sleep_time.hour, sleep_time.minute)
    
    # If sleep time is earlier than now, it's for tomorrow
    if sleep_dt <= now:
        sleep_dt = sleep_dt + timedelta(days=1)
    
    cutoff = sleep_dt - timedelta(hours=6)
    
    if now >= cutoff:
        minutes_until_sleep = int((sleep_dt - now).total_seconds() / 60)
        hours = minutes_until_sleep // 60
        mins = minutes_until_sleep % 60
        message = f"🚫 **Caffeine window closed!**\n\nYou're within 6 hours of sleep.\nSleep starts at {sleep_start} (in {hours}h {mins}m).\nCoffee now may disrupt your sleep."
    else:
        minutes_left = int((cutoff - now).total_seconds() / 60)
        hours_left = minutes_left // 60
        mins_left = minutes_left % 60
        message = f"✅ **Safe for caffeine!**\n\nYou have {hours_left}h {mins_left}m left before the 6-hour sleep window closes.\nLast call: {cutoff.strftime('%H:%M')}"
    
    return jsonify({"message": message})@bp.route('/caffeine/check', methods=['GET'])
def caffeine_check():
    """Check if it's safe to drink coffee."""
    user_id, err = get_user_from_request()
    if err:
        return jsonify({"error": err}), 400
    
    # Get user's schedule
    const = supabase_client.table('constant_schedules').select('*').eq('user_id', user_id).eq('active', True).execute()
    if not const.data:
        return jsonify({"message": "No schedule found. Please set up your schedule first."}), 404
    
    schedule = const.data[0]
    sleep_start = schedule.get('sleep_start')
    
    if not sleep_start:
        return jsonify({"message": "Sleep time not set in schedule."}), 400
    
    # Calculate if within 6 hours of sleep
    now = datetime.now()
    
    # Parse sleep time (handle string format)
    if isinstance(sleep_start, str):
        sleep_time = datetime.strptime(sleep_start[:5], "%H:%M")
    else:
        sleep_time = sleep_start
    
    sleep_dt = datetime(now.year, now.month, now.day, sleep_time.hour, sleep_time.minute)
    
    # If sleep time is earlier than now, it's for tomorrow
    if sleep_dt <= now:
        sleep_dt = sleep_dt + timedelta(days=1)
    
    cutoff = sleep_dt - timedelta(hours=6)
    
    if now >= cutoff:
        minutes_until_sleep = int((sleep_dt - now).total_seconds() / 60)
        hours = minutes_until_sleep // 60
        mins = minutes_until_sleep % 60
        message = f"🚫 **Caffeine window closed!**\n\nYou're within 6 hours of sleep.\nSleep starts at {sleep_start[:5]} (in {hours}h {mins}m).\nCoffee now may disrupt your sleep."
    else:
        minutes_left = int((cutoff - now).total_seconds() / 60)
        hours_left = minutes_left // 60
        mins_left = minutes_left % 60
        message = f"✅ **Safe for caffeine!**\n\nYou have {hours_left}h {mins_left}m left before the 6-hour sleep window closes.\nLast call: {cutoff.strftime('%H:%M')}"
    
    return jsonify({"message": message})

@bp.route('/dayoff', methods=['POST'])
def set_day_off():
    """Set today as a day off."""
    user_id, err = get_user_from_request()
    if err:
        return jsonify({"error": err}), 400
    
    data = request.get_json()
    date_str = data.get('date') if data else None
    
    if not date_str:
        # Get user timezone
        user = supabase_client.table('users').select('timezone').eq('id', user_id).execute()
        timezone = user.data[0].get('timezone') if user.data else DEFAULT_TIMEZONE
        date_str = str(get_user_now_from_timezone_name(timezone).date())
    
    # Check if daily schedule exists
    existing = supabase_client.table('daily_schedules').select('id').eq('user_id', user_id).eq('date', date_str).execute()
    
    payload = {
        'user_id': user_id,
        'date': date_str,
        'shift_type': 'off',
        'work_start': None,
        'work_end': None,
        'sleep_start': None,
        'sleep_end': None,
        'is_custom': True
    }
    
    if existing.data:
        supabase_client.table('daily_schedules').update(payload).eq('id', existing.data[0]['id']).execute()
    else:
        supabase_client.table('daily_schedules').insert(payload).execute()
    
    return jsonify({"success": True, "message": "Day off set successfully!"})