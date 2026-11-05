"""On-site probe for A&D AD-4412/4413-CW indicators. Read-only on both links.

Run from backend/ so the checkweigher package (parser, register map, codec) is importable:

  uv run --no-sync python ../scripts/probe.py ports
  uv run --no-sync python ../scripts/probe.py serial COM3 --baud 9600 --format 8N1 --out serial.log
  uv run --no-sync python ../scripts/probe.py serial-scan COM3 --seconds 10
  uv run --no-sync python ../scripts/probe.py modbus 192.168.1.50 --device-id 1 --watch 1 --out modbus.log

ports        serial ports with USB VID:PID (identifies the adapter chipset)
serial       every line timestamped with text, hex and parse result; Ctrl+C prints a summary
             (terminators, judgements, running-number gaps, whether TD/US lines consume numbers)
serial-scan  tries common baud/format combinations, ranked by parsable lines (products must be passing)
modbus       HR 1-10, HR 619-688, IR 190-283 raw and decoded with every word order x value encoding,
             counter-sum and limit-ordering checks; --watch then prints counter deltas per poll
Against the simulator (cw-sim run): serial socket://127.0.0.1:7001, modbus 127.0.0.1 --port 5020.
"""

from __future__ import annotations

import argparse
import logging
import re
import socket
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from importlib.metadata import version

import serial
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException
from serial.tools.list_ports import comports

from checkweigher.collector.sequence import WRAP, WRAP_WINDOW
from checkweigher.device import registers as R
from checkweigher.device.protocol import JUDGEMENTS, ParseError, ResultLine, parse_result_line

PRINTABLE = frozenset(range(0x20, 0x7F)) | {0x0D, 0x0A}
TERM_RE = re.compile(rb"\r\n|\n|\r")
TERMS = {b"\r\n": "CRLF", b"\n": "LF", b"\r": "CR"}
IDLE_FLUSH_S = 1.0
FALLBACK_CHUNK = 10
MAX_PLAUSIBLE_TARGET = 100_000  # display units; anything larger is a mis-decode
MODBUS_EXCEPTIONS = {1: "illegal function", 2: "illegal data address", 3: "illegal data value (too many registers?)",
                     4: "device failure", 6: "device busy"}


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s: str) -> int:
        for st in self.streams:
            st.write(s)
            st.flush()
        return len(s)

    def flush(self) -> None:
        for st in self.streams:
            st.flush()


def stamp() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def tally(c: Counter) -> str:
    return ", ".join(f"{k} x{v}" for k, v in c.most_common()) or "-"


def show(raw: bytes) -> str:
    return "".join(chr(b) if 0x20 <= b < 0x7F else f"\\x{b:02x}" for b in raw)


# ---- serial -------------------------------------------------------------------------------------

def serial_format(s: str) -> tuple[int, str, int]:
    m = re.fullmatch(r"([78])([NEO])([12])", s.upper())
    if not m:
        raise argparse.ArgumentTypeError(f"expected e.g. 8N1 or 7E1, got {s!r}")
    return int(m[1]), m[2], int(m[3])


def fmt_name(fmt: tuple[int, str, int]) -> str:
    return "".join(map(str, fmt))


def list_ports() -> None:
    ports = sorted(comports(), key=lambda p: p.device)
    print("serial ports:" if ports else "no serial ports found")
    for p in ports:
        print(f"  {p.device:<12} {p.description}  [{p.hwid}]")


def open_port(url: str, baud: int, fmt: tuple[int, str, int]) -> serial.SerialBase:
    bytesize, parity, stopbits = fmt
    try:
        return serial.serial_for_url(url, baudrate=baud, bytesize=bytesize, parity=parity, stopbits=stopbits,
                                     timeout=0.2)
    except (serial.SerialException, OSError, ValueError) as e:
        print(f"cannot open {url}: {e}")
        print("  wrong name, or held by another program (A&D software, a terminal, a running collector)?")
        list_ports()
        raise SystemExit(1) from None


