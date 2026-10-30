"""Dashboard filters: production-date range + shift + machines.

Rows are selected by their stored production date / shift, so aggregates are
exact regardless of shift boundaries. A timestamp window derived from the dates
is added for chunk exclusion and index range scans.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Query, Request

MAX_RANGE_DAYS = 400
UTC_ZONE = ZoneInfo("UTC")


@dataclass(frozen=True)
class Filters:
    date_from: date
    date_to: date
    shift: str | None = None
    machine_ids: list[int] = field(default_factory=list)
    tz: ZoneInfo = UTC_ZONE
    product_id: int | None = None

    @property
    def ts_lo(self) -> datetime:
        return datetime.combine(self.date_from, time(0), self.tz)

    @property
    def ts_hi(self) -> datetime:
        # A shift belongs to the date it starts on and may end the next day.
        return datetime.combine(self.date_to + timedelta(days=2), time(0), self.tz)

    def where(self, alias: str = "", *, time_col: str | None = "ts", time_slack: timedelta = timedelta(0)
              ) -> tuple[str, dict[str, Any]]:
        p = f"{alias}." if alias else ""
        clauses = [f"{p}shift_date BETWEEN %(date_from)s AND %(date_to)s"]
        params: dict[str, Any] = {"date_from": self.date_from, "date_to": self.date_to}
        if time_col:
            clauses.append(f"{p}{time_col} >= %(ts_lo)s AND {p}{time_col} < %(ts_hi)s")
            params |= {"ts_lo": self.ts_lo - time_slack, "ts_hi": self.ts_hi}
        if self.shift:
            clauses.append(f"{p}shift_code = %(shift)s")
            params["shift"] = self.shift
        if self.machine_ids:
            clauses.append(f"{p}machine_id = ANY(%(machine_ids)s)")
            params["machine_ids"] = self.machine_ids
        if self.product_id is not None:
            clauses.append(f"{p}product_id = %(product_id)s")
            params["product_id"] = self.product_id
        return " AND ".join(clauses), params


def get_filters(
    request: Request,
    date_from: date | None = None,
    date_to: date | None = None,
    shift: str | None = None,
    machine_id: Annotated[list[int] | None, Query()] = None,
    product_id: int | None = None,
) -> Filters:
    state = request.app.state
    today = state.resolver.resolve(datetime.now(state.tz))[0]
    df = date_from or today
    dt = date_to or df
    if dt < df:
        raise HTTPException(422, "date_to must not be before date_from")
    if (dt - df).days > MAX_RANGE_DAYS:
        raise HTTPException(422, f"date range is limited to {MAX_RANGE_DAYS} days")
    return Filters(df, dt, None if shift in (None, "", "all") else shift, sorted(set(machine_id or [])), state.tz,
                   product_id)
