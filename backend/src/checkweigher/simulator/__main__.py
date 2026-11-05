"""cw-sim run   - simulate a live indicator (serial-over-TCP + Modbus TCP)
cw-sim seed  - write synthetic history into the database
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
import sys
import time

from checkweigher.config import load_config
from checkweigher.device.registers import Codec, Layout
from checkweigher.simulator.device import DEFAULT_PRODUCTS, SimIndicator, SimProduct
from checkweigher.simulator.servers import ModbusEndpoint, SerialBroadcastServer

log = logging.getLogger("cw.sim")


async def run(args: argparse.Namespace) -> None:
    product = SimProduct.around(args.target, decimal_point=args.decimals) if args.target else DEFAULT_PRODUCTS[0]
    sim = SimIndicator(product, sd=args.sd, bias=args.bias, td_rate=args.td_rate, us_rate=args.us_rate,
                       md_rate=args.md_rate, seed=args.seed)
    codec = Codec(args.word_order, args.value_encoding)
    layout = Layout(args.summary_address, args.weighing_result_address or None, args.product_settings_address or None)
    serial_out = SerialBroadcastServer(args.host, args.serial_port)
    modbus = ModbusEndpoint(sim, codec, args.host, args.modbus_port, args.device_id, layout)
    await serial_out.start()
    await modbus.start()
    rng = random.Random(args.seed)
    t0 = time.monotonic()
    last_change = last_clear = t0
    log.info("producing ~%.0f products/min (drop rate %.1f%%)", args.ppm, args.drop_rate * 100)
    while True:
        await asyncio.sleep(max(0.05, rng.gauss(60.0 / args.ppm, 6.0 / args.ppm)))
        now = time.monotonic()
        if args.product_change_min and now - last_change > args.product_change_min * 60:
            sim.product = rng.choice([p for p in DEFAULT_PRODUCTS if p != sim.product])
            last_change = now
            await modbus.publish_product()
            log.info("product changed to G%d-P%d (%s g)", sim.product.group_no, sim.product.product_no,
                     sim.product.target)
        if args.clear_every_min and now - last_clear > args.clear_every_min * 60:
            sim.clear_summary()
            last_clear = now
            log.info("summary cleared")
        piece = sim.next_piece(now - t0)
        await modbus.publish_counters()
        if rng.random() >= args.drop_rate:
            await serial_out.send(piece.line)
        log.debug("%s", piece.line)


def main() -> None:
    p = argparse.ArgumentParser(description="AD-4412-CW simulator")
    p.add_argument("--log-level", default="INFO")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="simulate a live indicator")
    r.add_argument("--host", default="127.0.0.1")
    r.add_argument("--serial-port", type=int, default=7001)
    r.add_argument("--modbus-port", type=int, default=5020)
    r.add_argument("--device-id", type=int, default=1)
    r.add_argument("--ppm", type=float, default=60, help="products per minute")
    r.add_argument("--target", type=float, help="target weight in g (default: built-in 500 g product)")
    r.add_argument("--decimals", type=int, default=1)
    r.add_argument("--sd", type=float, default=1.6)
    r.add_argument("--bias", type=float, default=2.5, help="mean overfill in g at 500 g")
    r.add_argument("--td-rate", type=float, default=0.008)
    r.add_argument("--us-rate", type=float, default=0.004)
    r.add_argument("--md-rate", type=float, default=0.0008)
    r.add_argument("--drop-rate", type=float, default=0.0, help="fraction of serial lines to drop")
    r.add_argument("--product-change-min", type=float, default=0)
    r.add_argument("--clear-every-min", type=float, default=0)
    r.add_argument("--word-order", choices=["little", "big"], default="little")
    r.add_argument("--value-encoding", choices=["scaled_int", "float32"], default="scaled_int")
    # Emulate firmware that shifts the register blocks (0 = block not available).
    r.add_argument("--summary-address", type=int, default=Layout.summary)
    r.add_argument("--weighing-result-address", type=int, default=Layout.weighing_result)
    r.add_argument("--product-settings-address", type=int, default=Layout.product_settings)
    r.add_argument("--seed", type=int)

    s = sub.add_parser("seed", help="write synthetic history to the database")
    s.add_argument("--config")
    s.add_argument("--days", type=int, default=7)
    s.add_argument("--ppm", type=float, default=40)
    s.add_argument("--seed", type=int, default=42)

    args = p.parse_args()
    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("pymodbus").setLevel(logging.WARNING)
    if args.cmd == "seed":
        from checkweigher.simulator.seed import seed

        n = seed(load_config(args.config), args.days, args.ppm, args.seed)
        log.info("seeded %d weighings", n)
        return
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    try:
        asyncio.run(run(args), loop_factory=loop_factory)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
