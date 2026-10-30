from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response, StreamingResponse

from checkweigher.api import data
from checkweigher.api import schemas as S
from checkweigher.api.export import build_workbook
from checkweigher.api.filters import Filters, get_filters
from checkweigher.device.protocol import JUDGEMENTS
from checkweigher.shifts import Shift, ShiftResolver

router = APIRouter(prefix="/api")
FiltersDep = Annotated[Filters, Depends(get_filters)]


async def refresh_shifts(request: Request) -> list[Shift]:
    st = request.app.state
    async with st.pool.connection() as conn:
        rows = await data.fetch(conn, "SELECT code, name, start_time, end_time, sort FROM shift ORDER BY sort")
    shifts = [Shift(r["code"], r["name"], r["start_time"], r["end_time"], r["sort"]) for r in rows]
    if shifts:
        st.resolver = ShiftResolver(shifts, st.tz)
    return shifts


@router.get("/health", response_model=S.Health)
async def health(request: Request) -> S.Health:
    st = request.app.state
    try:
        async with st.pool.connection() as conn:
            rows = await data.fetch(conn, "SELECT extract(epoch FROM now() - max(updated_at)) AS age "
                                          "FROM machine_status")
        age = rows[0]["age"]
        return S.Health(ok=True, database=True, timescale=st.timescale,
                        collector_age_s=None if age is None else float(age))
    except Exception:
        return S.Health(ok=False, database=False, timescale=st.timescale, collector_age_s=None)


@router.get("/meta", response_model=S.Meta)
async def meta(request: Request) -> S.Meta:
    st = request.app.state
    shifts = await refresh_shifts(request)
    now = datetime.now(st.tz)
    today, current = st.resolver.resolve(now)
    async with st.pool.connection() as conn:
        machines = await data.machines(conn)
    return S.Meta(
        plant_name=st.cfg.plant.name, timezone=st.cfg.plant.timezone, today=today, current_shift=current,
        server_time=now, timescale=st.timescale, machines=machines,
        shifts=[S.ShiftRef(code=s.code, name=s.name, start_time=s.start, end_time=s.end) for s in shifts],
        judgements=JUDGEMENTS,
    )


@router.get("/summary", response_model=S.Summary)
async def summary(request: Request, f: FiltersDep) -> S.Summary:
    async with request.app.state.pool.connection() as conn:
        return await data.summary(conn, f)


@router.get("/trend", response_model=S.Trend)
async def trend(request: Request, f: FiltersDep,
                interval: Literal["auto", "15m", "1h", "shift", "1d"] = "auto") -> S.Trend:
    async with request.app.state.pool.connection() as conn:
        return await data.trend(conn, f, interval)


@router.get("/histogram", response_model=S.Histogram)
async def histogram(request: Request, f: FiltersDep, bins: Annotated[int, Query(ge=5, le=200)] = 40) -> S.Histogram:
    async with request.app.state.pool.connection() as conn:
        return await data.histogram(conn, f, bins)


@router.get("/weighings", response_model=S.Weighings)
async def weighings(request: Request, f: FiltersDep, limit: Annotated[int, Query(ge=1, le=1000)] = 100,
                    before: datetime | None = None,
                    judgement: Annotated[list[str] | None, Query()] = None) -> S.Weighings:
    async with request.app.state.pool.connection() as conn:
        return await data.weighings(conn, f, limit, before, judgement)


@router.get("/machines/{machine_id}/recent", response_model=list[S.Weighing])
async def recent(request: Request, machine_id: int,
                 limit: Annotated[int, Query(ge=1, le=2000)] = 200) -> list[S.Weighing]:
    async with request.app.state.pool.connection() as conn:
        return await data.recent(conn, machine_id, limit)


@router.get("/events", response_model=list[S.Event])
async def events(request: Request, machine_id: int | None = None,
                 limit: Annotated[int, Query(ge=1, le=500)] = 50) -> list[S.Event]:
    async with request.app.state.pool.connection() as conn:
        return await data.events(conn, machine_id, limit)


@router.get("/status", response_model=list[S.MachineStatus])
async def status(request: Request) -> list[S.MachineStatus]:
    async with request.app.state.pool.connection() as conn:
        return await data.statuses(conn)


@router.get("/live")
async def live(request: Request) -> StreamingResponse:
    """Server-sent events: machine status + newly stored weighings, about once a second."""
    pool = request.app.state.pool

    async def stream():
        since: datetime | None = None
        while not await request.is_disconnected():
            try:
                async with pool.connection() as conn:
                    status_rows = await data.statuses(conn)
                    if since is None:
                        rows = await data.fetch(conn, "SELECT max(ts) AS ts FROM weighing")
                        since = rows[0]["ts"] or datetime.fromtimestamp(0).astimezone()
                    new = await data.fetch(conn, f"SELECT {data.WEIGHING_COLS} FROM weighing WHERE ts > %s "
                                                 "ORDER BY ts LIMIT 500", (since,))
                if new:
                    since = new[-1]["ts"]
                payload = {"status": status_rows, "weighings": [S.Weighing(**r) for r in new]}
                yield f"event: tick\ndata: {json.dumps(jsonable_encoder(payload))}\n\n"
            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/export.xlsx")
async def export(request: Request, f: FiltersDep) -> Response:
    st = request.app.state
    if (f.date_to - f.date_from).days > 62:
        raise HTTPException(422, "export is limited to 62 days")
    async with st.pool.connection() as conn:
        content = await build_workbook(conn, f, st.cfg.plant.name)
    shift = f"_{f.shift}" if f.shift else ""
    name = f"checkweigher_{f.date_from:%Y%m%d}-{f.date_to:%Y%m%d}{shift}.xlsx"
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
