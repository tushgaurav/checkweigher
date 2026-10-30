from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import uvicorn

from checkweigher.api.app import create_app
from checkweigher.config import load_config


def main() -> None:
    p = argparse.ArgumentParser(description="Checkweigher dashboard API")
    p.add_argument("--config", help="path to config.yaml (default: $CW_CONFIG or ./config.yaml)")
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    p.add_argument("--log-level", default="info")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config(args.config)
    config = uvicorn.Config(create_app(cfg), host=args.host or cfg.api.host, port=args.port or cfg.api.port,
                            log_level=args.log_level, proxy_headers=True)
    server = uvicorn.Server(config)
    # psycopg async requires a selector event loop on Windows.
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(server.serve(), loop_factory=loop_factory)


if __name__ == "__main__":
    main()
