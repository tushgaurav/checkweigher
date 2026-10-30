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


def test_block_bounds():
    b = R.Block(190, [0] * 4, R.Codec())
    assert b.u32(192) == 0
    with pytest.raises(IndexError):
        b.u16(194)
