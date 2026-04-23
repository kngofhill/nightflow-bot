"""
Rotating shift patterns: resolve a calendar date to daily schedule (work, sleep, windows) + advice.

Pattern IDs: pitman_2_2_3 | block_rotation | pat_4n4o4d4o | pat_4n4o
"""

from __future__ import annotations

import json
from datetime import date, time
from typing import Any, Dict, List, Optional, Tuple

from shared.schedule_utils import (
    calculate_optimal_schedule,
    rest_day_habit_windows,
    safe_json_parse,
    str_to_time,
    time_to_str,
)

PITMAN_2_2_3: List[str] = [
    "night", "night", "off", "off", "night", "night", "night",
    "day", "day", "off", "off", "day", "day", "day",
]
PAT_4N4O4D4O: List[str] = ["night"] * 4 + ["off"] * 4 + ["day"] * 4 + ["off"] * 4
PAT_4N4O: List[str] = ["night"] * 4 + ["off"] * 4

DAY_SHIPPED_PATTERNS = frozenset(
    {
        "pitman_2_2_3",
        "block_rotation",
        "pat_4n4o4d4o",
    }
)


def _idx(start: date, d: date) -> int:
    return (d - start).days if d >= start else -1


def _next_work(seq: List[str], i: int) -> str:
    n = len(seq)
    for k in range(1, n + 1):
        s = seq[(i + k) % n]
        if s != "off":
            return s
    return "off"


def _seq_for(pattern_id: str) -> Optional[List[str]]:
    if pattern_id == "pitman_2_2_3":
        return PITMAN_2_2_3
    if pattern_id == "pat_4n4o4d4o":
        return PAT_4N4O4D4O
    if pattern_id == "pat_4n4o":
        return PAT_4N4O
    return None


def resolve_slot_in_cycle(
    pattern_id: str,
    start: date,
    d: date,
    block_nights: int = 14,
    block_days: int = 14,
    block_off: int = 0,
) -> Tuple[str, int, int]:
    i = _idx(start, d)
    if i < 0:
        return "off", 0, 1
    if pattern_id == "block_rotation":
        n, m, o = max(0, int(block_nights)), max(0, int(block_days)), max(0, int(block_off))
        c = n + m + o
        if c <= 0:
            return "off", 0, 1
        pos = i % c
        if pos < n:
            return "night", pos, c
        if pos < n + m:
            return "day", pos, c
        return "off", pos, c
    seq = _seq_for(pattern_id)
    if not seq:
        return "off", 0, 1
    c = len(seq)
    return seq[i % c], i % c, c


def _t(s: str, default: str = "07:00") -> str:
    x = str(s or default)[:5]
    return x if str_to_time(x) else default


def _to_time(s: str) -> Optional[time]:
    t = str_to_time(_t(s, "12:00"))
    return t


def _min_of_day(t: time) -> int:
    return t.hour * 60 + t.minute


def _wellness_suggestions_for_day(row: Dict[str, Any]) -> List[str]:
    """Non-blocking hints when user custom times look risky (normal days only)."""
    out: List[str] = []
    slp = str_to_time(_t(row.get("sleep_start") or "", "22:00"))
    if not slp:
        return out
    slpm = _min_of_day(slp)
    for w in row.get("coffee_windows") or []:
        t = str_to_time(str((w or {}).get("time", "12:00"))[:8])
        if not t:
            continue
        cm = _min_of_day(t)
        # crude "within 5h before bed" on same 24h line
        d = (slpm - cm) % 1440
        if 0 < d <= 5 * 60:
            out.append("Coffee very close to bedtime can fragment sleep — consider an earlier last cup on rest days.")
            break
    for w in row.get("meal_windows") or []:
        t = str_to_time(str((w or {}).get("time", "20:00"))[:8])
        if not t:
            continue
        mm = _min_of_day(t)
        d2 = (slpm - mm) % 1440
        if 0 < d2 <= 3 * 60:
            out.append("Heavy eating right before bed can feel uncomfortable — a lighter last meal may help on regular days.")
            break
    for w in row.get("brightness_windows") or []:
        t = str_to_time(str((w or {}).get("time", "21:00"))[:8])
        if not t:
            continue
        bm = _min_of_day(t)
        d3 = (slpm - bm) % 1440
        if 0 < d3 <= 2 * 60:
            out.append("Very bright light minutes before you lie down can delay melatonin — this is a gentle heads-up, not a rule change.")
            break
    return out


