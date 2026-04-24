"""
Automated tests for Nightflow shared logic and API helpers (no DB mocks required for these).
Run from project root:  python -m unittest test_app -v
"""

import unittest
from datetime import date, datetime, time, timedelta, timezone

from shared.schedule_utils import (
    str_to_time,
    time_to_str,
    classify_shift_type_from_work_start,
)
from shared.insights import (
    build_bad_habit_suggestion_items,
    get_habits_effective_for_current_shift,
    get_habits_effective_from_date,
    week_query_start,
)
from shared.subscription import (
    MAX_PRO_REFUNDS_PER_UTC_MONTH,
    pro_refund_month_limit_reached,
    try_record_pro_refund_count,
    merge_notification_prefs_increment_pro_refund,
    PRO_REFUND_COUNTS_BY_MONTH_KEY,
    PRO_REFUND_RECORDED_CHARGE_IDS_KEY,
)
from shared.rotating_engine import (
    resolve_slot_in_cycle,
    build_rotating_day_from_pattern_row,
    pattern_includes_day_work,
    build_rotating_day,
    PITMAN_2_2_3,
)
from api.routes.schedules import _shift_one_window_time, _add_minutes_to_time_hhmm


class TestScheduleUtils(unittest.TestCase):
    def test_str_to_time_parses_hhmm(self):
        t = str_to_time("19:30")
        self.assertIsNotNone(t)
        assert t is not None
        self.assertEqual(t.hour, 19)
        self.assertEqual(t.minute, 30)

    def test_time_to_str(self):
        self.assertEqual(time_to_str(time(8, 5)), "08:05")
        self.assertEqual(time_to_str("9:00"), "09:00")

    def test_classify_shift_night(self):
        self.assertEqual(classify_shift_type_from_work_start(time(20, 0)), "night")
        self.assertEqual(classify_shift_type_from_work_start(time(2, 0)), "night")


class TestRefundMonthlyCap(unittest.TestCase):
    def test_merge_increments_utc_month(self):
        p = merge_notification_prefs_increment_pro_refund(
            {PRO_REFUND_COUNTS_BY_MONTH_KEY: {}}
        )
        ym = datetime.now(timezone.utc).strftime("%Y-%m")
        self.assertEqual(p[PRO_REFUND_COUNTS_BY_MONTH_KEY].get(ym), 1)

    def test_limit_reached_at_one(self):
        ym = datetime.now(timezone.utc).strftime("%Y-%m")
        row_at_cap = {
            "notification_prefs": {PRO_REFUND_COUNTS_BY_MONTH_KEY: {ym: MAX_PRO_REFUNDS_PER_UTC_MONTH}}
        }
        self.assertTrue(pro_refund_month_limit_reached(row_at_cap))
        row_under = {"notification_prefs": {PRO_REFUND_COUNTS_BY_MONTH_KEY: {ym: 0}}}
        self.assertFalse(pro_refund_month_limit_reached(row_under))

    def test_try_record_dedupes_same_charge(self):
        prefs = {}
        p1, did1 = try_record_pro_refund_count(prefs, "chg_123")
        self.assertTrue(did1)
        p2, did2 = try_record_pro_refund_count(p1, "chg_123")
        self.assertFalse(did2)
        self.assertIn("chg_123", p1.get(PRO_REFUND_RECORDED_CHARGE_IDS_KEY, []))


class TestSchedulesHelpers(unittest.TestCase):
    def test_shift_one_window_hits(self):
        ok, nxt = _shift_one_window_time([{"time": "10:00"}, {"time": "14:00"}], "10:00", "10:30")
        self.assertTrue(ok)
        self.assertEqual(nxt[0]["time"], "10:30")
        self.assertEqual(nxt[1]["time"], "14:00")

    def test_shift_one_window_miss(self):
        ok, nxt = _shift_one_window_time([{"time": "11:00"}], "10:00", "10:30")
        self.assertFalse(ok)

    def test_add_minutes_earlier_sleep(self):
        # extend_sleep uses negative delta (earlier to bed)
        self.assertEqual(_add_minutes_to_time_hhmm("23:00", -30), "22:30")
        self.assertEqual(_add_minutes_to_time_hhmm("00:15", -30), "23:45")


