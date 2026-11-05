"""Simulated indicator state: product generation, judgement, counters and register images."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from checkweigher.device import registers as R
from checkweigher.device.protocol import format_result_line


@dataclass(frozen=True)
class SimProduct:
    group_no: int
    product_no: int
    target: Decimal
    hihi: Decimal
    hi: Decimal
    lo: Decimal
    lolo: Decimal
    tare: Decimal = Decimal(0)
    decimal_point: int = 1
    ow_exception: bool = False
    reject_stage: int = 0  # 0: 3-stage, 1: 5-stage

    @classmethod
    def around(cls, target: float, group_no: int = 1, product_no: int = 1, decimal_point: int = 1) -> SimProduct:
        t = Decimal(str(target))

        def d(pct: str) -> Decimal:
            return (t * Decimal(pct)).quantize(Decimal(1).scaleb(-decimal_point))

        return cls(group_no, product_no, t, t + d("0.03"), t + d("0.012"), t - d("0.006"), t - d("0.02"),
                   decimal_point=decimal_point)


DEFAULT_PRODUCTS = [SimProduct.around(500, 1, 1), SimProduct.around(250, 1, 2), SimProduct.around(1000, 2, 1)]


@dataclass
class Piece:
    judgement: str
    weight: Decimal | None
    line: str


@dataclass
class SimIndicator:
    product: SimProduct
    sd: float = 1.6
    bias: float = 2.5
    td_rate: float = 0.008
    us_rate: float = 0.004
    md_rate: float = 0.0008
    unit: str = "g"
    seed: int | None = None
    rng: random.Random = field(init=False)
    counters: dict[str, int] = field(init=False)
    sum_w: Decimal = field(init=False, default=Decimal(0))
    sum_w2: Decimal = field(init=False, default=Decimal(0))
    min_w: Decimal | None = field(init=False, default=None)
    max_w: Decimal | None = field(init=False, default=None)
    last_weight: Decimal = field(init=False, default=Decimal(0))
    _walk: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        self.clear_summary()

    def clear_summary(self) -> None:
        self.counters = dict.fromkeys(("total", "ok", "hihi", "hi", "lo", "lolo", "detect_two", "unsplit",
                                       "foreign"), 0)
        self.sum_w = self.sum_w2 = Decimal(0)
        self.min_w = self.max_w = None

    def _judge(self, w: Decimal) -> str:
        p = self.product
        if w > p.hihi:
            return "HH"
        if w > p.hi:
            return "HI"
        if w < p.lolo:
            return "LL"
        if w < p.lo:
            return "LO"
        return "OK"

    def _weight(self, t: float) -> Decimal:
        # Slow filler drift (sinusoid + bounded random walk) on top of process noise.
        self._walk = max(-1.5, min(1.5, self._walk + self.rng.gauss(0, 0.02)))
        drift = 1.0 * math.sin(2 * math.pi * t / 5400.0) + self._walk
        scale = float(self.product.target) / 500.0
        w = float(self.product.target) + (self.bias + drift) * scale + self.rng.gauss(0, self.sd * scale)
        q = Decimal(1).scaleb(-self.product.decimal_point)
        return Decimal(str(w)).quantize(q, rounding=ROUND_HALF_UP)

    def next_piece(self, t: float) -> Piece:
        c = self.counters
        c["total"] += 1
        r = self.rng.random()
        if r < self.td_rate + self.us_rate:
            judgement = "TD" if r < self.td_rate else "US"
            c["detect_two" if judgement == "TD" else "unsplit"] += 1
            return Piece(judgement, None, format_result_line(None, judgement, None, 0))
        w = self._weight(t)
        judgement = "MD" if self.rng.random() < self.md_rate else self._judge(w)
        c[{"OK": "ok", "HH": "hihi", "HI": "hi", "LO": "lo", "LL": "lolo", "MD": "foreign"}[judgement]] += 1
        self.last_weight = w
        self.sum_w += w
        self.sum_w2 += w * w
        self.min_w = w if self.min_w is None else min(self.min_w, w)
        self.max_w = w if self.max_w is None else max(self.max_w, w)
        return Piece(judgement, w, format_result_line(c["total"], judgement, w, self.product.decimal_point,
                                                      self.unit))

    # ---- register images (manual Table 18 / 19) --------------------------------------------------
    def input_block(self, codec: R.Codec) -> list[int]:
        regs = [0] * R.IR_BLOCK_COUNT
        dp = self.product.decimal_point

        def put(addr: int, words: list[int]) -> None:
            i = addr - R.IR_BLOCK_START
            regs[i : i + len(words)] = words

        c = self.counters
        for addr, key in ((R.IR_ALL_TOTAL, "total"), (R.IR_ALL_OK, "ok"), (R.IR_ALL_HIHI, "hihi"),
                          (R.IR_ALL_HI, "hi"), (R.IR_ALL_LO, "lo"), (R.IR_ALL_LOLO, "lolo"),
                          (R.IR_ALL_DETECT_TWO, "detect_two"), (R.IR_ALL_UNSPLIT, "unsplit"),
                          (R.IR_ALL_FOREIGN, "foreign")):
            put(addr, codec.encode_u32(c[key]))
        weighed = c["total"] - c["detect_two"] - c["unsplit"]
        if weighed:
            put(R.IR_ALL_TOTAL_WEIGHT, codec.encode_value(min(self.sum_w / 1000, Decimal("9999.9")), dp))
            put(R.IR_ALL_AVERAGE, codec.encode_value(self.sum_w / weighed, dp))
            put(R.IR_ALL_MAX, codec.encode_value(self.max_w or Decimal(0), dp))
            put(R.IR_ALL_MIN, codec.encode_value(self.min_w or Decimal(0), dp))
        put(R.IR_WEIGHING_RESULT, codec.encode_value(self.last_weight, dp))
        return regs

    def holding_ids(self) -> list[int]:
        return [self.product.product_no, self.product.group_no]

    def holding_product_block(self, codec: R.Codec) -> list[int]:
        p = self.product
        regs = [0] * R.HR_PRODUCT_BLOCK_COUNT

        def put(addr: int, words: list[int]) -> None:
            i = addr - R.HR_PRODUCT_BLOCK_START
            regs[i : i + len(words)] = words

        put(R.HR_DECIMAL_POINT, [p.decimal_point])
        put(R.HR_CAPACITY, codec.encode_value(Decimal(6000), p.decimal_point))
        put(R.HR_REJECT_STAGE, [p.reject_stage])
        for addr, v in ((R.HR_TARGET, p.target), (R.HR_HIHI, p.hihi), (R.HR_HI, p.hi), (R.HR_LO, p.lo),
                        (R.HR_LOLO, p.lolo), (R.HR_TARE, p.tare)):
            put(addr, codec.encode_value(v, p.decimal_point))
        put(R.HR_OW_EXCEPTION, [int(p.ow_exception)])
        put(R.HR_PRODUCT_LENGTH, [200])
        put(R.HR_SPEED, [60])
        return regs