class LineSplitter:
    """Splits the byte stream on CR LF / LF / CR and reports which terminator ended each line."""

    def __init__(self) -> None:
        self.buf = b""
        self.last_rx = time.monotonic()

    def feed(self, chunk: bytes) -> list[tuple[bytes, str]]:
        now = time.monotonic()
        if chunk:
            self.buf += chunk
            self.last_rx = now
        out = []
        while m := TERM_RE.search(self.buf):
            if m[0] == b"\r" and m.end() == len(self.buf) and now - self.last_rx < 0.3:
                break  # the LF of a CR LF may still be in flight
            out.append((self.buf[: m.start()], TERMS[m[0]]))
            self.buf = self.buf[m.end() :]
        if self.buf and (now - self.last_rx > IDLE_FLUSH_S or len(self.buf) > 512):
            out.append((self.buf, "none"))
            self.buf = b""
        return out


class SerialStats:
    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.started = time.monotonic()
        self.last_at: float | None = None
        self.bytes = self.printable = self.lines = self.empty = self.parsed = self.n_errors = 0
        self.terms: Counter[str] = Counter()
        self.lengths: Counter[int] = Counter()
        self.judgements: Counter[str] = Counter()
        self.headers: Counter[str] = Counter()
        self.units: Counter[str] = Counter()
        self.decimals: Counter[int] = Counter()
        self.errors: list[str] = []
        self.first_seq: int | None = None
        self.prev_seq: int | None = None
        self.unnumbered = 0
        self.gaps: list[int] = []
        self.resets = self.duplicates = 0
        self.td_numbering: Counter[str] = Counter()

    def feed(self, chunk: bytes) -> None:
        self.bytes += len(chunk)
        self.printable += sum(b in PRINTABLE for b in chunk)

    def line(self, raw: bytes, term: str) -> None:
        if not raw.strip(b"\x00 "):
            self.empty += 1
            return
        now = time.monotonic()
        dt = now - self.last_at if self.last_at else 0.0
        self.last_at = now
        self.lines += 1
        self.terms[term] += 1
        self.lengths[len(raw)] += 1
        # Same decoding as collector/serial_reader.py.
        text = raw.decode("ascii", errors="replace").strip("\r\x00 ")
        try:
            r = parse_result_line(text)
            r.weight_grams()
        except ParseError as e:
            self.n_errors += 1
            if len(self.errors) < 5:
                self.errors.append(str(e))
            info = f"PARSE ERROR: {e}"
        else:
            self.parsed += 1
            info = self._record(r)
        if self.verbose:
            print(f"{stamp()} +{dt:6.2f}s {term:<4} len={len(raw):<3} |{show(raw)}|  {info}")
            print(f"{'':14}{raw.hex(' ')}")

    def _record(self, r: ResultLine) -> str:
        self.judgements[r.judgement] += 1
        parts = [f"seq={'-' if r.seq is None else r.seq}",
                 f"{r.judgement} ({JUDGEMENTS.get(r.judgement, 'NOT IN MANUAL TABLE')})"]
        if r.header:
            self.headers[r.header] += 1
            parts.append(r.header)
        if r.weight is not None:
            self.units[r.unit or "(none)"] += 1
            self.decimals[-int(r.weight.as_tuple().exponent)] += 1
            parts.append(f"{r.weight} {r.unit or ''}".strip())
        if note := self._seq(r.seq):
            parts.append(note)
        return "  ".join(parts)

    def _seq(self, seq: int | None) -> str | None:
        if seq is None:
            self.unnumbered += 1
            return None
        prev, unnumbered = self.prev_seq, self.unnumbered
        self.prev_seq, self.unnumbered = seq, 0
        if prev is None:
            self.first_seq = seq
            return None
        if seq == prev:
            self.duplicates += 1
            return "!! duplicate running number"
        if seq < prev and not (prev >= WRAP - WRAP_WINDOW and seq < WRAP_WINDOW):
            self.resets += 1
            return f"!! running number went back from #{prev} (summary cleared / power cycle?)"
        skipped = (seq - prev) % WRAP - 1
        note = None
        if unnumbered:
            # Consuming TD/US lines would skip at least as many numbers as there were such lines.
            kind = ("consumed" if skipped == unnumbered else "not consumed" if skipped < unnumbered
                    else "unclear, lines also lost")
            self.td_numbering[kind] += 1
            note = f"after {unnumbered} TD/US line(s) the number skipped {skipped} ({kind})"
        if (missing := skipped - unnumbered) > 0:  # same rule as the collector's SequenceTracker
            self.gaps.append(missing)
            return f"!! {missing} line(s) missing since #{prev}" + (f"; {note}" if note else "")
        return note

    def summary(self) -> None:
        secs = max(time.monotonic() - self.started, 1e-9)
        print("\n==== serial summary ====")
        print(f"duration {secs:.0f}s, {self.bytes} bytes, {self.lines} lines ({self.lines / secs * 60:.1f}/min), "
              f"{self.empty} empty")
        print(f"terminators: {tally(self.terms)}")
        print(f"line lengths: {tally(self.lengths)}")
        print(f"non-printable bytes: {self.bytes - self.printable}")
        print(f"parsed: {self.parsed} ok, {self.n_errors} errors")
        for e in self.errors:
            print(f"  {e}")
        print(f"judgements: {tally(self.judgements)}")
        print(f"headers: {tally(self.headers)}   units: {tally(self.units)}   decimals: {tally(self.decimals)}")
        if self.first_seq is not None:
            print(f"running number: first #{self.first_seq}, last #{self.prev_seq}; {len(self.gaps)} gap(s) "
                  f"({sum(self.gaps)} missing), {self.resets} reset(s), {self.duplicates} duplicate(s)")
        if self.td_numbering:
            yes, no = self.td_numbering["consumed"], self.td_numbering["not consumed"]
            verdict = ("TD/US lines DO advance the running number" if yes and not no else
                       "TD/US lines do NOT advance the running number" if no and not yes else "inconclusive")
            print(f"numbered line after TD/US lines: {tally(self.td_numbering)} -> {verdict}")

        hints = []
        if not self.bytes:
            hints.append("no bytes at all: check cable (straight vs null-modem), port name, RS-232C Port = "
                         "'Weighing Result', and that products are passing")
        elif self.printable < 0.95 * self.bytes or (self.lines and not self.parsed):
            hints.append("bytes arrive but do not parse: baud/format mismatch (run serial-scan) or wrong Output mode")
        if self.terms["CR"] and not (self.terms["CRLF"] or self.terms["LF"]):
            hints.append("lines end in CR only: the collector splits on LF and would never see a complete line")
        if self.terms["none"]:
            hints.append("some data arrived with no terminator at all (flushed after 1 s idle)")
        if unknown := [j for j in self.judgements if j not in JUDGEMENTS]:
            hints.append(f"judgement codes not in the manual table: {', '.join(unknown)} "
                         "(counted as rejected but in no KPI category)")
        for h in hints:
            print(f"hint: {h}")


