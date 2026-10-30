"""Blocking pyserial reader on a dedicated thread, delivering complete lines to asyncio.

A thread per port behaves identically on Linux and Windows and for every
pyserial URL type (real ports, /dev/serial/by-path links, socket://host:port).
Lines are timestamped on the reader thread as soon as the terminator arrives.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime

import serial

from checkweigher.config import SerialConfig

log = logging.getLogger("cw.serial")

LineCallback = Callable[[str, datetime], None]
StateCallback = Callable[[str, str | None], None]

MAX_LINE = 256


class SerialLineReader:
    def __init__(self, cfg: SerialConfig, loop: asyncio.AbstractEventLoop, on_line: LineCallback,
                 on_state: StateCallback, name: str):
        self.cfg, self.loop, self.on_line, self.on_state, self.name = cfg, loop, on_line, on_state, name
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"serial-{name}", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)

    def _emit_state(self, state: str, detail: str | None = None) -> None:
        self.loop.call_soon_threadsafe(self.on_state, state, detail)

    def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                port = serial.serial_for_url(
                    self.cfg.url,
                    baudrate=self.cfg.baudrate,
                    bytesize=self.cfg.bytesize,
                    parity=self.cfg.parity,
                    stopbits=self.cfg.stopbits,
                    timeout=1.0,
                )
            except (serial.SerialException, OSError, ValueError) as e:
                self._emit_state("disconnected", str(e))
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 30.0)
                continue
            log.info("%s: serial open %s", self.name, self.cfg.url)
            self._emit_state("connected", self.cfg.url)
            backoff = 1.0
            try:
                self._read_loop(port)
            except (serial.SerialException, OSError) as e:
                log.warning("%s: serial error: %s", self.name, e)
                self._emit_state("disconnected", str(e))
            finally:
                port.close()
            self._stop.wait(1.0)
        self._emit_state("stopped")

    def _read_loop(self, port: serial.SerialBase) -> None:
        buf = bytearray()
        while not self._stop.is_set():
            chunk = port.read(port.in_waiting or 1)
            if not chunk:
                continue
            buf += chunk
            while (i := buf.find(b"\n")) != -1:
                line, buf = bytes(buf[:i]), buf[i + 1 :]
                ts = datetime.fromtimestamp(time.time_ns() / 1e9, UTC)
                text = line.decode("ascii", errors="replace").strip("\r\x00 ")
                if text:
                    self.loop.call_soon_threadsafe(self.on_line, text, ts)
            if len(buf) > MAX_LINE:
                log.warning("%s: discarding %d bytes without line terminator", self.name, len(buf))
                buf.clear()
