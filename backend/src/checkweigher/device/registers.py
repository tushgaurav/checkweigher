"""Modbus register map (manual §10.5, Tables 18 and 19) and value decoding.

Addresses below are the manual's 1-based addresses. The protocol offset sent on
the wire is ``address - 1`` (manual §10, caution 5).

4-byte values span two registers. The §10.3.1 example returns 1000 as
``[0x03E8, 0x0000]``, i.e. low word first. How decimal values (weights) are
encoded is not stated in the manual; ``scaled_int`` assumes a signed 32-bit
integer scaled by the product decimal point (holding register 619).
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
    def from_block(cls, b: Block) -> Counters:
        return cls(
            total=b.u32(IR_ALL_TOTAL),
            ok=b.u32(IR_ALL_OK),
            hihi=b.u32(IR_ALL_HIHI),
            hi=b.u32(IR_ALL_HI),
            lo=b.u32(IR_ALL_LO),
            lolo=b.u32(IR_ALL_LOLO),
            detect_two=b.u32(IR_ALL_DETECT_TWO),
            unsplit=b.u32(IR_ALL_UNSPLIT),
            foreign=b.u32(IR_ALL_FOREIGN),
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
        dp = product.u16(HR_DECIMAL_POINT)
        return cls(
            group_no=ids.u16(HR_GROUP_NO),
            product_no=ids.u16(HR_PRODUCT_NO),
            decimal_point=dp,
            target=product.value(HR_TARGET, dp),
            hihi=product.value(HR_HIHI, dp),
            hi=product.value(HR_HI, dp),
            lo=product.value(HR_LO, dp),
            lolo=product.value(HR_LOLO, dp),
            tare=product.value(HR_TARE, dp),
            ow_exception=bool(product.u16(HR_OW_EXCEPTION)),
            reject_stage=product.u16(HR_REJECT_STAGE),
        )
