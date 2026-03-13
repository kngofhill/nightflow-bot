import json
from datetime import datetime, time, timedelta, date
from typing import Dict, Any, Optional, Union


def str_to_time(time_str: str) -> Optional[time]:
    try:
        if not time_str:
            return None

        value = str(time_str).strip()

        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                return datetime.strptime(value, fmt).time()
            except ValueError:
                continue

        return None
    except Exception:
        return None


def time_to_str(t: Union[time, str]) -> str:
    if isinstance(t, time):
        return t.strftime("%H:%M")

    if isinstance(t, str):
        parsed = str_to_time(t)
        if parsed:
            return parsed.strftime("%H:%M")
        return t

    return str(t)


def safe_json_parse(data: Any) -> Any:
    if data is None:
        return []
    if isinstance(data, str):
        try:
            return json.loads(data)
        except Exception:
            return []
    return data


def calculate_optimal_schedule(work_start: time, work_end: time) -> Dict[str, Any]:
    today = date.today()
    work_start_dt = datetime.combine(today, work_start)
    work_end_dt = datetime.combine(today, work_end)

    if work_end_dt <= work_start_dt:
        work_end_dt += timedelta(days=1)

    if work_start.hour >= 20 or work_start.hour <= 4:
        shift_type = "night"
    elif 12 <= work_start.hour < 20:
        shift_type = "evening"
    else:
        shift_type = "day"

    if shift_type == "night":
        sleep_start = work_end_dt.time()
        wake_dt = work_start_dt - timedelta(hours=1, minutes=30)
        sleep_end = wake_dt.time()
    elif shift_type == "evening":
        sleep_start = time(2, 0)
        sleep_end = time(10, 0)
    else:
        sleep_start = time(22, 0)
        sleep_end = time(6, 0)

    coffee_windows = []
    pre_work_coffee = work_start_dt - timedelta(minutes=30)
    coffee_windows.append({
        "time": pre_work_coffee.strftime("%H:%M"),
        "message": "☕ Pre-shift coffee. Perfect timing to start alert.",
        "type": "pre_work"
    })

    mid_coffee = work_start_dt + timedelta(hours=3, minutes=30)
    coffee_windows.append({
        "time": mid_coffee.strftime("%H:%M"),
        "message": "☕ Mid-shift boost. You're halfway there.",
        "type": "mid_shift"
    })

    meal_windows = []
    pre_meal = work_start_dt - timedelta(hours=1, minutes=30)
    meal_windows.append({
        "time": pre_meal.strftime("%H:%M"),
        "message": "🍽️ Pre-shift meal. Protein + complex carbs for steady energy.",
        "type": "pre_work"
    })

    mid_meal = work_start_dt + timedelta(hours=4)
    meal_windows.append({
        "time": mid_meal.strftime("%H:%M"),
        "message": "🥗 Mid-shift fuel. Avoid heavy/greasy food.",
        "type": "mid_shift"
    })

    post_meal = work_end_dt
    meal_windows.append({
        "time": post_meal.strftime("%H:%M"),
        "message": "🍌 Post-shift snack. Light before sleep. Banana is perfect.",
        "type": "post_work"
    })

    brightness_windows = []
    pre_bright = work_start_dt - timedelta(minutes=15)
    brightness_windows.append({
        "time": pre_bright.strftime("%H:%M"),
        "message": "☀️ Bright light time. Tell your brain: wake up!",
        "type": "bright",
        "action": "increase_light"
    })

    sleep_start_dt = datetime.combine(today, sleep_start)
    if sleep_start_dt <= work_end_dt and shift_type == "night":
        sleep_start_dt += timedelta(days=1)

    dim_time = sleep_start_dt - timedelta(hours=2)
    brightness_windows.append({
        "time": dim_time.strftime("%H:%M"),
        "message": "🌙 Time to dim lights. Tell your brain: sleep is coming.",
        "type": "dim",
        "action": "dim_lights"
    })

    no_screens = sleep_start_dt - timedelta(minutes=30)
    brightness_windows.append({
        "time": no_screens.strftime("%H:%M"),
        "message": "📵 30 min until sleep. Put devices away. Read a book.",
        "type": "no_screens",
        "action": "no_screens"
    })

    if shift_type == "night":
        commute_time = work_end_dt + timedelta(minutes=30)
        brightness_windows.append({
            "time": commute_time.strftime("%H:%M"),
            "message": "🕶️ On the way home? Wear sunglasses. Blue light blockers help.",
            "type": "blue_block",
            "action": "wear_sunglasses"
        })

    return {
        "sleep_start": time_to_str(sleep_start),
        "sleep_end": time_to_str(sleep_end),
        "coffee_windows": coffee_windows,
        "meal_windows": meal_windows,
        "brightness_windows": brightness_windows,
        "shift_type": shift_type
    }


def is_within_caffeine_window(sleep_start: time, current_time: time) -> bool:
    sleep_start_dt = datetime.combine(date.today(), sleep_start)
    current_dt = datetime.combine(date.today(), current_time)

    if sleep_start_dt <= current_dt:
        sleep_start_dt += timedelta(days=1)

    cutoff_dt = sleep_start_dt - timedelta(hours=6)
    return current_dt >= cutoff_dt


def generate_transition_advice(old_work_start: time, old_work_end: time,
                               new_work_start: time, new_work_end: time,
                               days_until_change: int) -> str:
    old_start_dt = datetime.combine(date.today(), old_work_start)
    new_start_dt = datetime.combine(date.today(), new_work_start)

    if new_start_dt <= old_start_dt:
        new_start_dt += timedelta(days=1)

    hours_diff = (new_start_dt - old_start_dt).total_seconds() / 3600

    advice = f"🔄 **Shift Change Preparation**\n\n"
    advice += f"Moving from {time_to_str(old_work_start)}-{time_to_str(old_work_end)} "
    advice += f"to {time_to_str(new_work_start)}-{time_to_str(new_work_end)}\n\n"

    if hours_diff > 0:
        advice += f"Your new shift starts {hours_diff:.1f} hours later.\n\n"

        if hours_diff <= 3:
            advice += "✅ Small adjustment. Stay up a bit later each night."
        elif hours_diff <= 6:
            advice += "⚡ Medium shift. Consider a split sleep schedule:\n"
            advice += "• Nap 3-4 hours before first new shift\n"
            advice += "• Then sleep 4-5 hours after shift"
        else:
            advice += "⚠️ Large shift change. This will take a few days to adjust:\n"
            advice += "• Day 1: Stay up 2 hours later than usual\n"
            advice += "• Day 2: Stay up 4 hours later\n"
            advice += "• Day 3: Full adjustment"
    else:
        advice += f"Your new shift starts {abs(hours_diff):.1f} hours earlier.\n\n"
        advice += "Early transition strategy:\n"
        advice += "• Go to bed earlier each night\n"
        advice += "• Get bright light exposure immediately upon waking\n"
        advice += "• Avoid caffeine 6 hours before new bedtime"

    advice += "\n\nI'll send you daily transition reminders."
    return advice