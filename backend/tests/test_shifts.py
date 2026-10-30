from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from checkweigher.shifts import DEFAULT_SHIFTS, NO_SHIFT, Shift, ShiftResolver

IST = ZoneInfo("Asia/Kolkata")


@pytest.mark.parametrize(
    ("local", "expected"),
    [
        (datetime(2026, 10, 5, 6, 0), (date(2026, 10, 5), "A")),
        (datetime(2026, 10, 5, 13, 59, 59), (date(2026, 10, 5), "A")),
        (datetime(2026, 10, 5, 14, 0), (date(2026, 10, 5), "B")),
        (datetime(2026, 10, 5, 22, 0), (date(2026, 10, 5), "C")),
        (datetime(2026, 10, 5, 23, 59), (date(2026, 10, 5), "C")),
        # After midnight still belongs to the night shift of the previous production date.
        (datetime(2026, 10, 6, 0, 0), (date(2026, 10, 5), "C")),
        (datetime(2026, 10, 6, 5, 59, 59), (date(2026, 10, 5), "C")),
    ],
)
def test_default_shifts(local, expected):
    r = ShiftResolver(DEFAULT_SHIFTS, IST)
    assert r.resolve(local.replace(tzinfo=IST)) == expected


def test_utc_input_is_converted_to_plant_time():
    r = ShiftResolver(DEFAULT_SHIFTS, IST)
    # 20:00 UTC = 01:30 IST next day -> shift C of the previous production date
    assert r.resolve(datetime(2026, 10, 5, 20, 0, tzinfo=UTC)) == (date(2026, 10, 5), "C")


def test_gap_in_shift_definitions():
    r = ShiftResolver([Shift("D", "Day", *(datetime(1, 1, 1, h).time() for h in (8, 20)))], IST)
    assert r.resolve(datetime(2026, 10, 5, 21, 0, tzinfo=IST)) == (date(2026, 10, 5), NO_SHIFT)
