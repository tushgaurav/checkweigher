"""Network endpoints of the simulated indicator.

* Serial "Weighing Result" output exposed over TCP; the collector connects with
  pyserial's ``socket://host:port`` URL exactly as it would to a serial-to-Ethernet adapter.
* Modbus TCP server exposing the manual's input/holding register map.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging

from pymodbus.server import ModbusTcpServer
from pymodbus.simulator import DataType, SimData, SimDevice

from checkweigher.device import registers as R
from checkweigher.simulator.device import SimIndicator

log = logging.getLogger("cw.sim")

FC_HOLDING, FC_INPUT = 3, 4


class SerialBroadcastServer:
    def __init__(self, host: str, port: int):
        self.host, self.port = host, port
        self.clients: set[asyncio.StreamWriter] = set()
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        log.info("serial output on socket://%s:%d", self.host, self.port)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        log.info("serial client connected %s", writer.get_extra_info("peername"))
        self.clients.add(writer)
        try:
            while await reader.read(256):
                pass  # the indicator ignores input on the result port
        except ConnectionError:
            pass
        finally:
            self.clients.discard(writer)
            writer.close()

    async def send(self, line: str) -> None:
        data = (line + "\r\n").encode("ascii")
        for w in list(self.clients):
            try:
                w.write(data)
                await w.drain()
            except ConnectionError:
                self.clients.discard(w)


class ModbusEndpoint:
    def __init__(self, sim: SimIndicator, codec: R.Codec, host: str, port: int, device_id: int,
                 layout: R.Layout = R.MANUAL):
        self.sim, self.codec, self.device_id, self.layout = sim, codec, device_id, layout

        def regs(n: int) -> list[SimData]:
            return [SimData(0, count=n, values=0, datatype=DataType.REGISTERS)]

        def bits() -> list[SimData]:
            return [SimData(0, count=16, values=False, datatype=DataType.BITS)]

        # Distinct blocks (co, di, hr, ir): holding and input registers overlap in address space.
        device = SimDevice(device_id, simdata=(bits(), bits(), regs(1000), regs(1000)))
        self.server = ModbusTcpServer(device, address=(host, port))
        self.host, self.port = host, port

    async def start(self) -> None:
        await self.server.serve_forever(background=True)
        await self.publish_identity()
        await self.publish_product()
        await self.publish_counters()
        log.info("modbus tcp on %s:%d (device id %d)", self.host, self.port, self.device_id)

    async def publish_identity(self) -> None:
        """IR 1-44 (manual Table 18): own IP / subnet / gateway, RS-232C settings, Modbus slave address."""
        try:
            ip = list(ipaddress.IPv4Address(self.host).packed)
        except ValueError:
            ip = [0, 0, 0, 0]
        regs = [0] * 44
        regs[0:12] = [*ip, 255, 255, 255, 0, *ip[:3], 1]
        regs[22:28] = [3, 0, 2, 0, 1, 0]  # weighing result, cyclic print, 9600, no parity, 8 bit, 1 stop bit
        regs[34:36] = [1, self.device_id]
        await self.server.async_setValues(self.device_id, FC_INPUT, R.offset(1), regs)

    async def publish_product(self) -> None:
        await self.server.async_setValues(self.device_id, FC_HOLDING, R.offset(R.HR_PRODUCT_NO),
                                          self.sim.holding_ids())
        if self.layout.product_settings is not None:
            await self.server.async_setValues(self.device_id, FC_HOLDING, R.offset(self.layout.product_settings),
                                              self.sim.holding_product_block(self.codec))

    async def publish_counters(self) -> None:
        regs = self.sim.input_block(self.codec)
        if self.layout == R.MANUAL:
            await self.server.async_setValues(self.device_id, FC_INPUT, R.offset(R.IR_BLOCK_START), regs)
            return
        # Shifted firmware: only the blocks the collector reads, at their configured addresses.
        await self.server.async_setValues(self.device_id, FC_INPUT, R.offset(self.layout.summary),
                                          regs[: R.COUNTERS_COUNT])
        if self.layout.weighing_result is not None:
            i = R.IR_WEIGHING_RESULT - R.IR_BLOCK_START
            await self.server.async_setValues(self.device_id, FC_INPUT, R.offset(self.layout.weighing_result),
                                              regs[i : i + 2])

    async def stop(self) -> None:
        await self.server.shutdown()