class TestInsightsBadHabits(unittest.TestCase):
    def test_coffee_too_close_includes_template(self):
        items = build_bad_habit_suggestion_items(
            "22:00",
            [{"time": "20:00", "message": "x", "type": "mid_shift"}],
            [],
            [],
            "night",
        )
        self.assertTrue(any("Coffee" in (x.get("title") or "") for x in items))
        ap = next(x for x in items if "apply" in x)["apply"]
        self.assertEqual(ap.get("op"), "shift_coffee")
        self.assertEqual(ap.get("template"), "night")

    def test_no_issue_when_coffee_safe(self):
        items = build_bad_habit_suggestion_items(
            "22:00",
            [{"time": "15:00", "message": "x", "type": "mid_shift"}],
            [],
            [],
        )
        self.assertEqual(items, [])

    def test_week_query_start(self):
        w0 = date(2025, 3, 10)
        eff = date(2025, 3, 12)
        self.assertEqual(week_query_start(w0, None), w0)
        self.assertEqual(week_query_start(w0, eff), eff)

    def test_habits_effective_none(self):
        self.assertIsNone(get_habits_effective_from_date(None))

    def test_habits_effective_shift_mismatch_uses_today(self):
        d0 = date(2025, 3, 1)
        today = date(2025, 3, 20)
        prefs = {"habits_effective_from": "2025-03-01", "habits_effective_shift_type": "rotating"}
        eff = get_habits_effective_for_current_shift(prefs, "constant", today)
        self.assertEqual(eff, today)
        eff_ok = get_habits_effective_for_current_shift(prefs, "rotating", today)
        self.assertEqual(eff_ok, d0)


class TestRotatingEngine(unittest.TestCase):
    def test_pitman_cycle_length(self):
        self.assertEqual(len(PITMAN_2_2_3), 14)

    def test_resolve_pitman_slot(self):
        start = date(2020, 1, 1)
        slot, idx, cyc = resolve_slot_in_cycle("pitman_2_2_3", start, start, 14, 14, 0)
        self.assertEqual(slot, "night")
        self.assertEqual(cyc, 14)
        d13 = start + timedelta(days=13)
        s13, i13, _ = resolve_slot_in_cycle("pitman_2_2_3", start, d13, 14, 14, 0)
        self.assertEqual(s13, "day", "last index of first week block should be first day in pitman list")

    def test_pattern_includes_day_work(self):
        self.assertTrue(pattern_includes_day_work("pitman_2_2_3", 14, None))
        self.assertFalse(pattern_includes_day_work("pat_4n4o", 0, None))
        self.assertTrue(pattern_includes_day_work("block_rotation", 14, {"block_days": 7}))

    def test_build_rotating_day_from_row_has_pattern_slot(self):
        row = {
            "shifts": {
                "pattern_id": "pat_4n4o",
                "block_nights": 4,
                "block_off": 4,
                "block_days": 0,
                "night": {
                    "work_start": "19:00",
                    "work_end": "07:00",
                    "sleep_start": "08:00",
                    "sleep_end": "16:00",
                },
            },
            "pattern_start_date": "2000-01-01",
        }
        out = build_rotating_day_from_pattern_row(row, date(2000, 1, 1))
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out.get("pattern_slot"), "night")

    def test_build_rotating_day_smoke_pitman(self):
        night = {
            "work_start": "19:00",
            "work_end": "07:00",
            "sleep_start": "08:00",
            "sleep_end": "16:00",
        }
        day_ = {
            "work_start": "07:00",
            "work_end": "19:00",
            "sleep_start": "22:00",
            "sleep_end": "06:00",
        }
        d0 = date(2000, 1, 3)
        comp = build_rotating_day("pitman_2_2_3", date(2000, 1, 1), d0, night, day_)
        self.assertIn("work_start", comp)
        self.assertIn("pattern_slot", comp)


if __name__ == "__main__":
    unittest.main()
