"""SQL-level tests against a real PostgreSQL (TimescaleDB variant if the server has it).

Uses CW_TEST_DATABASE_URL (default: the dev server from scripts/dev-db.ps1). A throwaway
database is created and dropped per test session; the test is skipped if no server is reachable.
"""

from __future__ import annotations

import asyncio
import os
import statistics
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import psycopg
import pytest
from psycopg.rows import dict_row

from checkweigher.api import data
from checkweigher.api.filters import Filters
from checkweigher.db.migrate import migrate
from checkweigher.shifts import DEFAULT_SHIFTS, ShiftResolver

ADMIN_URL = os.environ.get("CW_TEST_DATABASE_URL", "postgresql://cw:cw@localhost:5433/postgres")
IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 10, 5)


def _db_url(admin: str, name: str) -> str:
    return admin.rsplit("/", 1)[0] + f"/{name}"


@pytest.fixture(scope="module")
def db_url():
    try:
        admin = psycopg.connect(ADMIN_URL, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip(f"no PostgreSQL at {ADMIN_URL}")
    name = f"cw_test_{uuid.uuid4().hex[:8]}"
    admin.execute(f'CREATE DATABASE "{name}"')
    url = _db_url(ADMIN_URL, name)
    try:
        migrate(url)
        _seed(url)
        yield url
    finally:
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.close()


# (machine, local time, judgement, weight) -- product 500 g, limits LO 497 / HI 506
ROWS = [
    (1, datetime(2026, 10, 5, 7, 0), "OK", "501.0"),
    (1, datetime(2026, 10, 5, 7, 1), "OK", "502.0"),
    (1, datetime(2026, 10, 5, 7, 2), "OK", "502.0"),
    (1, datetime(2026, 10, 5, 7, 3), "HI", "507.5"),
    (1, datetime(2026, 10, 5, 7, 4), "TD", None),
    (1, datetime(2026, 10, 5, 23, 30), "LO", "496.0"),   # shift C of the 5th
    (1, datetime(2026, 10, 6, 2, 0), "OK", "503.0"),     # still shift C of the 5th
    (2, datetime(2026, 10, 5, 15, 0), "OK", "500.5"),
    (2, datetime(2026, 10, 5, 15, 1), "HI", "508.0"),
]


def _seed(url: str) -> None:
    resolver = ShiftResolver(DEFAULT_SHIFTS, IST)
    with psycopg.connect(url, autocommit=True) as conn:
        for mid in (1, 2):
            conn.execute("INSERT INTO machine (id, code, name, mode) VALUES (%s, %s, %s, 'serial+modbus')",
                         (mid, f"CW-0{mid}", f"Machine {mid}"))
        pid = conn.execute(
            "INSERT INTO product_setting (machine_id, group_no, product_no, target_g, hihi_g, hi_g, lo_g, lolo_g, "
            "tare_g, ow_exception, reject_stage) VALUES (1, 1, 1, 500, 515, 506, 497, 490, 0, false, 0) RETURNING id"
        ).fetchone()[0]  # type: ignore[index]
        for i, (mid, local, j, w) in enumerate(ROWS):
            ts = local.replace(tzinfo=IST).astimezone(UTC)
            sd, sc = resolver.resolve(ts)
            conn.execute(
                "INSERT INTO weighing (ts, machine_id, seq, judgement, weight_g, target_g, product_id, shift_date, "
                "shift_code, source) VALUES (%s,%s,%s,%s,%s,500,%s,%s,%s,'serial')",
                (ts, mid, None if w is None else i + 1, j, None if w is None else Decimal(w), pid, sd, sc),
            )
        conn.execute(
            "INSERT INTO reconciliation (machine_id, window_start, window_end, shift_date, shift_code, expected, "
            "received) VALUES (1, now(), now(), %s, 'A', 6, 5)", (DAY,))


def run(url: str, fn, *args):
    async def go():
        async with await psycopg.AsyncConnection.connect(url, autocommit=True, row_factory=dict_row) as conn:
            return await fn(conn, *args)

    return asyncio.run(go(), loop_factory=asyncio.SelectorEventLoop)


def test_summary_weighted_and_exact(db_url):
    s = run(db_url, data.summary, Filters(DAY, DAY, tz=IST))
    k = s.overall
    assert k.total == len(ROWS)
    assert k.weighed == len(ROWS) - 1
    assert k.overweight == 2 and k.underweight == 1 and k.feeding_errors == 1 and k.detect_two == 1
    assert k.overweight_pct == pytest.approx(2 / 9 * 100)
    weights = [float(w) for *_, w in ROWS if w is not None]
    assert k.mean_g == pytest.approx(statistics.mean(weights))
    assert k.sd_g == pytest.approx(statistics.stdev(weights))
    assert k.median_g == statistics.median(weights)
    assert k.mode_g == 502.0 and k.mode_count == 2
    ok = [float(w) for _, _, j, w in ROWS if j == "OK"]
    assert k.ega_pct == pytest.approx(sum(w - 500 for w in ok) / (500 * len(ok)) * 100)

    by_machine = {m.machine.id: m for m in s.machines}
    assert by_machine[1].kpis.total == 7 and by_machine[2].kpis.total == 2
    assert by_machine[1].last is not None and by_machine[1].last.weight_g == 503.0  # 02:00 on the 6th
    assert by_machine[1].completeness is not None and by_machine[1].completeness.pct == pytest.approx(5 / 6 * 100)
    assert s.products and s.products[0].target_g == 500.0


def test_shift_filter_crosses_midnight(db_url):
    c = run(db_url, data.summary, Filters(DAY, DAY, shift="C", tz=IST))
    assert c.overall.total == 2
    assert c.overall.underweight == 1
    nxt = run(db_url, data.summary, Filters(DAY + timedelta(days=1), DAY + timedelta(days=1), tz=IST))
    assert nxt.overall.total == 0


def test_machine_filter(db_url):
    s = run(db_url, data.summary, Filters(DAY, DAY, machine_ids=[2], tz=IST))
    assert s.overall.total == 2 and [m.machine.id for m in s.machines] == [2]


def test_trend_intervals(db_url):
    f = Filters(DAY, DAY, tz=IST)
    shifts = run(db_url, data.trend, f, "shift")
    assert [p.label for p in shifts.points] == ["05 Oct A", "05 Oct B", "05 Oct C"]
    assert sum(p.total for p in shifts.points) == len(ROWS)
    hourly = run(db_url, data.trend, f, "1h")
    assert hourly.points[0].label.endswith("07:00")
    assert sum(p.total for p in hourly.points) == len(ROWS)
    daily = run(db_url, data.trend, f, "1d")
    assert len(daily.points) == 1 and daily.points[0].total == len(ROWS)


def test_histogram_and_weighings_pagination(db_url):
    f = Filters(DAY, DAY, tz=IST)
    h = run(db_url, data.histogram, f, 40)
    assert h.total == len(ROWS) - 1 and h.product is not None
    page1 = run(db_url, data.weighings, f, 4, None, None)
    assert len(page1.rows) == 4 and page1.next_before is not None
    page2 = run(db_url, data.weighings, f, 4, page1.next_before, None)
    page3 = run(db_url, data.weighings, f, 4, page2.next_before, None)
    seen = [r.ts for r in page1.rows + page2.rows + page3.rows]
    assert len(seen) == len(set(seen)) == len(ROWS)
    rejects = run(db_url, data.weighings, f, 50, None, ["HI", "HH"])
    assert {r.judgement for r in rejects.rows} == {"HI"} and len(rejects.rows) == 2