def _work_day(
    d: date,
    slot: str,
    wsa: str,
    web: str,
    sso: Optional[str],
    seo: Optional[str],
    advice: Optional[str],
    template: Optional[Dict[str, Any]] = None,
    is_transition: bool = False,
) -> Dict[str, Any]:
    ws, we = _to_time(wsa), _to_time(web)
    if not ws or not we:
        return _off_style(d, "08:00", "16:00", advice, [], [], [])
    s_s = str_to_time(_t(sso, "22:00")) if sso else None
    s_e = str_to_time(_t(seo, "06:00")) if seo else None
    if s_s and s_e and not (sso and seo):
        s_s, s_e = None, None
    if s_s is None and sso:
        s_s = str_to_time(_t(sso, "22:00"))
    if s_e is None and seo:
        s_e = str_to_time(_t(seo, "06:00"))
    opt = calculate_optimal_schedule(ws, we, s_s, s_e)
    st = opt.get("shift_type", "night" if slot == "night" else "day")
    for k in ("coffee_windows", "meal_windows", "brightness_windows"):
        v = opt.get(k)
        if not isinstance(v, list):
            v = safe_json_parse(v) or []
        opt[k] = v
    ss = opt.get("sleep_start")
    se_ = opt.get("sleep_end")
    coffee: List = list(opt.get("coffee_windows", []) or [])
    meal: List = list(opt.get("meal_windows", []) or [])
    bright: List = list(opt.get("brightness_windows", []) or [])

    tpl = template or {}
    if not is_transition:
        for k, default in (("coffee_windows", coffee), ("meal_windows", meal), ("brightness_windows", bright)):
            cus = tpl.get(k)
            if isinstance(cus, list) and len(cus) > 0:
                if k == "coffee_windows":
                    coffee = cus
                elif k == "meal_windows":
                    meal = cus
                else:
                    bright = cus
    wellness: List[str] = []
    if not is_transition and tpl:
        wellness = _wellness_suggestions_for_day(
            {
                "sleep_start": time_to_str(ss) if ss is not None else None,
                "coffee_windows": coffee,
                "meal_windows": meal,
                "brightness_windows": bright,
            }
        )

    row = {
        "date": str(d),
        "shift_type": st if st in ("day", "night", "evening") else ("night" if slot == "night" else "day"),
        "work_start": _t(wsa, "07:00"),
        "work_end": _t(web, "19:00"),
        "sleep_start": time_to_str(ss) if ss is not None else None,
        "sleep_end": time_to_str(se_) if se_ is not None else None,
        "is_custom": False,
        "coffee_windows": coffee,
        "meal_windows": meal,
        "brightness_windows": bright,
        "transition_advice": advice,
        "is_transition_day": is_transition,
    }
    if is_transition:
        row["reminders_locked"] = "Transition day: coffee / meal / light use the system plan so sleep timing stays consistent."
    if wellness:
        row["wellness_suggestions"] = wellness
    return row


def _off_style(
    d: date,
    sl: str,
    se: str,
    advice: Optional[str],
    coffee: List,
    meal: List,
    bright: List,
) -> Dict[str, Any]:
    return {
        "date": str(d),
        "shift_type": "off",
        "work_start": None,
        "work_end": None,
        "sleep_start": _t(sl, "22:00"),
        "sleep_end": _t(se, "06:00"),
        "is_custom": False,
        "coffee_windows": coffee,
        "meal_windows": meal,
        "brightness_windows": bright,
        "transition_advice": advice,
    }