def pump(port: serial.SerialBase, st: SerialStats, deadline: float | None) -> None:
    split = LineSplitter()
    while deadline is None or time.monotonic() < deadline:
        chunk = port.read(port.in_waiting or 1)
        st.feed(chunk)
        for raw, term in split.feed(chunk):
            st.line(raw, term)


def cmd_serial(args: argparse.Namespace) -> None:
    port = open_port(args.url, args.baud, args.format)
    print(f"# listening on {args.url} {args.baud} {fmt_name(args.format)} (Ctrl+C for the summary)")
    st = SerialStats()
    try:
        pump(port, st, time.monotonic() + args.seconds if args.seconds else None)
    except KeyboardInterrupt:
        pass
    except (serial.SerialException, OSError) as e:
        print(f"{stamp()} !! port lost: {e}")
    finally:
        port.close()
    st.summary()


def cmd_scan(args: argparse.Namespace) -> None:
    combos = [(b, f) for b in args.bauds for f in args.formats]
    print(f"# {len(combos)} combinations x {args.seconds:g}s on {args.url}; products must be passing")
    results = []
    try:
        for baud, fmt in combos:
            port = open_port(args.url, baud, fmt)
            st = SerialStats(verbose=False)
            try:
                pump(port, st, time.monotonic() + args.seconds)
            except (serial.SerialException, OSError) as e:
                print(f"  {baud:>6} {fmt_name(fmt)}  port lost: {e}")
            finally:
                port.close()
            pct = st.printable / st.bytes * 100 if st.bytes else 0.0
            results.append((st.parsed, pct, st.bytes, baud, fmt))
            print(f"  {baud:>6} {fmt_name(fmt)}  bytes={st.bytes:<6} printable={pct:5.1f}%  lines={st.lines:<4} "
                  f"parsed={st.parsed}")
    except KeyboardInterrupt:
        print("  (interrupted)")
    if not results:
        return
    parsed, _, _, baud, fmt = max(results)
    if parsed:
        print(f"best: --baud {baud} --format {fmt_name(fmt)} ({parsed} parsable lines)")
    elif not any(r[2] for r in results):
        print("no bytes at any setting: check cable (straight vs null-modem), port, RS-232C Port = 'Weighing Result', "
              "and that products are passing")
    else:
        print("bytes arrived but nothing parsed: check Output mode = 'Cyclic Print', then capture with `serial`")


