"""Map timestamps to (production date, shift code).

A shift that crosses midnight (e.g. 22:00-06:00) belongs to the production
date on which it started, so 02:00 on the 5th is shift C of the 4th.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

NO_SHIFT = "-"


@dataclass(frozen=True)
class Shift:
    code: str
    name: str
    start: time
    end: time
    sort: int = 0


# Matches the seed in db/sql/001_schema.sql; used if the database is unreachable at startup.
DEFAULT_SHIFTS = [
    Shift("A", "Shift A", time(6), time(14), 1),
    Shift("B", "Shift B", time(14), time(22), 2),
    Shift("C", "Shift C", time(22), time(6), 3),
]


class ShiftResolver:
    def __init__(self, shifts: list[Shift], tz: ZoneInfo):
        self.shifts = sorted(shifts, key=lambda s: s.sort)
        self.tz = tz

    def resolve(self, ts: datetime) -> tuple[date, str]:
        local = ts.astimezone(self.tz)
        t, d = local.time(), local.date()
        for s in self.shifts:
            if s.start < s.end:
                if s.start <= t < s.end:
                    return d, s.code
            elif t >= s.start:
                return d, s.code
            elif t < s.end:
                return d - timedelta(days=1), s.code
        return d, NO_SHIFT
