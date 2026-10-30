from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from checkweigher.device.protocol import UNIT_TO_GRAMS
from checkweigher.device.registers import ProductSettings


@dataclass(frozen=True, slots=True)
class ProductContext:
    """Product settings in effect on a machine, converted to grams."""

    product_id: int | None
    group_no: int
    product_no: int
    target_g: Decimal
    hihi_g: Decimal
    hi_g: Decimal
    lo_g: Decimal
    lolo_g: Decimal
    tare_g: Decimal
    ow_exception: bool
    reject_stage: int

    @classmethod
    def from_settings(cls, s: ProductSettings, unit: str, product_id: int | None = None) -> ProductContext:
        k = UNIT_TO_GRAMS[unit]
        return cls(
            product_id=product_id,
            group_no=s.group_no,
            product_no=s.product_no,
            target_g=s.target * k,
            hihi_g=s.hihi * k,
            hi_g=s.hi * k,
            lo_g=s.lo * k,
            lolo_g=s.lolo * k,
            tare_g=s.tare * k,
            ow_exception=s.ow_exception,
            reject_stage=s.reject_stage,
        )

    def key(self) -> tuple:
        return (self.group_no, self.product_no, self.target_g, self.hihi_g, self.hi_g, self.lo_g,
                self.lolo_g, self.tare_g, self.ow_exception, self.reject_stage)

    def judge(self, weight_g: Decimal) -> str:
        """Weight judgement from limits ("bigger than" / "smaller than", manual Table 5)."""
        if weight_g > self.hihi_g:
            return "HH"
        if weight_g > self.hi_g:
            return "HI"
        if weight_g < self.lolo_g:
            return "LL"
        if weight_g < self.lo_g:
            return "LO"
        return "OK"


@dataclass(slots=True)
class WeighingRecord:
    ts: datetime
    machine_id: int
    seq: int | None
    judgement: str
    weight_g: Decimal | None
    target_g: Decimal | None
    product_id: int | None
    shift_date: date
    shift_code: str
    source: str
    raw: str | None = None

    def as_row(self) -> tuple:
        return (self.ts, self.machine_id, self.seq, self.judgement, self.weight_g, self.target_g,
                self.product_id, self.shift_date, self.shift_code, self.source, self.raw)

    def to_json(self) -> dict:
        return {
            "ts": self.ts.isoformat(), "machine_id": self.machine_id, "seq": self.seq,
            "judgement": self.judgement, "weight_g": None if self.weight_g is None else str(self.weight_g),
            "target_g": None if self.target_g is None else str(self.target_g), "product_id": self.product_id,
            "shift_date": self.shift_date.isoformat(), "shift_code": self.shift_code, "source": self.source,
            "raw": self.raw,
        }

    @classmethod
    def from_json(cls, d: dict) -> WeighingRecord:
        return cls(
            ts=datetime.fromisoformat(d["ts"]), machine_id=d["machine_id"], seq=d["seq"],
            judgement=d["judgement"], weight_g=None if d["weight_g"] is None else Decimal(d["weight_g"]),
            target_g=None if d["target_g"] is None else Decimal(d["target_g"]), product_id=d["product_id"],
            shift_date=date.fromisoformat(d["shift_date"]), shift_code=d["shift_code"], source=d["source"],
            raw=d["raw"],
        )