def build_rotating_day(
    pattern_id: str,
    start: date,
    d: date,
    night: Dict[str, Any],
    day: Optional[Dict[str, Any]],
    block_nights: int = 14,
    block_days: int = 14,
    block_off: int = 0,
) -> Dict[str, Any]:
    n = night or {}
    d_pl = day or {}
    wn = (_t(n.get("work_start", "19:00"), "19:00"), _t(n.get("work_end", "07:00"), "07:00"))
    wd = (_t(d_pl.get("work_start", "07:00"), "07:00"), _t(d_pl.get("work_end", "19:00"), "19:00"))
    n_ss = n.get("sleep_start")
    n_se = n.get("sleep_end")
    d_ss, d_se = d_pl.get("sleep_start"), d_pl.get("sleep_end")

    slot, index, _cyc = resolve_slot_in_cycle(
        pattern_id, start, d, block_nights, block_days, block_off
    )
    out_meta = {
        "pattern_id": pattern_id,
        "pattern_index": index,
        "pattern_slot": slot,
    }
    if slot == "night":
        adv: Optional[str] = None
        sso, seo = n_ss, n_se
        n_b, m_b = int(block_nights), int(block_days)
        n_tr = (pattern_id == "pitman_2_2_3" and index == 6) or (
            pattern_id == "block_rotation" and m_b > 0 and n_b > 0 and index == n_b - 1
        )
        if pattern_id == "pitman_2_2_3" and index == 6:
            sso, seo = "08:00", "12:00"
            adv = "Night → day: short 4h sleep (08:00–12:00), then stay awake until ~22:00 before day block."
        if pattern_id == "block_rotation" and m_b > 0 and n_b > 0 and index == n_b - 1:
            sso, seo = "08:00", "12:00"
            adv = (adv or "")
            adv = adv + " End of night block: short 4h sleep, then stay awake until first day-sleep (≈22:00)."
        base = _work_day(
            d, "night", wn[0], wn[1], sso, seo, adv.strip() if adv else None, template=n, is_transition=n_tr
        )
        base.update(out_meta)
        return base

    if slot == "day":
        adv2: Optional[str] = None
        sso, seo = d_ss, d_se
        d_tr = (pattern_id == "pitman_2_2_3" and index == 13)
        if pattern_id == "pitman_2_2_3" and index == 13:
            adv2 = "Day → night: take a 4h nap 14:00–18:00 before the first night of the new cycle."
        n_b, m_b, o_b = int(block_nights), int(block_days), int(block_off)
        if (
            pattern_id == "block_rotation"
            and n_b > 0
            and m_b > 0
            and o_b == 0
            and index == n_b + m_b - 1
        ):
            d_tr = True
            sso, seo = "14:00", "18:00"
            adv2 = (adv2 or "")
            adv2 = adv2 + " End of day block: 4h nap 14:00–18:00, then first night of night block."

        base = _work_day(
            d, "day", wd[0], wd[1], sso, seo, adv2.strip() if adv2 else None, template=d_pl, is_transition=d_tr
        )
        base.update(out_meta)
        return base

    if slot == "off":
        sl, se = "08:00", "16:00"
        adv3: Optional[str] = "Off day — sleep aligned with upcoming work block."

        if pattern_id == "pitman_2_2_3":
            nxt = _next_work(PITMAN_2_2_3, index)
            if nxt == "day":
                sl, se = "22:00", "06:00"
            else:
                sl, se = "08:00", "16:00"
        if pattern_id == "pat_4n4o4d4o":
            if 4 <= index <= 7:
                sl, se = "22:00", "06:00"
                adv3 = "Off before day run — use day sleep (22:00–06:00)."
            if 12 <= index <= 15:
                sl, se = "08:00", "16:00"
                adv3 = "Off before night run — use night sleep (08:00–16:00)."
            if index == 15:
                sl, se = "14:00", "18:00"
                adv3 = "Last off day before night: 4h nap, then first night."
        if pattern_id == "pat_4n4o":
            sl, se = "08:00", "16:00"
            adv3 = "Off — stay in night mode (08:00–16:00)."
            extra_b: List[Dict] = []
            if index == 7:
                sl, se = "14:00", "18:00"
                adv3 = "Last off day: 4h nap 14:00–18:00, bright light ~20:00, then first night block."
                extra_b = [
                    {
                        "time": "20:00",
                        "message": "Bright light 20:00 to boost alertness before the night block.",
                        "type": "alert",
                    }
                ]
            else:
                extra_b = []
            hab = rest_day_habit_windows(sl, se)
            bright_merged = list(hab["brightness_windows"]) + extra_b
            b = _off_style(d, sl, se, adv3, hab["coffee_windows"], hab["meal_windows"], bright_merged)
            b.update(out_meta)
            return b
        if pattern_id == "block_rotation":
            sl, se = "08:00", "16:00"
            adv3 = "Off day — use night rest sleep; next work block is nights."
        hab = rest_day_habit_windows(sl, se)
        b = _off_style(
            d,
            sl,
            se,
            adv3,
            hab["coffee_windows"],
            hab["meal_windows"],
            hab["brightness_windows"],
        )
        b.update(out_meta)
        return b

    hab0 = rest_day_habit_windows("22:00", "06:00")
    b = _off_style(d, "22:00", "06:00", None, hab0["coffee_windows"], hab0["meal_windows"], hab0["brightness_windows"])
    b.update(out_meta)
    return b