# ---- modbus -------------------------------------------------------------------------------------

Words = dict[tuple[str, int], int | None]

BLOCKS = [
    ("hr", R.HR_PRODUCT_NO, 10, "product / group number"),
    ("hr", R.HR_PRODUCT_BLOCK_START, R.HR_PRODUCT_BLOCK_COUNT, "active product settings"),
    ("ir", R.IR_BLOCK_START, R.IR_BLOCK_COUNT, "all summary + weighing result"),
]
U16 = [(R.HR_DECIMAL_POINT, "decimal point"), (R.HR_DIVISION, "division"), (R.HR_REJECT_STAGE, "reject stage"),
       (R.HR_OW_EXCEPTION, "OW exception"), (R.HR_PRODUCT_LENGTH, "length"), (R.HR_SPEED, "speed")]
LIMITS = [(R.HR_TARGET, "target"), (R.HR_HIHI, "HiHi"), (R.HR_HI, "Hi"), (R.HR_LO, "Lo"), (R.HR_LOLO, "LoLo"),
          (R.HR_TARE, "tare")]
SUMMARY_VALUES = [(R.IR_ALL_TOTAL_WEIGHT, "summary total weight"), (R.IR_ALL_AVERAGE, "summary average"),
                  (R.IR_ALL_MAX, "summary max"), (R.IR_ALL_MIN, "summary min"),
                  (R.IR_WEIGHING_RESULT, "last weighing result")]
COUNTERS = [(R.IR_ALL_TOTAL, "total", "total"), (R.IR_ALL_OK, "OK", "passed"), (R.IR_ALL_HIHI, "HH", "over HiHi"),
            (R.IR_ALL_HI, "HI", "over Hi"), (R.IR_ALL_LO, "LO", "under Lo"), (R.IR_ALL_LOLO, "LL", "under LoLo"),
            (R.IR_ALL_DETECT_TWO, "TD", "detect two"), (R.IR_ALL_UNSPLIT, "US", "unsplit"),
            (R.IR_ALL_FOREIGN, "MD", "foreign / metal")]
CODECS = {f"{wo}/{enc}": R.Codec(wo, enc) for enc in ("scaled_int", "float32") for wo in ("little", "big")}


def parse_range(s: str) -> tuple[str, int, int]:
    m = re.fullmatch(r"(hr|ir):(\d+):(\d+)", s.lower())
    if not m or int(m[2]) < 1 or not 1 <= int(m[3]) <= 125:
        raise argparse.ArgumentTypeError(f"expected hr:START:COUNT or ir:START:COUNT (1-based, count 1-125), got {s!r}")
    return m[1], int(m[2]), int(m[3])


def read_regs(client: ModbusTcpClient, kind: str, start: int, count: int, device_id: int,
              ) -> tuple[list[int | None], str]:
    """One request for the whole block; if the indicator refuses it, retry in small chunks."""
    fn = client.read_holding_registers if kind == "hr" else client.read_input_registers

    def one(addr: int, n: int) -> tuple[list[int] | None, str]:
        try:
            rr = fn(R.offset(addr), count=n, device_id=device_id)
        except ModbusException as e:
            return None, str(e)
        if rr.isError():
            code = getattr(rr, "exception_code", None)
            return None, f"exception {code}: {MODBUS_EXCEPTIONS.get(code, rr)}"
        return list(rr.registers), ""

    regs, err = one(start, count)
    if regs is not None and len(regs) == count:
        return list(regs), f"single read of {count} OK"
    out: list[int | None] = []
    failed = []
    for a in range(start, start + count, FALLBACK_CHUNK):
        n = min(FALLBACK_CHUNK, start + count - a)
        part, _ = one(a, n)
        if part is None or len(part) != n:
            failed.append(f"{a}+{n}")
        out += part if part is not None and len(part) == n else [None] * n
    return out, (f"single read of {count} FAILED ({err}); {FALLBACK_CHUNK}-register reads: "
                 + ("all OK" if not failed else "failed at " + ", ".join(failed)))


