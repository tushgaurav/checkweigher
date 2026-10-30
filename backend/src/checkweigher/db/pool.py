from __future__ import annotations

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


async def open_pool(url: str, *, min_size: int = 1, max_size: int = 5, name: str = "cw",
                    getconn_timeout_s: float = 10.0) -> AsyncConnectionPool:
    """`getconn_timeout_s` bounds how long a caller waits for a connection, e.g. while the database is down."""
    pool = AsyncConnectionPool(
        url,
        min_size=min_size,
        max_size=max_size,
        name=name,
        open=False,
        timeout=getconn_timeout_s,
        # Discard connections broken by a server restart before handing them out.
        check=AsyncConnectionPool.check_connection,
        kwargs={"row_factory": dict_row, "autocommit": True, "connect_timeout": 5},
    )
    await pool.open(wait=False)
    return pool
