"""Checkweigher-wise Excel export.

Generic layout until the client's template is available: a Summary sheet with
the dashboard KPIs, then one sheet of individual weighings per machine.
"""

from __future__ import annotations

import io
from dataclasses import replace
from datetime import datetime

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font
from psycopg import AsyncConnection

from checkweigher.api import data
from checkweigher.api.filters import Filters
from checkweigher.api.schemas import KPIs

KPI_ROWS: list[tuple[str, str, str]] = [
    ("Products judged", "total", "0"),
    ("Passed", "passed", "0"),
    ("Rejected", "rejected", "0"),
    ("Overweight", "overweight", "0"),
    ("Underweight", "underweight", "0"),
    ("Feeding errors (detect two + unsplit)", "feeding_errors", "0"),
    ("Metal detected", "metal", "0"),
    ("EGA %", "ega_pct", "0.000"),
    ("EGA g/pack", "ega_g_per_pack", "0.00"),
    ("Overweight %", "overweight_pct", "0.00"),
    ("Underweight %", "underweight_pct", "0.00"),
    ("Feeding error %", "feeding_error_pct", "0.00"),
    ("Quantity (kg)", "quantity_kg", "#,##0.000"),
    ("Passed quantity (kg)", "passed_kg", "#,##0.000"),
    ("Mean (g)", "mean_g", "0.00"),
    ("Median (g)", "median_g", "0.00"),
    ("Mode (g)", "mode_g", "0.00"),
    ("Standard deviation (g)", "sd_g", "0.000"),
    ("Min (g)", "min_g", "0.00"),
    ("Max (g)", "max_g", "0.00"),
]


def _bold(ws, value) -> WriteOnlyCell:
    c = WriteOnlyCell(ws, value=value)
    c.font = Font(bold=True)
    return c


async def build_workbook(conn: AsyncConnection, f: Filters, plant_name: str) -> bytes:
    summary = await data.summary(conn, f)
    wb = Workbook(write_only=True)

    ws = wb.create_sheet("Summary")
    ws.append([_bold(ws, f"{plant_name} - Checkweigher report")])
    ws.append(["Production dates", f"{f.date_from:%d-%m-%Y} to {f.date_to:%d-%m-%Y}"])
    ws.append(["Shift", f.shift or "All"])
    ws.append(["Generated", datetime.now(f.tz).strftime("%d-%m-%Y %H:%M")])
    ws.append([])
    columns: list[tuple[str, KPIs]] = [("All selected", summary.overall)]
    columns += [(m.machine.code, m.kpis) for m in summary.machines]
    ws.append([_bold(ws, "KPI")] + [_bold(ws, name) for name, _ in columns])
    for label, key, fmt in KPI_ROWS:
        row: list = [label]
        for _, k in columns:
            c = WriteOnlyCell(ws, value=getattr(k, key))
            c.number_format = fmt
            row.append(c)
        ws.append(row)

    products = {p.id: p for p in summary.products}
    for m in summary.machines:
        sheet = wb.create_sheet(m.machine.code[:31])
        sheet.append([_bold(sheet, h) for h in ("Date", "Time", "Shift", "Product", "Target (g)", "Weight (g)",
                                               "Judgement", "Seq")])
        mf = replace(f, machine_ids=[m.machine.id])
        where, params = mf.where()
        async with conn.transaction(), conn.cursor(name=f"export_{m.machine.id}") as cur:
            await cur.execute(f"SELECT ts, shift_code, product_id, target_g, weight_g, judgement, seq "
                              f"FROM weighing WHERE {where} ORDER BY ts", params)
            async for r in cur:
                local = r["ts"].astimezone(f.tz).replace(tzinfo=None)
                p = products.get(r["product_id"])
                sheet.append([local.date(), local.time().replace(microsecond=0), r["shift_code"],
                              f"G{p.group_no}-P{p.product_no}" if p else None,
                              None if r["target_g"] is None else float(r["target_g"]),
                              None if r["weight_g"] is None else float(r["weight_g"]), r["judgement"], r["seq"]])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