def read_all(client: ModbusTcpClient, device_id: int, extra: list[tuple[str, int, int, str]] | None = None,
             ) -> tuple[Words, list[tuple[str, int, int, str, list[int | None], str]]]:
    words: Words = {}
    blocks = []
    for kind, start, count, label in [*BLOCKS, *(extra or [])]:
        regs, note = read_regs(client, kind, start, count, device_id)
        words.update({(kind, start + i): v for i, v in enumerate(regs)})
        blocks.append((kind, start, count, label, regs, note))
    return words, blocks


def decode(codec: R.Codec, words: Words, kind: str, addr: int, dp: int) -> Decimal | None:
    w0, w1 = words.get((kind, addr)), words.get((kind, addr + 1))
    if w0 is None or w1 is None:
        return None
    try:
        v = codec.value(w0, w1, dp)
    except (InvalidOperation, OverflowError, ValueError):
        return None
    return v if v.is_finite() else None


def u32(codec: R.Codec, words: Words, addr: int) -> int | None:
    w0, w1 = words.get(("ir", addr)), words.get(("ir", addr + 1))
    return None if w0 is None or w1 is None else codec.u32(w0, w1)


def num(v: Decimal | int | None) -> str:
    if v is None:
        return "n/a"
    return f"{float(v):.4g}" if abs(v) >= 10**9 else str(v)


def pair(words: Words, kind: str, addr: int) -> str:
    w0, w1 = words.get((kind, addr)), words.get((kind, addr + 1))
    return "---- ----" if w0 is None or w1 is None else f"{w0:04x} {w1:04x}"


def decimal_point(words: Words) -> int:
    dp = words.get(("hr", R.HR_DECIMAL_POINT))
    return dp if dp is not None and 0 <= dp <= 6 else 0


def limit_shape(t: Decimal | None, hh: Decimal | None, h: Decimal | None, lo: Decimal | None,
                ll: Decimal | None) -> str:
    if t is None or hh is None or h is None or lo is None or ll is None:
        return "unreadable"
    if not 0 < t < MAX_PLAUSIBLE_TARGET:
        return "implausible"
    if ll <= lo <= t <= h <= hh:
        return "absolute weights (LoLo <= Lo <= target <= Hi <= HiHi)"
    if ll <= lo <= 0 <= h <= hh < t:
        return "OFFSETS from target (signed)"
    if 0 <= h <= hh < t and 0 <= lo <= ll < t:
        return "OFFSETS from target (magnitudes)"
    return "implausible"


