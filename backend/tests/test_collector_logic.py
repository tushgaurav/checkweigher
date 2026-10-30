from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from checkweigher.collector.modbus_only import UNKNOWN, CounterDeltaTracker
from checkweigher.collector.models import ProductContext
from checkweigher.collector.reconcile import Reconciler
from checkweigher.collector.sequence import SequenceTracker
from checkweigher.device.registers import Counters

D = Decimal
CTX = ProductContext(product_id=1, group_no=1, product_no=1, target_g=D(500), hihi_g=D(515), hi_g=D(506),
                     lo_g=D(497), lolo_g=D(490), tare_g=D(0), ow_exception=False, reject_stage=0)
ZERO = Counters(0, 0, 0, 0, 0, 0, 0, 0, 0)


def counters(**kw) -> Counters:
    c = replace(ZERO, **kw)
    return replace(c, total=kw.get("total", c.ok + c.hihi + c.hi + c.lo + c.lolo + c.detect_two + c.unsplit
                                    + c.foreign))


# ---- sequence ------------------------------------------------------------------------------------
def test_sequence_contiguous_and_gap():
    t = SequenceTracker()
    assert [t.observe(s) for s in (1, 2, 3)] == [None, None, None]
    ev = t.observe(6)
    assert ev and ev.kind == "gap" and ev.missing == 2


def test_sequence_unnumbered_feeding_errors_are_not_gaps():
    t = SequenceTracker()
    t.observe(10)
    t.observe(None)  # TD line (may or may not advance the counter)
    assert t.observe(12) is None
    t.observe(None)
    assert t.observe(13) is None


def test_sequence_reset_and_wrap():
    t = SequenceTracker()
    t.observe(500)
    ev = t.observe(1)
    assert ev and ev.kind == "reset"
    t = SequenceTracker()
    t.observe(99998)
    assert t.observe(99999) is None
    assert t.observe(0) is None
    ev = t.observe(3)
    assert ev and ev.kind == "gap" and ev.missing == 2


def test_sequence_duplicate():
    t = SequenceTracker()
    t.observe(5)
    ev = t.observe(5)
    assert ev and ev.kind == "duplicate"


# ---- reconciliation ------------------------------------------------------------------------------
def test_reconciler_windows_and_clear():
    r = Reconciler()
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    assert r.check(counters(ok=10), t0) == (None, False)
    for _ in range(4):
        r.on_record("OK")
    r.on_record("HI")
    w, cleared = r.check(counters(ok=15, hi=1), t0 + timedelta(seconds=30))
    assert not cleared and w is not None
    assert (w.expected, w.received) == (6, 5)
    assert w.expected_by_judgement == {"OK": 5, "HI": 1}
    w, cleared = r.check(counters(ok=2), t0 + timedelta(seconds=60))
    assert cleared and w is None


# ---- modbus-only derivation ----------------------------------------------------------------------
def test_modbus_only_single_piece_gets_weight():
    t = CounterDeltaTracker()
    assert t.update(counters(ok=5), D("501.0"), CTX).pieces == []
    res = t.update(counters(ok=6), D("502.1"), CTX)
    assert res.pieces == [("OK", D("502.1"))] and res.missed_weights == 0


def test_modbus_only_multiple_pieces_counts_exact_weight_attached_once():
    t = CounterDeltaTracker()
    t.update(counters(ok=5), None, CTX)
    res = t.update(counters(ok=7, hi=1, detect_two=1), D("508.0"), CTX)
    js = sorted(j for j, _ in res.pieces)
    assert js == ["HI", "OK", "OK", "TD"]
    weighted = [(j, w) for j, w in res.pieces if w is not None]
    assert weighted == [("HI", D("508.0"))]
    assert res.missed_weights == 2
    assert res.pieces[-1] == ("HI", D("508.0"))


def test_modbus_only_inconsistent_weight_not_attached():
    t = CounterDeltaTracker()
    t.update(counters(ok=5), None, CTX)
    # counter says LO but the register still holds an OK weight -> stale, do not attach
    res = t.update(counters(ok=5, lo=1), D("501.0"), CTX)
    assert res.pieces == [("LO", None)]


def test_modbus_only_reset_and_unknown():
    t = CounterDeltaTracker()
    t.update(counters(ok=5), None, CTX)
    assert t.update(counters(ok=1), None, CTX).reset
    t.update(counters(ok=1), None, CTX)
    res = t.update(counters(ok=1, total=3), None, CTX)  # e.g. E1/E2 not in any counter
    assert [j for j, _ in res.pieces] == [UNKNOWN, UNKNOWN]


def test_context_judge_boundaries():
    assert CTX.judge(D(506)) == "OK" and CTX.judge(D("506.1")) == "HI"
    assert CTX.judge(D(497)) == "OK" and CTX.judge(D("496.9")) == "LO"
    assert CTX.judge(D("515.1")) == "HH" and CTX.judge(D("489.9")) == "LL"
