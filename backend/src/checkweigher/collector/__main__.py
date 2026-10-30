from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from checkweigher.collector.service import CollectorService
from checkweigher.config import load_config


def main() -> None:
    p = argparse.ArgumentParser(description="Checkweigher data collector")
    p.add_argument("--config", help="path to config.yaml (default: $CW_CONFIG or ./config.yaml)")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level.upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("pymodbus").setLevel(logging.WARNING)
    cfg = load_config(args.config)
    # psycopg async requires a selector event loop on Windows.
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    try:
        asyncio.run(CollectorService(cfg).run(), loop_factory=loop_factory)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