def dump(client: ModbusTcpClient, args: argparse.Namespace) -> None:
    words, blocks = read_all(client, args.device_id, [(*r, "extra") for r in args.range])
    for kind, start, count, label, regs, note in blocks:
        print(f"\n{kind.upper()} {start}..{start + count - 1} ({label}): {note}")
        for i in range(0, count, 8):
            cells = " ".join("----" if v is None else f"{v:04x}" for v in regs[i : i + 8])
            print(f"  {kind.upper()} {start + i:>4}  {cells}")

    print("\n==== decoded: compare every value with the indicator display ====")
    print("HR 1..10 as u16: " + " ".join(str(words.get(("hr", a))) for a in range(1, 11)))
    print(f"product no (HR 1) = {words.get(('hr', 1))}, group no (HR 2) = {words.get(('hr', 2))}"
          "  <- if they show up one register later, the address offset is wrong")
    print("  ".join(f"{name} (HR {a}) = {words.get(('hr', a))}" for a, name in U16))

    dp, dp_raw = decimal_point(words), words.get(("hr", R.HR_DECIMAL_POINT))
    print(f"\n32-bit values; scaled_int uses dp={dp} from HR {R.HR_DECIMAL_POINT}"
          + ("" if dp == dp_raw else f" (raw value {dp_raw} is not a digit count!)"))
    print(f"  {'':32}{'words':<11}" + "".join(f"{k:>19}" for k in CODECS))
    vals: dict[str, dict[str, Decimal | None]] = {}
    for kind, addr, name in [*(("hr", a, n) for a, n in LIMITS), *(("ir", a, n) for a, n in SUMMARY_VALUES)]:
        vals[name] = {k: decode(c, words, kind, addr, dp) for k, c in CODECS.items()}
        print(f"  {kind.upper()} {addr:<4} {name:<24}{pair(words, kind, addr):<11}"
              + "".join(f"{num(v):>19}" for v in vals[name].values()))

    print("\nlimit check per decoding (the collector assumes absolute weights):")
    plausible: dict[str, str] = {}
    for k in CODECS:
        shape = limit_shape(*(vals[n][k] for n in ("target", "HiHi", "Hi", "Lo", "LoLo")))
        print(f"  {k:<19} {shape}")
        if shape not in ("unreadable", "implausible"):
            plausible[k] = shape

    print("\nsummary counters: compare with the indicator's summary screen")
    orders = {wo: R.Codec(wo) for wo in ("little", "big")}
    counts = {wo: {code: u32(c, words, addr) for addr, code, _ in COUNTERS} for wo, c in orders.items()}
    print(f"  {'':32}{'words':<11}" + "".join(f"{'u32 ' + wo:>14}" for wo in orders))
    for addr, code, label in COUNTERS:
        print(f"  IR {addr:<4} {label:<24}{pair(words, 'ir', addr):<11}"
              + "".join(f"{num(counts[wo][code]):>14}" for wo in orders))
    sums = {wo: None if None in d.values() else sum(v for k, v in d.items() if k != "total" and v is not None)
            for wo, d in counts.items()}
    print(f"  {'':8}{'sum of categories':<24}{'':<11}" + "".join(f"{num(sums[wo]):>14}" for wo in orders))

    print("\n==== suggestions (confirm against the display before putting them in config.yaml) ====")
    tl, tb = counts["little"]["total"], counts["big"]["total"]
    if tl is None or tb is None:
        print("word_order: counters unreadable")
    elif tl == tb:
        print("word_order: cannot tell while the counters are zero; pass a few products and re-run")
    else:
        likely = "little" if tl < tb else "big"
        total, cats = counts[likely]["total"], sums[likely]
        print(f"word_order: {likely}  (total reads {total} this way)")
        if total is not None and cats is not None:
            diff = total - cats
            print("counters: total = OK + HH + HI + LO + LL + TD + US + MD" if diff == 0 else
                  f"counters: total is {diff} more than the categories (E1/E2 or other rejects only in total?)"
                  if diff > 0 else f"counters: categories add up to {-diff} more than total (double counting?)")
    if len(plausible) == 1:
        k, shape = next(iter(plausible.items()))
        print(f"value_encoding: {k.split('/')[1]}  (as {k}; limits are {shape})")
    elif plausible:
        print(f"value_encoding: ambiguous between {', '.join(plausible)}; compare target with the display")
    else:
        print("value_encoding: no decoding gives a plausible target/limits; compare the raw words with the display")
    if any("OFFSETS" in s for s in plausible.values()):
        print("WARNING: limits look like offsets from target, but the collector treats them as absolute weights")


def watch(client: ModbusTcpClient, args: argparse.Namespace) -> None:
    codec = R.Codec(args.word_order, args.value_encoding)
    print(f"\n# polling every {args.watch:g}s as {args.word_order}/{args.value_encoding} (Ctrl+C to stop)")
    prev_counts: dict[str, int | None] | None = None
    prev_product: list[int | None] | None = None
    while True:
        words, _ = read_all(client, args.device_id)
        if None in words.values():
            print(f"{stamp()} read failed; retrying")
            time.sleep(args.watch)
            continue
        dp = decimal_point(words)
        product = [words[("hr", a)] for a in (1, 2, *range(R.HR_PRODUCT_BLOCK_START,
                                                            R.HR_PRODUCT_BLOCK_START + R.HR_PRODUCT_BLOCK_COUNT))]
        if product != prev_product:
            print(f"{stamp()} product G{words[('hr', R.HR_GROUP_NO)]}-P{words[('hr', R.HR_PRODUCT_NO)]} dp={dp}  "
                  + "  ".join(f"{n}={num(decode(codec, words, 'hr', a, dp))}" for a, n in LIMITS))
            prev_product = product
        counts = {code: u32(codec, words, addr) for addr, code, _ in COUNTERS}
        weight = (f"last weight [{pair(words, 'ir', R.IR_WEIGHING_RESULT)}] "
                  f"{num(decode(codec, words, 'ir', R.IR_WEIGHING_RESULT, dp))}")
        if prev_counts is None:
            print(f"{stamp()} counters " + " ".join(f"{k}={v}" for k, v in counts.items()) + f"  {weight}")
        elif counts != prev_counts:
            total, prev_total = counts["total"] or 0, prev_counts["total"] or 0
            if total < prev_total:
                print(f"{stamp()} !! total went from {prev_total} to {total}: summary cleared")
            else:
                deltas = " ".join(f"{k}+{(v or 0) - (prev_counts[k] or 0)}" for k, v in counts.items()
                                  if k != "total" and v != prev_counts[k])
                print(f"{stamp()} total {total} (+{total - prev_total})  {deltas or '(no category moved)'}  {weight}")
        prev_counts = counts
        time.sleep(args.watch)


