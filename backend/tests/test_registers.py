from decimal import Decimal

import pytest

from checkweigher.device import registers as R


def test_manual_example_low_word_first():
    # Manual §10.3.1: total number 1000 is returned as Data1=0x03E8, Data2=0x0000.
    assert R.Codec("little").u32(0x03E8, 0x0000) == 1000
    assert R.Codec("big").u32(0x0000, 0x03E8) == 1000


def test_offsets_are_address_minus_one():
    assert R.offset(R.IR_ALL_TOTAL) == 189
    assert R.offset(R.HR_PRODUCT_NO) == 0
    assert R.IR_BLOCK_START + R.IR_BLOCK_COUNT - 1 == R.IR_WEIGHING_RESULT + 1


@pytest.mark.parametrize("word_order", ["little", "big"])
@pytest.mark.parametrize("encoding", ["scaled_int", "float32"])
@pytest.mark.parametrize("value", ["500.0", "-12.5", "0.0", "9999.9"])
def test_value_roundtrip(word_order, encoding, value):
    c = R.Codec(word_order, encoding)
    words = c.encode_value(Decimal(value), 1)
    assert c.value(words[0], words[1], 1) == Decimal(value)


def test_signed_scaled_int():
    c = R.Codec("little", "scaled_int")
    assert c.value(0xFF9C, 0xFFFF, 2) == Decimal("-1.00")


# Site 1 (AD-4412-CW, 2026-11-05) dumps of IR 214..233 before/after 10 products, all judged Hi.
SITE1_BEFORE = "0000 0000 0149 0000 00a6 0000 0000 0000 0024 0000 002c 0000 0000 0000 0025 0000 002c 0000 0000 0000"
SITE1_AFTER = "08b2 0000 0153 0000 00a6 0000 0000 0000 002e 0000 002c 0000 0000 0000 0025 0000 002c 0000 0000 0000"
SITE1 = R.Layout(summary=216, weighing_result=214, product_settings=None)


def test_site1_firmware_layout_decodes_real_dump():
    start, count = SITE1.ir_span(with_weight=True)
    assert (start, count) == (214, 20)

    def counters(dump: str) -> R.Counters:
        return R.Counters.from_block(R.Block(start, [int(w, 16) for w in dump.split()], R.Codec()), SITE1.summary)

    before, after = counters(SITE1_BEFORE), counters(SITE1_AFTER)
    assert (after.total, after.ok, after.hi, after.lo, after.detect_two, after.unsplit) == (339, 166, 46, 44, 37, 44)
    assert after.total - before.total == after.hi - before.hi == 10
    assert after.total - sum(after.by_judgement().values()) == 2  # a counter the manual does not list (IR 240)
    weight = R.Block(start, [int(w, 16) for w in SITE1_AFTER.split()], R.Codec()).value(SITE1.weighing_result, 1)
    assert weight == Decimal("222.6")


def test_product_settings_follow_a_shifted_block():
    codec = R.Codec()
    regs = [0] * R.HR_PRODUCT_BLOCK_COUNT
    regs[0] = 1  # decimal point
    regs[R.HR_TARGET - R.HR_PRODUCT_BLOCK_START : R.HR_TARGET - R.HR_PRODUCT_BLOCK_START + 2] = [1250, 0]
    s = R.ProductSettings.from_blocks(R.Block(R.HR_PRODUCT_NO, [3, 2], codec), R.Block(700, regs, codec))
    assert (s.product_no, s.group_no, s.decimal_point, s.target) == (3, 2, 1, Decimal("125.0"))


def test_block_bounds():
    b = R.Block(190, [0] * 4, R.Codec())
    assert b.u32(192) == 0
    with pytest.raises(IndexError):
        b.u16(194)
