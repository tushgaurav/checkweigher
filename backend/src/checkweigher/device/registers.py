"""Modbus register map (manual §10.5, Tables 18 and 19) and value decoding.

Addresses below are the manual's 1-based addresses. The protocol offset sent on
the wire is ``address - 1`` (manual §10, caution 5).

4-byte values span two registers. The §10.3.1 example returns 1000 as
``[0x03E8, 0x0000]``, i.e. low word first. How decimal values (weights) are
encoded is not stated in the manual; ``scaled_int`` assumes a signed 32-bit
integer scaled by the product decimal point (holding register 619).

Some firmware inserts registers the manual does not list, which shifts whole
blocks (see :class:`Layout`). Field order inside a block stays the manual's.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

WordOrder = Literal["little", "big"]
ValueEncoding = Literal["scaled_int", "float32"]

# ---- Input registers (function 04) -------------------------------------------------------------
IR_BLOCK_START = 190  # "All summary" ... "Weighing result" in one read
IR_BLOCK_COUNT = 94  # 190..283

IR_ALL_TOTAL = 190
IR_ALL_OK = 192
IR_ALL_HIHI = 194
IR_ALL_HI = 196
IR_ALL_LO = 198
IR_ALL_LOLO = 200
IR_ALL_DETECT_TWO = 202
IR_ALL_UNSPLIT = 204
IR_ALL_FOREIGN = 206
IR_ALL_TOTAL_WEIGHT = 208
IR_ALL_AVERAGE = 210
IR_ALL_MAX = 212
IR_ALL_MIN = 214
IR_WEIGHING_RESULT = 282
COUNTERS_COUNT = IR_ALL_FOREIGN + 2 - IR_ALL_TOTAL  # total .. foreign matter: 9 x 4 bytes
MAX_READ = 125  # Modbus limit for one register read

# ---- Holding registers (function 03) ------------------------------------------------------------
HR_PRODUCT_NO = 1
HR_GROUP_NO = 2
HR_PRODUCT_BLOCK_START = 619  # decimal point .. tare
HR_PRODUCT_BLOCK_COUNT = 70  # 619..688

HR_DECIMAL_POINT = 619
HR_DIVISION = 620
HR_CAPACITY = 621
HR_REJECT_STAGE = 644
HR_TARGET = 645
HR_HIHI = 647
HR_HI = 649
HR_LO = 651
HR_LOLO = 653
HR_OW_EXCEPTION = 655
HR_PRODUCT_LENGTH = 658
HR_SPEED = 659
HR_TARE = 687

# Summary counters -> serial judgement code they correspond to.
COUNTER_JUDGEMENTS: dict[str, str] = {
    "ok": "OK",
    "hihi": "HH",
    "hi": "HI",
    "lo": "LO",
    "lolo": "LL",
    "detect_two": "TD",
    "unsplit": "US",
    "foreign": "MD",
}


def offset(address: int) -> int:
    return address - 1


@dataclass(frozen=True)
class Layout:
    """Where a firmware keeps the blocks the collector reads (1-based addresses).

    Defaults are the manual's. ``None`` means the block is not available on that firmware.
    """

    summary: int = IR_ALL_TOTAL  # IR "All summary - Total number"; the 8 category counters follow
    weighing_result: int | None = IR_WEIGHING_RESULT  # IR last weighing result (4 bytes)
    product_settings: int | None = HR_PRODUCT_BLOCK_START  # HR "Decimal point", first of the product block

    def ir_span(self, with_weight: bool) -> tuple[int, int]:
        """(start, count) of one input-register read covering the counters and, optionally, the weight."""
        parts = [(self.summary, COUNTERS_COUNT)]
        if with_weight and self.weighing_result is not None:
            parts.append((self.weighing_result, 2))
        start = min(a for a, _ in parts)
        return start, max(a + n for a, n in parts) - start


MANUAL = Layout()


class Codec:
    def __init__(self, word_order: WordOrder = "little", value_encoding: ValueEncoding = "scaled_int"):
        self.word_order = word_order
        self.value_encoding = value_encoding

    def _words(self, lo_addr_word: int, hi_addr_word: int) -> tuple[int, int]:
        """Return (high word, low word) for the two registers in address order."""
        return (hi_addr_word, lo_addr_word) if self.word_order == "little" else (lo_addr_word, hi_addr_word)

    def u32(self, w0: int, w1: int) -> int:
        hi, lo = self._words(w0, w1)
        return (hi << 16) | lo

    def s32(self, w0: int, w1: int) -> int:
        v = self.u32(w0, w1)
        return v - (1 << 32) if v & 0x8000_0000 else v

    def value(self, w0: int, w1: int, decimals: int) -> Decimal:
        if self.value_encoding == "float32":
            hi, lo = self._words(w0, w1)
            f = struct.unpack(">f", struct.pack(">HH", hi, lo))[0]
            return Decimal(repr(f)).quantize(Decimal(1).scaleb(-decimals))
        return Decimal(self.s32(w0, w1)).scaleb(-decimals)

    # -- encoding (simulator) --
    def encode_u32(self, v: int) -> list[int]:
        hi, lo = (v >> 16) & 0xFFFF, v & 0xFFFF
        return [lo, hi] if self.word_order == "little" else [hi, lo]

    def encode_value(self, v: Decimal, decimals: int) -> list[int]:
        if self.value_encoding == "float32":
            hi, lo = struct.unpack(">HH", struct.pack(">f", float(v)))
            return [lo, hi] if self.word_order == "little" else [hi, lo]
        return self.encode_u32(int(v.scaleb(decimals).to_integral_value()) & 0xFFFF_FFFF)


@dataclass(frozen=True)
class Block:
    """Registers read starting at a 1-based manual address."""

    start: int
    regs: list[int]
    codec: Codec

    def _i(self, address: int) -> int:
        i = address - self.start
        if not 0 <= i < len(self.regs):
            raise IndexError(f"address {address} outside block {self.start}..{self.start + len(self.regs) - 1}")
        return i

    def u16(self, address: int) -> int:
        return self.regs[self._i(address)]

    def u32(self, address: int) -> int:
        i = self._i(address)
        return self.codec.u32(self.regs[i], self.regs[i + 1])

    def value(self, address: int, decimals: int) -> Decimal:
        i = self._i(address)
        return self.codec.value(self.regs[i], self.regs[i + 1], decimals)


@dataclass(frozen=True)
class Counters:
    """"All summary" totals from the indicator (reset when the operator clears the summary)."""

    total: int
    ok: int
    hihi: int
    hi: int
    lo: int
    lolo: int
    detect_two: int
    unsplit: int
    foreign: int

    @classmethod
    def from_block(cls, b: Block, summary: int = IR_ALL_TOTAL) -> Counters:
        """``summary``: address of the total counter on this firmware (see :class:`Layout`)."""
        at = summary - IR_ALL_TOTAL
        return cls(
            total=b.u32(IR_ALL_TOTAL + at),
            ok=b.u32(IR_ALL_OK + at),
            hihi=b.u32(IR_ALL_HIHI + at),
            hi=b.u32(IR_ALL_HI + at),
            lo=b.u32(IR_ALL_LO + at),
            lolo=b.u32(IR_ALL_LOLO + at),
            detect_two=b.u32(IR_ALL_DETECT_TWO + at),
            unsplit=b.u32(IR_ALL_UNSPLIT + at),
            foreign=b.u32(IR_ALL_FOREIGN + at),
        )

    def by_judgement(self) -> dict[str, int]:
        return {code: getattr(self, name) for name, code in COUNTER_JUDGEMENTS.items()}


@dataclass(frozen=True)
class ProductSettings:
    """Active product settings read from holding registers, in the indicator's unit."""

    group_no: int
    product_no: int
    decimal_point: int
    target: Decimal
    hihi: Decimal
    hi: Decimal
    lo: Decimal
    lolo: Decimal
    tare: Decimal
    ow_exception: bool
    reject_stage: int

    @classmethod
    def from_blocks(cls, ids: Block, product: Block) -> ProductSettings:
        """``product`` must start at the product block's first register, wherever the firmware keeps it."""
        at = product.start - HR_PRODUCT_BLOCK_START
        dp = product.u16(HR_DECIMAL_POINT + at)
        return cls(
            group_no=ids.u16(HR_GROUP_NO),
            product_no=ids.u16(HR_PRODUCT_NO),
            decimal_point=dp,
            target=product.value(HR_TARGET + at, dp),
            hihi=product.value(HR_HIHI + at, dp),
            hi=product.value(HR_HI + at, dp),
            lo=product.value(HR_LO + at, dp),
            lolo=product.value(HR_LOLO + at, dp),
            tare=product.value(HR_TARE + at, dp),
            ow_exception=bool(product.u16(HR_OW_EXCEPTION + at)),
            reject_stage=product.u16(HR_REJECT_STAGE + at),
        )