def cmd_modbus(args: argparse.Namespace) -> None:
    logging.getLogger("pymodbus").setLevel(logging.CRITICAL)  # failures are reported in our own output
    client = ModbusTcpClient(args.host, port=args.port, timeout=args.timeout, retries=1)
    if not client.connect():
        print(f"cannot connect to {args.host}:{args.port}")
        print("  ping the indicator; Connection > Modbus must be 'Modbus / TCP' (restart the indicator after")
        print("  changing it); check this PC's IP/subnet and any firewall in between")
        raise SystemExit(1)
    print(f"# connected to {args.host}:{args.port}, device id {args.device_id}")
    try:
        dump(client, args)
        if args.watch:
            watch(client, args)
    except KeyboardInterrupt:
        pass
    finally:
        client.close()


def main() -> None:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--out", help="also append everything printed to this file")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ports", parents=[common], help="list serial ports").set_defaults(func=lambda _: list_ports())

    s = sub.add_parser("serial", parents=[common], help="capture result lines")
    s.add_argument("url", help="COM3, /dev/ttyUSB0 or socket://host:port")
    s.add_argument("--baud", type=int, default=9600)
    s.add_argument("--format", type=serial_format, default="8N1", help="data bits, parity, stop bits (8N1, 7E1, ...)")
    s.add_argument("--seconds", type=float, help="stop after this long (default: until Ctrl+C)")
    s.set_defaults(func=cmd_serial)

    sc = sub.add_parser("serial-scan", parents=[common], help="find baud rate / format")
    sc.add_argument("url")
    sc.add_argument("--seconds", type=float, default=8, help="listening time per combination")
    sc.add_argument("--bauds", type=lambda v: [int(x) for x in v.split(",")], default=[2400, 4800, 9600, 19200, 38400])
    sc.add_argument("--formats", type=lambda v: [serial_format(x) for x in v.split(",")],
                    default=[serial_format(f) for f in ("8N1", "7E1", "7O1", "8E1", "8O1")])
    sc.set_defaults(func=cmd_scan)

    m = sub.add_parser("modbus", parents=[common], help="dump and decode registers")
    m.add_argument("host")
    m.add_argument("--port", type=int, default=502)
    m.add_argument("--device-id", type=int, default=1)
    m.add_argument("--timeout", type=float, default=2.0)
    m.add_argument("--range", type=parse_range, action="append", default=[], metavar="hr|ir:START:COUNT",
                   help="extra raw dump, 1-based manual addresses (repeatable)")
    m.add_argument("--watch", type=float, metavar="SECONDS", help="after the dump, poll and print counter changes")
    m.add_argument("--word-order", choices=["little", "big"], default="little", help="decoding used by --watch")
    m.add_argument("--value-encoding", choices=["scaled_int", "float32"], default="scaled_int",
                   help="decoding used by --watch")
    m.set_defaults(func=cmd_modbus)

    args = p.parse_args()
    sys.stdout.reconfigure(errors="backslashreplace")
    if args.out:
        sys.stdout = Tee(sys.stdout, open(args.out, "a", encoding="utf-8"))
    now = datetime.now().astimezone()
    print(f"# probe {' '.join(sys.argv[1:])}")
    print(f"# {socket.gethostname()}  local {now:%Y-%m-%d %H:%M:%S %z}  utc {datetime.now(UTC):%H:%M:%S}  "
          f"pyserial {serial.VERSION}  pymodbus {version('pymodbus')}")
    args.func(args)


if __name__ == "__main__":
    main()
