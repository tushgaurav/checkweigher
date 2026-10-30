from decimal import Decimal

import pytest

from checkweigher.device.protocol import ParseError, format_result_line, parse_result_line


@pytest.mark.parametrize(
    ("line", "seq", "judgement", "header", "weight", "unit"),
    [
        # Examples from manual §9.25
        ("00001,OK,ST,+00012.345 g", 1, "OK", "ST", Decimal("12.345"), "g"),
        ("00001,HH,ST,+00012.345 g\r\n", 1, "HH", "ST", Decimal("12.345"), "g"),
        ("00001,LO,ST,+00012.345 g", 1, "LO", "ST", Decimal("12.345"), "g"),
        ("00004,E1,ST,+00012.345 g", 4, "E1", "ST", Decimal("12.345"), "g"),
        ("00006,MD,ST,+00012.345 g", 6, "MD", "ST", Decimal("12.345"), "g"),
        ("*****,TD,**,**********  ", None, "TD", None, None, None),
        ("*****,US,**,**********  ", None, "US", None, None, None),
        ("00010,HI,US,+00005.432 g", 10, "HI", "US", Decimal("5.432"), "g"),
        ("00011,HH,OL,+9999999E+19", 11, "HH", "OL", None, None),
        ("00012,OK,ST,-00000.120kg", 12, "OK", "ST", Decimal("-0.120"), "kg"),
    ],
)
def test_parse_manual_examples(line, seq, judgement, header, weight, unit):
    r = parse_result_line(line)
    assert (r.seq, r.judgement, r.header, r.weight, r.unit) == (seq, judgement, header, weight, unit)


def test_weight_grams_conversion():
    assert parse_result_line("00012,OK,ST,+00001.250kg").weight_grams() == Decimal("1250.000")
    assert parse_result_line("00012,OK,ST,+0000500.5 g").weight_grams() == Decimal("500.5")
    assert parse_result_line("*****,TD,**,**********  ").weight_grams() is None


@pytest.mark.parametrize("line", ["ST,+00012.345  g", "garbage", "0000x,OK,ST,+1.0 g", "00001,O,ST,+1.0 g",
                                  "00001,OK,ST,abc g"])
def test_parse_rejects_bad_lines(line):
    with pytest.raises(ParseError):
        parse_result_line(line)


def test_ad_format_hint():
    with pytest.raises(ParseError, match="Cyclic Print"):
        parse_result_line("ST,+00012.345  g")


def test_format_roundtrip_is_24_chars():
    line = format_result_line(1, "OK", Decimal("12.345"), 3)
    assert line == "00001,OK,ST,+00012.345 g"
    assert len(line) == 24
    assert len(format_result_line(None, "TD", None, 0)) == 24
    assert parse_result_line(format_result_line(123456, "LO", Decimal("498.7"), 1)).seq == 23456
