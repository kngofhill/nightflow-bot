"""
Habits / weekly insights: effective date after schedule-type changes, and
pre-sleep habit warnings (aligned with rotating_engine wellness heuristics).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from shared.schedule_utils import str_to_time, time_to_str, safe_json_parse

HABITS_EFFECTIVE_KEY = "habits_effective_from"
HABITS_EFFECTIVE_SHIFT_KEY = "habits_effective_shift_type"


def _prefs_as_dict(prefs: Any) -> dict:
    if prefs is None:
        return {}
    if isinstance(prefs, str):
        return safe_json_parse(prefs) or {}
    if isinstance(prefs, dict):
        return dict(prefs)
    return {}


def get_habits_effective_from_date(prefs: Any) -> Optional[date]:
    if prefs is None:
        return None
    if isinstance(prefs, str):
        prefs = safe_json_parse(prefs) or {}
    if not isinstance(prefs, dict):
        return None
    raw = prefs.get(HABITS_EFFECTIVE_KEY) or prefs.get("habitsEffectiveFrom")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def get_habits_effective_for_current_shift(
    prefs: Any, current_shift_type: str, local_today: date
) -> Optional[date]:
    """
    First date to include ``shift_summaries`` for the user's *current* schedule mode
    (``constant`` vs ``rotating``). If the stored mode in prefs does not match, only
    data from ``local_today`` onward is used (drops stale reports from a previous mode).
    """
    p = _prefs_as_dict(prefs)
    eff = get_habits_effective_from_date(p)
    stored = p.get(HABITS_EFFECTIVE_SHIFT_KEY) or p.get("habitsEffectiveShiftType")
    ct = (current_shift_type or "constant").strip() or "constant"
    if eff is None:
        return None
    if not stored or str(stored).strip() == "":
        return eff
    if str(stored).strip() == ct:
        return eff
    return local_today


def week_query_start(week_start: date, eff: Optional[date]) -> date:
    if eff is None:
        return week_start
    return max(week_start, eff)


def _m(t) -> int:
    return t.hour * 60 + t.minute


def _add_minutes_hhmm(tstr: str, delta_minutes: int) -> str:
    t = str_to_time(tstr)
    if not t:
        return tstr
    base = datetime.combine(date.today(), t) + timedelta(minutes=delta_minutes)
    return time_to_str(base.time())


def _d_before_bed(event_m: int, slpm: int) -> int:
    return (slpm - event_m) % 1440


def build_bad_habit_suggestion_items(
    sleep_start: Optional[str],
    coffee_windows: list,
    meal_windows: list,
    brightness_windows: list,
    template: Optional[str] = None,
) -> List[dict]:
    """
    Heuristics (same idea as _wellness_suggestions_for_day):
    - coffee: within 5h before bed
    - meal: within 3h
    - brightness: within 2h
    template: 'night' | 'day' | None — passed through to /suggestions/apply for rotating.
    """
    slp = str_to_time((sleep_start or "22:00")[:8])
    if not slp:
        return []
    slpm = _m(slp)
    tlabel = f"🌙 Night · " if template == "night" else f"☀️ Day · " if template == "day" else ""
    out: List[dict] = []

    for w in coffee_windows or []:
        raw_t = (w or {}).get("time")
        t = str_to_time(str(raw_t or "12:00")[:8]) if raw_t is not None else None
        if not t:
            continue
        cm = _m(t)
        d = _d_before_bed(cm, slpm)
        if 0 < d <= 5 * 60:
            ts = time_to_str(t)
            to_t = _add_minutes_hhmm(ts, -60)
            it = {
                "title": f"☕ {tlabel}Coffee may be too close to sleep",
                "body": f"Last cup at {ts} is within 5h of bedtime on this template — that can break rest for some people.",
                "action": f"Nudge to {to_t} (or edit in Settings).",
                "apply": {
                    "op": "shift_coffee",
                    "from": ts,
                    "to": to_t,
                },
            }
            if template:
                it["apply"]["template"] = template
            out.append(it)
            break

    for w in meal_windows or []:
        raw_t = (w or {}).get("time")
        t = str_to_time(str(raw_t or "20:00")[:8]) if raw_t is not None else None
        if not t:
            continue
        mm = _m(t)
        d2 = _d_before_bed(mm, slpm)
        if 0 < d2 <= 3 * 60:
            ts = time_to_str(t)
            to_t = _add_minutes_hhmm(ts, -30)
            it = {
                "title": f"🍽 {tlabel}Meal may be too close to sleep",
                "body": f"Eating at {ts} is within 3h of bed — a lighter/earlier last meal on this pattern may help.",
                "action": f"Nudge to {to_t} (or edit in Settings).",
                "apply": {
                    "op": "shift_meal",
                    "from": ts,
                    "to": to_t,
                },
            }
            if template:
                it["apply"]["template"] = template
            out.append(it)
            break

    for w in brightness_windows or []:
        raw_t = (w or {}).get("time")
        t = str_to_time(str(raw_t or "21:00")[:8]) if raw_t is not None else None
        if not t:
            continue
        bm = _m(t)
        d3 = _d_before_bed(bm, slpm)
        if 0 < d3 <= 2 * 60:
            ts = time_to_str(t)
            to_t = _add_minutes_hhmm(ts, -30)
            it = {
                "title": f"💡 {tlabel}Light may be too close to bed",
                "body": f"Brightness at {ts} is right before you lie down — your eyes will thank you for a dimmer cue earlier.",
                "action": f"Nudge to {to_t} (or edit in Settings).",
                "apply": {
                    "op": "shift_bright",
                    "from": ts,
                    "to": to_t,
                },
            }
            if template:
                it["apply"]["template"] = template
            out.append(it)
            break

    return out
