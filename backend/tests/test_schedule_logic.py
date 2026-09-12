"""Tests for anchor-based schedule distribution (pure logic, no DB)."""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/test")
os.environ.setdefault("JWT_SECRET", "test-secret")

from datetime import date, datetime, timezone

from app.services import schedule_logic as sl


def test_parse_hhmm_valid_and_invalid():
    assert sl.parse_hhmm("09:30") is not None
    assert sl.parse_hhmm("23:59") is not None
    for bad in ("24:00", "9", "abc", "09:60", "", "0900"):
        try:
            sl.parse_hhmm(bad)
            assert False, f"expected ValueError for {bad!r}"
        except ValueError:
            pass


def test_distribution_counts():
    assert sl.distribution_for_count(1) == [1, 0]
    assert sl.distribution_for_count(2) == [1, 1]
    assert sl.distribution_for_count(3) == [2, 1]
    assert sl.distribution_for_count(4) == [2, 2]
    assert sl.distribution_for_count(5) == [3, 2]
    assert sl.distribution_for_count(7) == [4, 3]


def test_slot_times_deterministic_for_same_inputs():
    kw = dict(channel_key="ch-1", run_date=date(2026, 9, 11), count=3,
              anchor_1="09:00", anchor_2="18:00", tz_name="Asia/Kolkata")
    a = sl.slot_times(**kw)
    b = sl.slot_times(**kw)
    assert a == b
    assert len(a) == 3
    assert a == sorted(a)


def test_slot_times_all_in_utc_and_on_run_date():
    times = sl.slot_times(channel_key="ch-2", run_date=date(2026, 9, 11), count=4,
                          anchor_1="09:00", anchor_2="18:00")
    for t in times:
        assert t.tzinfo is not None and t.utcoffset().total_seconds() == 0
        # 09:00 IST == 03:30 UTC; 18:00 IST == 12:30 UTC — same UTC date.
        assert t.date() == date(2026, 9, 11)


def test_two_slots_landed_on_both_anchors():
    times = sl.slot_times(channel_key="ch-3", run_date=date(2026, 9, 11), count=2,
                          anchor_1="09:00", anchor_2="18:00", tz_name="Asia/Kolkata")
    local_hours = sorted(t.astimezone(sl.ZoneInfo("Asia/Kolkata")).hour for t in times)
    # one near 9am, one near 6pm IST (jitter ≤ 45min can push hour by +0)
    assert 9 <= local_hours[0] <= 10
    assert 18 <= local_hours[1] <= 19


def test_single_count_picks_exactly_one_anchor():
    """1/day: always exactly one slot, at one of the two anchors."""
    seen_anchors = set()
    for i in range(20):
        times = sl.slot_times(channel_key=f"ch-{i}", run_date=date(2026, 9, 11), count=1,
                              anchor_1="09:00", anchor_2="18:00", tz_name="Asia/Kolkata")
        assert len(times) == 1
        h = times[0].astimezone(sl.ZoneInfo("Asia/Kolkata")).hour
        assert h in (9, 18)
        seen_anchors.add(h)
    assert len(seen_anchors) == 2  # both anchors get used across channels


def test_due_slot_indexes_catchup_and_idempotency():
    now = datetime(2026, 9, 11, 10, 0, tzinfo=timezone.utc)  # 15:30 IST
    kw = dict(now_utc=now, channel_key="ch-x", run_date=date(2026, 9, 11),
              count=2, anchor_1="09:00", anchor_2="18:00", tz_name="Asia/Kolkata")
    due = sl.due_slot_indexes(**kw)
    # 09:00 IST (03:30 UTC) passed; 18:00 IST (12:30 UTC) not yet.
    assert all(i == 0 for i in due) and 1 not in due
    # After slot 0 ran, nothing new is due (idempotent catch-up).
    after = sl.due_slot_indexes(**kw, done_slot_indexes={0})
    assert after == []
    # Next day, both slots become due again for the new run_date.
    tomorrow = sl.due_slot_indexes(**{**kw, "run_date": date(2026, 9, 12)}, )
    # at now (10:00 UTC on the 11th) no slot of the 12th is due yet:
    assert tomorrow == []


def test_restart_produces_same_due_slots():
    """Simulate a Render cold start: a fresh call with the same inputs sees
    the same due slot list, so catch-up is exact and never duplicates."""
    now = datetime(2026, 9, 11, 14, 0, tzinfo=timezone.utc)  # 19:30 IST
    kw = dict(now_utc=now, channel_key="ch-y", run_date=date(2026, 9, 11),
              count=3, anchor_1="09:00", anchor_2="18:00", tz_name="Asia/Kolkata")
    first = sl.due_slot_indexes(**kw)
    again = sl.due_slot_indexes(**kw)
    assert first == again and len(first) == 3
