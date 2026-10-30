"""SQL for the dashboard, assembled into response models."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

from psycopg import AsyncConnection

from checkweigher.api import schemas as S
from checkweigher.api.filters import Filters
from checkweigher.api.kpi import SUM_COLUMNS, SUM_SQL, Sums, compute_kpis, distribution, histogram_bins

AGG_SLACK = timedelta(days=1)  # aggregate buckets start up to a bucket width before their rows

Row = dict[str, Any]


async def fetch(conn: AsyncConnection, sql: str, params: dict[str, Any] | tuple | None = None) -> list[Row]:
    cur = await conn.execute(sql, params)
    return await cur.fetchall()  # type: ignore[return-value]


async def machines(conn: AsyncConnection, ids: list[int] | None = None) -> list[S.MachineRef]:
    rows = await fetch(conn, "SELECT id, code, name, mode FROM machine WHERE active "
                             "AND (%(ids)s::smallint[] IS NULL OR id = ANY(%(ids)s)) ORDER BY id",
                       {"ids": ids or None})
    return [S.MachineRef(**r) for r in rows]


def merge_sums(items: list[Sums]) -> Sums:
    out = Sums()
    for c in SUM_COLUMNS:
        setattr(out, c, sum(getattr(s, c) for s in items))
    out.min_w = min((s.min_w for s in items if s.min_w is not None), default=None)
    out.max_w = max((s.max_w for s in items if s.max_w is not None), default=None)
    return out


def kpis(s: Sums, hist: list[tuple[float, int]]) -> S.KPIs:
    return S.KPIs(**compute_kpis(s), **distribution(hist))


async def summary(conn: AsyncConnection, f: Filters) -> S.Summary:
    where, params = f.where(time_col="bucket", time_slack=AGG_SLACK)
    sums = {r["machine_id"]: Sums.from_row(r) for r in await fetch(
        conn, f"SELECT machine_id, {SUM_SQL} FROM weighing_15m WHERE {where} GROUP BY machine_id", params)}

    hist: dict[int, list[tuple[float, int]]] = defaultdict(list)
    for r in await fetch(conn, f"SELECT machine_id, weight_g, sum(n) AS n FROM weighing_hist WHERE {where} "
                               "GROUP BY machine_id, weight_g ORDER BY weight_g", params):
        hist[r["machine_id"]].append((float(r["weight_g"]), int(r["n"])))
    overall_hist: dict[float, int] = defaultdict(int)
    for h in hist.values():
        for w, n in h:
            overall_hist[w] += n

    rwhere, rparams = f.where()
    comp = {r["machine_id"]: r for r in await fetch(
        conn, f"SELECT machine_id, sum(expected) AS expected, sum(received) AS received FROM reconciliation "
              f"WHERE {f.where(time_col=None)[0]} GROUP BY machine_id", rparams)}

    machine_list = await machines(conn, f.machine_ids)
    last = {}
    for m in machine_list:
        # Backward index scan on (machine_id, ts), bounded by the date window.
        rows = await fetch(conn, f"SELECT machine_id, ts, weight_g, judgement FROM weighing WHERE machine_id = "
                                 f"%(mid)s AND {rwhere} ORDER BY ts DESC LIMIT 1", rparams | {"mid": m.id})
        if rows:
            last[m.id] = S.LastWeight(**rows[0])

    def completeness(rows: list[Row]) -> S.Completeness | None:
        exp, rec = sum(int(r["expected"]) for r in rows), sum(int(r["received"]) for r in rows)
        return S.Completeness(expected=exp, received=rec, pct=min(100.0, rec / exp * 100) if exp else None) \
            if rows else None

    per_machine = [
        S.MachineSummary(machine=m, kpis=kpis(sums.get(m.id, Sums()), hist.get(m.id, [])), last=last.get(m.id),
                         completeness=completeness([comp[m.id]] if m.id in comp else []))
        for m in machine_list
    ]
    products = await fetch(
        conn,
        f"SELECT p.id, p.machine_id, p.group_no, p.product_no, p.target_g, p.hihi_g, p.hi_g, p.lo_g, p.lolo_g, "
        f"sum(a.n) AS n FROM weighing_15m a JOIN product_setting p ON p.id = a.product_id "
        f"WHERE {f.where('a', time_col='bucket', time_slack=AGG_SLACK)[0]} GROUP BY p.id ORDER BY n DESC",
        params,
    )
    latest = max(last.values(), key=lambda x: x.ts, default=None)
    return S.Summary(
        date_from=f.date_from, date_to=f.date_to, shift=f.shift, machine_ids=f.machine_ids,
        overall=kpis(merge_sums(list(sums.values())), sorted(overall_hist.items())),
        last=latest, completeness=completeness(list(comp.values())), machines=per_machine,
        products=[S.Product(**r) for r in products],
    )


TREND_INTERVALS = {"15m": timedelta(minutes=15), "1h": timedelta(hours=1)}


def auto_interval(f: Filters) -> str:
    days = (f.date_to - f.date_from).days + 1
    return "15m" if days <= 1 else "1h" if days <= 7 else "shift" if days <= 45 else "1d"


async def trend(conn: AsyncConnection, f: Filters, interval: str) -> S.Trend:
    if interval == "auto":
        interval = auto_interval(f)
    where, params = f.where("a", time_col="bucket", time_slack=AGG_SLACK)
    if interval in TREND_INTERVALS:
        origin = datetime(2000, 1, 1, tzinfo=f.tz)
        sql = (f"SELECT date_bin(%(stride)s, a.bucket, %(origin)s) AS t, {SUM_SQL} FROM weighing_15m a "
               f"WHERE {where} GROUP BY 1 ORDER BY 1")
        rows = await fetch(conn, sql, params | {"stride": TREND_INTERVALS[interval], "origin": origin})
        label = "%H:%M" if interval == "15m" else "%d %b %H:%M"
        points = [(r["t"], r["t"].astimezone(f.tz).strftime(label), r) for r in rows]
    elif interval == "shift":
        sql = (f"SELECT a.shift_date, a.shift_code, s.start_time, s.sort, {SUM_SQL} FROM weighing_15m a "
               f"LEFT JOIN shift s ON s.code = a.shift_code WHERE {where} "
               f"GROUP BY a.shift_date, a.shift_code, s.start_time, s.sort ORDER BY a.shift_date, s.sort")
        points = []
        for r in await fetch(conn, sql, params):
            t = datetime.combine(r["shift_date"], r["start_time"] or datetime.min.time(), f.tz)
            points.append((t, f"{r['shift_date']:%d %b} {r['shift_code']}", r))
    elif interval == "1d":
        sql = f"SELECT a.shift_date, {SUM_SQL} FROM weighing_15m a WHERE {where} GROUP BY 1 ORDER BY 1"
        points = [(datetime.combine(r["shift_date"], datetime.min.time(), f.tz), f"{r['shift_date']:%d %b}", r)
                  for r in await fetch(conn, sql, params)]
    else:
        raise ValueError(f"unknown interval {interval}")

    fields = S.TrendPoint.model_fields.keys() - {"t", "label"}
    out = []
    for t, label, r in points:
        k = compute_kpis(Sums.from_row(r))
        out.append(S.TrendPoint(t=t, label=label, **{f: k[f] for f in fields}))
    return S.Trend(interval=interval, points=out)


async def histogram(conn: AsyncConnection, f: Filters, max_bins: int = 40) -> S.Histogram:
    """Weight distribution of one product (the requested one, else the most produced in range):
    mixing products with different targets would make the histogram meaningless."""
    where, params = f.where("a", time_col="bucket", time_slack=AGG_SLACK)
    product = await fetch(
        conn,
        f"SELECT p.id, p.machine_id, p.group_no, p.product_no, p.target_g, p.hihi_g, p.hi_g, p.lo_g, p.lolo_g, "
        f"sum(a.n) AS n FROM weighing_15m a JOIN product_setting p ON p.id = a.product_id "
        f"WHERE {where} GROUP BY p.id ORDER BY n DESC LIMIT 1",
        params,
    )
    if product and f.product_id is None:
        f = replace(f, product_id=product[0]["id"])
    where, params = f.where(time_col="bucket", time_slack=AGG_SLACK)
    rows = await fetch(conn, f"SELECT weight_g, sum(n) AS n FROM weighing_hist WHERE {where} "
                             "GROUP BY weight_g ORDER BY weight_g", params)
    hist = [(float(r["weight_g"]), int(r["n"])) for r in rows]
    bins, width = histogram_bins(hist, max_bins)
    return S.Histogram(bins=[S.HistogramBin(**b) for b in bins], bin_width=width, total=sum(n for _, n in hist),
                       product=S.Product(**product[0]) if product else None)


WEIGHING_COLS = "ts, machine_id, seq, judgement, weight_g, target_g, product_id, shift_date, shift_code, source"


async def weighings(conn: AsyncConnection, f: Filters, limit: int, before: datetime | None,
                    judgements: list[str] | None = None) -> S.Weighings:
    where, params = f.where()
    if before:
        where += " AND ts < %(before)s"
        params["before"] = before
    if judgements:
        where += " AND judgement = ANY(%(judgements)s)"
        params["judgements"] = judgements
    rows = await fetch(conn, f"SELECT {WEIGHING_COLS} FROM weighing WHERE {where} ORDER BY ts DESC "
                             "LIMIT %(limit)s", params | {"limit": limit})
    return S.Weighings(rows=[S.Weighing(**r) for r in rows],
                       next_before=rows[-1]["ts"] if len(rows) == limit else None)


async def recent(conn: AsyncConnection, machine_id: int, limit: int) -> list[S.Weighing]:
    rows = await fetch(conn, f"SELECT {WEIGHING_COLS} FROM weighing WHERE machine_id = %s ORDER BY ts DESC "
                             "LIMIT %s", (machine_id, limit))
    return [S.Weighing(**r) for r in reversed(rows)]


async def events(conn: AsyncConnection, machine_id: int | None, limit: int) -> list[S.Event]:
    rows = await fetch(conn, "SELECT id, ts, machine_id, kind, message, detail FROM collector_event "
                             "WHERE (%(mid)s::smallint IS NULL OR machine_id = %(mid)s) ORDER BY ts DESC "
                             "LIMIT %(limit)s", {"mid": machine_id, "limit": limit})
    return [S.Event(**r) for r in rows]


STATUS_FRESH_S = 15


async def statuses(conn: AsyncConnection) -> list[S.MachineStatus]:
    rows = await fetch(conn, "SELECT s.*, extract(epoch FROM now() - s.updated_at) AS age_s FROM machine_status s "
                             "JOIN machine m ON m.id = s.machine_id WHERE m.active ORDER BY s.machine_id")
    out = []
    for r in rows:
        age = r.pop("age_s")
        online = float(age) < STATUS_FRESH_S and "connected" in (r["serial_state"], r["modbus_state"])
        out.append(S.MachineStatus(online=online, **r))
    return out