def _coerce_shifts_payload(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            return json.loads(raw) or {}
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}
    if isinstance(raw, dict):
        return raw
    return {}


def pattern_includes_day_work(
    pattern_id: str, block_days: int = 14, shifts: Optional[Dict[str, Any]] = None
) -> bool:
    if pattern_id in ("pat_4n4o",):
        return False
    if pattern_id == "block_rotation":
        bd = int(block_days)
        if shifts and shifts.get("block_days") is not None:
            bd = int(shifts.get("block_days") or 0)
        return bd > 0
    return pattern_id in DAY_SHIPPED_PATTERNS


def _as_date(d: Any, fallback: date) -> date:
    if d is None:
        return fallback
    if isinstance(d, date):
        return d
    if isinstance(d, str):
        try:
            return date.fromisoformat(d[:10])
        except (ValueError, TypeError):
            return fallback
    if hasattr(d, "year") and hasattr(d, "month") and hasattr(d, "day"):
        try:
            return date(int(d.year), int(d.month), int(d.day))  # type: ignore[attr-defined]
        except Exception:
            return fallback
    return fallback


# If pattern_start_date is NULL/missing, do *not* fall back to `local_day` (the day being
# resolved): that made every day use "today" as the anchor, so the cycle index was always 0
# and Monday vs Thursday (etc.) was ignored. Use a fixed epoch only for broken legacy rows.
PATTERN_START_FALLBACK = date(2000, 1, 1)


def _parse_pattern_start_date(row: Dict[str, Any], sh: Dict[str, Any]) -> date:
    """
    Calendar day that maps to index 0 of the pattern sequence (e.g. for Pitman, the first
    "night" in the built-in 14-day array). Shifts by whole days relative to this anchor.
    """
    raw: Any = row.get("pattern_start_date") or sh.get("pattern_start_date") or sh.get(
        "patternStartDate"
    )
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        return PATTERN_START_FALLBACK
    return _as_date(raw, PATTERN_START_FALLBACK)


def build_rotating_day_from_pattern_row(
    row: Dict[str, Any], local_day: date
) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    sh = _coerce_shifts_payload(row.get("shifts"))
    start = _parse_pattern_start_date(row, sh)
    pid = str(
        sh.get("pattern_id")
        or sh.get("patternName")
        or row.get("pattern_name")
        or "pitman_2_2_3"
    )
    night = sh.get("night") or {}
    day_ = sh.get("day")
    if not isinstance(night, dict):
        night = {}
    if day_ is not None and not isinstance(day_, dict):
        day_ = None
    bn = int(sh.get("block_nights", sh.get("blockNights", 14)) or 0)
    bd = int(sh.get("block_days", sh.get("blockDays", 14)) or 0)
    bo = int(sh.get("block_off", sh.get("blockOff", 0)) or 0)
    if pid == "block_rotation":
        if bn < 0:
            bn = 0
        if bd < 0:
            bd = 0
        if bo < 0:
            bo = 0
    return build_rotating_day(
        pid,
        start,
        local_day,
        night,
        day_ if day_ is not None else None,
        block_nights=bn,
        block_days=bd,
        block_off=bo,
    )
