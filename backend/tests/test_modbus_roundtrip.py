"""Simulator Modbus server <-> collector decoding, over a real TCP socket."""

from __future__ import annotations

import socket
from decimal import Decimal

import pytest
from pymodbus.client import AsyncModbusTcpClient

from checkweigher.device import registers as R
from checkweigher.simulator.device import SimIndicator, SimProduct
from checkweigher.simulator.servers import ModbusEndpoint


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.parametrize(("word_order", "encoding"), [("little", "scaled_int"), ("big", "float32")])
async def test_counters_and_product_roundtrip(word_order, encoding):
    codec = R.Codec(word_order, encoding)
    product = SimProduct.around(500, group_no=2, product_no=7)
    sim = SimIndicator(product, seed=1)
    for i in range(25):
        sim.next_piece(float(i))
    port = free_port()
    ep = ModbusEndpoint(sim, codec, "127.0.0.1", port, device_id=1)
    await ep.start()
    client = AsyncModbusTcpClient("127.0.0.1", port=port, timeout=2, reconnect_delay=0)
    try:
        assert await client.connect()
        ir = await client.read_input_registers(R.offset(R.IR_BLOCK_START), count=R.IR_BLOCK_COUNT, device_id=1)
        ids = await client.read_holding_registers(R.offset(R.HR_PRODUCT_NO), count=2, device_id=1)
        hr = await client.read_holding_registers(R.offset(R.HR_PRODUCT_BLOCK_START),
                                                 count=R.HR_PRODUCT_BLOCK_COUNT, device_id=1)
        assert not ir.isError() and not ids.isError() and not hr.isError()

        counters = R.Counters.from_block(R.Block(R.IR_BLOCK_START, ir.registers, codec))
        assert counters.total == 25
        assert counters.total == sum(sim.counters[k] for k in sim.counters if k != "total")
        assert counters.ok == sim.counters["ok"]

        settings = R.ProductSettings.from_blocks(R.Block(R.HR_PRODUCT_NO, ids.registers, codec),
                                                 R.Block(R.HR_PRODUCT_BLOCK_START, hr.registers, codec))
        assert (settings.group_no, settings.product_no, settings.decimal_point) == (2, 7, 1)
        assert settings.target == Decimal("500.0")
        assert settings.hi == product.hi and settings.lolo == product.lolo

        last = R.Block(R.IR_BLOCK_START, ir.registers, codec).value(R.IR_WEIGHING_RESULT, 1)
        assert last == sim.last_weight
    finally:
        client.close()
        await ep.stop()
