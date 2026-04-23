import json
from datetime import datetime, time, timedelta, date
from typing import Any, Dict, List, Optional, Union

from shared.miniapp_i18n import mt, norm_lang


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


def classify_shift_type_from_work_start(work_start: time) -> str:
    """
    Heuristic from clock-in: night shift usually starts 19:00+ or early morning; afternoon 12-18:59 is "evening".
    """
    h = work_start.hour
    if h >= 19 or h <= 4:
        return "night"
    if 12 <= h < 19:
        return "evening"
    return "day"


def calculate_optimal_schedule(
    work_start: time,
    work_end: time,
    sleep_start_override: Optional[time] = None,
    sleep_end_override: Optional[time] = None,
    lang: str = "en",
) -> Dict[str, Any]:
    lang = norm_lang(lang)
    today = date.today()
    work_start_dt = datetime.combine(today, work_start)
    work_end_dt = datetime.combine(today, work_end)

    if work_end_dt <= work_start_dt:
        work_end_dt += timedelta(days=1)

    shift_type = classify_shift_type_from_work_start(work_start)

    if sleep_start_override and sleep_end_override:
        sleep_start = sleep_start_override
        sleep_end = sleep_end_override
    elif shift_type == "night":
        # Wind-down after shift, then 8h sleep (Nightflow spec)
        sleep_start_dt = work_end_dt + timedelta(hours=2)
        sleep_end_dt = sleep_start_dt + timedelta(hours=8)
        sleep_start = sleep_start_dt.time()
        sleep_end = sleep_end_dt.time()
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
        "message": mt("calc_coffee_pre", lang),
        "type": "pre_work"
    })

    mid_coffee = work_start_dt + timedelta(hours=3, minutes=30)
    coffee_windows.append({
        "time": mid_coffee.strftime("%H:%M"),
        "message": mt("calc_coffee_mid", lang),
        "type": "mid_shift"
    })

    meal_windows = []
    pre_meal = work_start_dt - timedelta(hours=1, minutes=30)
    meal_windows.append({
        "time": pre_meal.strftime("%H:%M"),
        "message": mt("calc_meal_pre", lang),
        "type": "pre_work"
    })

    mid_meal = work_start_dt + timedelta(hours=4)
    meal_windows.append({
        "time": mid_meal.strftime("%H:%M"),
        "message": mt("calc_meal_mid", lang),
        "type": "mid_shift"
    })

    post_meal = work_end_dt
    meal_windows.append({
        "time": post_meal.strftime("%H:%M"),
        "message": mt("calc_meal_post", lang),
        "type": "post_work"
    })

    brightness_windows = []
    pre_bright = work_start_dt - timedelta(minutes=15)
    brightness_windows.append({
        "time": pre_bright.strftime("%H:%M"),
        "message": mt("calc_bright", lang),
        "type": "bright",
        "action": "increase_light"
    })

    if shift_type == "night":
        sleep_start_dt = work_end_dt + timedelta(hours=2)
        if sleep_start_override and sleep_end_override:
            sd = datetime.combine(work_end_dt.date(), sleep_start_override)
            if sd <= work_end_dt:
                sd += timedelta(days=1)
            sleep_start_dt = sd
    else:
        sleep_start_dt = datetime.combine(today, sleep_start)

    dim_time = sleep_start_dt - timedelta(hours=2)
    brightness_windows.append({
        "time": dim_time.strftime("%H:%M"),
        "message": mt("calc_dim", lang),
        "type": "dim",
        "action": "dim_lights"
    })

    no_screens = sleep_start_dt - timedelta(minutes=30)
    brightness_windows.append({
        "time": no_screens.strftime("%H:%M"),
        "message": mt("calc_screens", lang),
        "type": "no_screens",
        "action": "no_screens"
    })

    if shift_type == "night":
        commute_time = work_end_dt + timedelta(minutes=30)
        brightness_windows.append({
            "time": commute_time.strftime("%H:%M"),
            "message": mt("calc_commute", lang),
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


def rest_day_habit_windows(sleep_start_str: str, sleep_end_str: str, lang: str = "en") -> Dict[str, List[Dict[str, Any]]]:
    lang = norm_lang(lang)
    """
    Gentle coffee / meal / light suggestions for a rest (off) day, anchored to the
    recommended main sleep window only (no work times).
    """
    ss = str_to_time(str(sleep_start_str or "")[:8]) or time(22, 0)
    se = str_to_time(str(sleep_end_str or "")[:8]) or time(6, 0)
    d0 = date(2020, 1, 1)
    bed = datetime.combine(d0, ss)
    wake = datetime.combine(d0, se)
    if wake <= bed:
        wake += timedelta(days=1)
    awake_start = wake
    awake_end = bed + timedelta(days=1)
    span_h = max(0.0, (awake_end - awake_start).total_seconds() / 3600.0)

    def _t(dt: datetime) -> str:
        return dt.strftime("%H:%M")

    coffee: List[Dict[str, Any]] = []
    meals: List[Dict[str, Any]] = []
    bright: List[Dict[str, Any]] = []

    last_caffeine = awake_end - timedelta(hours=8)
    c1: Optional[datetime] = None
    if span_h >= 2.5:
        c1 = awake_start + timedelta(hours=1, minutes=30)
        if c1 < last_caffeine - timedelta(minutes=30):
            coffee.append(
                {
                    "time": _t(c1),
                    "message": mt("rest_coffee1", lang),
                    "type": "rest_day",
                }
            )
        if span_h >= 7 and c1 is not None:
            c2 = awake_start + timedelta(hours=5)
            if c2 < last_caffeine - timedelta(hours=1) and c2 > c1 + timedelta(hours=2):
                coffee.append(
                    {
                        "time": _t(c2),
                        "message": mt("rest_coffee2", lang),
                        "type": "rest_day",
                    }
                )

    m1_dt: Optional[datetime] = None
    if span_h >= 3:
        m1_dt = awake_start + timedelta(hours=1)
        meals.append(
            {
                "time": _t(m1_dt),
                "message": mt("rest_meal1", lang),
                "type": "rest_day",
            }
        )
    if span_h >= 8 and m1_dt is not None:
        m2 = awake_start + timedelta(hours=span_h / 2)
        if m2 > m1_dt + timedelta(hours=3) and m2 < awake_end - timedelta(hours=4):
            meals.append(
                {
                    "time": _t(m2),
                    "message": mt("rest_meal2", lang),
                    "type": "rest_day",
                }
            )
    if span_h >= 5:
        m3 = awake_end - timedelta(hours=4)
        ok = True
        if m1_dt is not None and m3 <= m1_dt + timedelta(hours=2):
            ok = False
        if ok and m3 < awake_end - timedelta(hours=2) and m3 > awake_start:
            meals.append(
                {
                    "time": _t(m3),
                    "message": mt("rest_meal3", lang),
                    "type": "rest_day",
                }
            )

    if span_h >= 1.5:
        bright.append(
            {
                "time": _t(awake_start + timedelta(minutes=20)),
                "message": mt("rest_bl_bright", lang),
                "type": "bright",
                "action": "increase_light",
            }
        )
        dim = awake_end - timedelta(hours=2)
        if dim > awake_start + timedelta(hours=1):
            bright.append(
                {
                    "time": _t(dim),
                    "message": mt("rest_bl_dim", lang),
                    "type": "dim",
                    "action": "dim_lights",
                }
            )
        ns = awake_end - timedelta(minutes=30)
        if ns > awake_start + timedelta(hours=2):
            bright.append(
                {
                    "time": _t(ns),
                    "message": mt("rest_bl_ns", lang),
                    "type": "no_screens",
                    "action": "no_screens",
                }
            )

    return {"coffee_windows": coffee, "meal_windows": meals, "brightness_windows": bright}


def is_within_caffeine_window(sleep_start: time, current_time: time) -> bool:
    sleep_start_dt = datetime.combine(date.today(), sleep_start)
    current_dt = datetime.combine(date.today(), current_time)

    if sleep_start_dt <= current_dt:
        sleep_start_dt += timedelta(days=1)

    cutoff_dt = sleep_start_dt - timedelta(hours=6)
    return current_dt >= cutoff_dt


def generate_transition_advice(
    old_work_start: time,
    old_work_end: time,
    new_work_start: time,
    new_work_end: time,
    days_until_change: int,
    lang: str = "en",
) -> str:
    lang = norm_lang(lang)
    old_start_dt = datetime.combine(date.today(), old_work_start)
    new_start_dt = datetime.combine(date.today(), new_work_start)

    if new_start_dt <= old_start_dt:
        new_start_dt += timedelta(days=1)

    hours_diff = (new_start_dt - old_start_dt).total_seconds() / 3600

    o1, o2 = time_to_str(old_work_start), time_to_str(old_work_end)
    n1, n2 = time_to_str(new_work_start), time_to_str(new_work_end)
    advice = mt("tr_adv_head", lang) + "\n\n"
    advice += mt("tr_adv_line", lang, o1=o1, o2=o2, n1=n1, n2=n2) + "\n\n"

    if hours_diff > 0:
        advice += mt("tr_adv_late_h", lang, h=hours_diff) + "\n\n"

        if hours_diff <= 3:
            advice += mt("tr_adv_small", lang)
        elif hours_diff <= 6:
            advice += mt("tr_adv_medium", lang)
        else:
            advice += mt("tr_adv_large", lang)
    else:
        advice += mt("tr_adv_early_h", lang, h=abs(hours_diff)) + "\n\n"
        advice += mt("tr_adv_early_s", lang)

    advice += "\n\n" + mt("tr_adv_foot", lang)
    return advice