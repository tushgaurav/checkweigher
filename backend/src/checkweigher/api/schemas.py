from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel


class MachineRef(BaseModel):
    id: int
    code: str
    name: str
    mode: str


class ShiftRef(BaseModel):
    code: str
    name: str
    start_time: time
    end_time: time


class Meta(BaseModel):
    plant_name: str
    timezone: str
    today: date
    current_shift: str
    server_time: datetime
    timescale: bool
    machines: list[MachineRef]
    shifts: list[ShiftRef]
    judgements: dict[str, str]


class KPIs(BaseModel):
    total: int
    weighed: int
    passed: int
    rejected: int
    overweight: int
    overweight_hihi: int
    underweight: int
    underweight_lolo: int
    feeding_errors: int
    detect_two: int
    unsplit: int
    metal: int
    external: int
    overweight_pct: float | None
    underweight_pct: float | None
    rejected_pct: float | None
    feeding_error_pct: float | None
    ega_pct: float | None
    ega_g_per_pack: float | None
    quantity_kg: float
    passed_kg: float
    giveaway_kg: float
    mean_g: float | None
    mean_target_g: float | None
    mean_dev_g: float | None
    sd_g: float | None
    sd_vs_target_g: float | None
    min_g: float | None
    max_g: float | None
    median_g: float | None
    mode_g: float | None
    mode_count: int | None


class LastWeight(BaseModel):
    machine_id: int
    ts: datetime
    weight_g: float | None
    judgement: str


class Completeness(BaseModel):
    expected: int
    received: int
    pct: float | None


class Product(BaseModel):
    id: int
    machine_id: int
    group_no: int
    product_no: int
    target_g: float | None
    hihi_g: float | None
    hi_g: float | None
    lo_g: float | None
    lolo_g: float | None
    n: int


class MachineSummary(BaseModel):
    machine: MachineRef
    kpis: KPIs
    last: LastWeight | None
    completeness: Completeness | None


class Summary(BaseModel):
    date_from: date
    date_to: date
    shift: str | None
    machine_ids: list[int]
    overall: KPIs
    last: LastWeight | None
    completeness: Completeness | None
    machines: list[MachineSummary]
    products: list[Product]


class TrendPoint(BaseModel):
    t: datetime
    label: str
    total: int
    passed: int
    mean_g: float | None
    sd_g: float | None
    sd_vs_target_g: float | None
    min_g: float | None
    max_g: float | None
    mean_target_g: float | None
    overweight_pct: float | None
    underweight_pct: float | None
    rejected_pct: float | None
    feeding_error_pct: float | None
    ega_pct: float | None


class Trend(BaseModel):
    interval: str
    points: list[TrendPoint]


class HistogramBin(BaseModel):
    lo: float
    hi: float
    n: int


class Histogram(BaseModel):
    bins: list[HistogramBin]
    bin_width: float | None
    total: int
    product: Product | None


class Weighing(BaseModel):
    ts: datetime
    machine_id: int
    seq: int | None
    judgement: str
    weight_g: float | None
    target_g: float | None
    product_id: int | None
    shift_date: date
    shift_code: str
    source: str


class Weighings(BaseModel):
    rows: list[Weighing]
    next_before: datetime | None


class Event(BaseModel):
    id: int
    ts: datetime
    machine_id: int | None
    kind: str
    message: str
    detail: dict[str, Any] | None


class MachineStatus(BaseModel):
    machine_id: int
    online: bool
    serial_state: str | None
    modbus_state: str | None
    last_line_at: datetime | None
    last_modbus_at: datetime | None
    last_ts: datetime | None
    last_weight_g: float | None
    last_judgement: str | None
    last_seq: int | None
    product_id: int | None
    device_counters: dict[str, Any] | None
    updated_at: datetime


class Health(BaseModel):
    ok: bool
    database: bool
    timescale: bool
    collector_age_s: float | None
