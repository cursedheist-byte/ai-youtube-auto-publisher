"""Pure scheduling math: anchor times + per-channel daily distribution.

Kept free of DB/FS access so it can be unit-tested without PostgreSQL.

Concept
-------
The admin sets exactly two daily "anchor" times (HH:MM, in the schedule's
timezone, default Asia/Kolkata). Each channel publishes `daily_upload_count`
videos per day, distributed around the anchors:

- 1/day  -> one video at a randomly chosen anchor (seeded per channel+date
            so restarts/catch-up pick the same slot and never duplicate).
- 2/day  -> one around anchor 1, one around anchor 2.
- 3+/day -> the count is split ceil/floor between the two anchors, with a
            per-day randomized minute offset inside each window so multiple
            runs don't fire at the exact same second.

All times are computed in the schedule timezone, returned as UTC datetimes.
"""
from __future__ import annotations

import hashlib
import random
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

# Maximum randomized jitter (minutes) applied inside a window.
MAX_JITTER_MINUTES = 45

DEFAULT_TIMEZONE = "Asia/Kolkata"


def parse_hhmm(value: str) -> time:
    """Parse 'HH:MM' (24h) -> datetime.time. Raises ValueError on bad input."""
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time {value!r}: expected 'HH:MM'")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid time {value!r}")
    return time(hour=hour, minute=minute)


def _seeded_random(*parts) -> random.Random:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()
    return random.Random(digest)


def distribution_for_count(count: int, single_anchor_index: int = 0) -> list[int]:
    """How many of `count` uploads land in each anchor window.

    Returns [slots_at_anchor_1, slots_at_anchor_2].
    1/day  -> all weight on the chosen anchor (default anchor 1).
    2/day  -> 1 and 1.
    3/day  -> 2 and 1 (ceil at anchor 1).
    4/day  -> 2 and 2, 5/day -> 3 and 2, etc.
    """
    count = max(1, count)
    if count == 1:
        return [1, 0] if single_anchor_index == 0 else [0, 1]
    half = count // 2
    return [count - half, half]


def slot_times(
    *,
    channel_key: str,
    run_date: date,
    count: int,
    anchor_1: str,
    anchor_2: str,
    tz_name: str = DEFAULT_TIMEZONE,
) -> list[datetime]:
    """UTC-aware datetimes for every upload slot of a channel/day.

    Deterministic for a given (channel, date, count, anchors): restarts and
    missed-schedule catch-up produce the identical set of times, so the
    idempotency check in automation_service sees the same slot_index list.
    """
    tz = ZoneInfo(tz_name)
    a1 = parse_hhmm(anchor_1)
    a2 = parse_hhmm(anchor_2)
    count = max(1, count)
    rng = _seeded_random(channel_key, run_date, count, anchor_1, anchor_2)

    def base(anchor: time) -> datetime:
        return datetime.combine(run_date, anchor, tzinfo=tz)

    if count == 1:
        # One anchor chosen by a stable per-day coin flip.
        chosen = a1 if rng.random() < 0.5 else a2
        return [base(chosen).astimezone(timezone.utc)]

    per_anchor = distribution_for_count(count)
    slots: list[datetime] = []
    for anchor, n in ((a1, per_anchor[0]), (a2, per_anchor[1])):
        if n <= 0:
            continue
        window_minutes = 120
        step = window_minutes / n
        for i in range(n):
            jitter = rng.randint(0, MAX_JITTER_MINUTES) if MAX_JITTER_MINUTES else 0
            slots.append(base(anchor) + timedelta(minutes=jitter + i * step))
    slots.sort()
    return [s.astimezone(timezone.utc) for s in slots]


def due_slot_indexes(
    *,
    now_utc: datetime,
    channel_key: str,
    run_date: date,
    count: int,
    anchor_1: str,
    anchor_2: str,
    tz_name: str = DEFAULT_TIMEZONE,
    done_slot_indexes: set[int] | None = None,
) -> list[int]:
    """Which slot indexes (0-based, chronological) are due right now.

    A slot is "due" when its time has passed and it has not been claimed
    yet. A Render cold start simply calls this on the next watchdog tick
    and catches up every missed slot of today.
    """
    done = done_slot_indexes or set()
    times = slot_times(
        channel_key=channel_key,
        run_date=run_date,
        count=count,
        anchor_1=anchor_1,
        anchor_2=anchor_2,
        tz_name=tz_name,
    )
    return [i for i, t in enumerate(times) if t <= now_utc and i not in done]
