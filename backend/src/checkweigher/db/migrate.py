"""Apply SQL migrations in ``db/sql``.

Files are applied in name order. ``NNN_name.timescale.sql`` / ``NNN_name.plain.sql``
pairs are variants of the same migration: the TimescaleDB one is used when the
extension can be loaded, otherwise the plain-PostgreSQL one (dev / tests).
"""

from __future__ import annotations

import argparse
import logging
import os
import re
from pathlib import Path

import psycopg

from checkweigher.config import load_config

log = logging.getLogger("cw.migrate")
SQL_DIR = Path(__file__).parent / "sql"


def split_statements(sql: str) -> list[str]:
    """Split a script on top-level semicolons (respects quotes, $$ bodies and comments)."""
    out, buf, i, n = [], [], 0, len(sql)
    while i < n:
        c = sql[i]
        if sql.startswith("--", i):
            j = sql.find("\n", i)
            j = n if j == -1 else j
            buf.append(sql[i:j])
            i = j
        elif sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            j = n if j == -1 else j + 2
            buf.append(sql[i:j])
            i = j
        elif c == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'" and not sql.startswith("''", j):
                    break
                j += 2 if sql.startswith("''", j) else 1
            buf.append(sql[i : j + 1])
            i = j + 1
        elif c == "$" and (m := re.match(r"\$[A-Za-z_]*\$", sql[i:])):
            tag = m.group(0)
            j = sql.find(tag, i + len(tag))
            j = n if j == -1 else j + len(tag)
            buf.append(sql[i:j])
            i = j
        elif c == ";":
            out.append("".join(buf))
            buf = []
            i += 1
        else:
            buf.append(c)
            i += 1
    out.append("".join(buf))

    def has_code(s: str) -> bool:
        return bool(re.sub(r"--[^\n]*|/\*.*?\*/", "", s, flags=re.S).strip())

    return [s.strip() for s in out if has_code(s)]


def timescale_available(conn: psycopg.Connection) -> bool:
    if os.environ.get("CW_DISABLE_TIMESCALE"):
        return False
    row = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb'), "
        "current_setting('shared_preload_libraries')"
    ).fetchone()
    assert row is not None
    return bool(row[0]) and "timescaledb" in row[1]


def plan(files: list[Path], use_timescale: bool) -> list[tuple[str, Path]]:
    chosen: dict[str, Path] = {}
    for f in sorted(files):
        name = f.name.removesuffix(".sql")
        version, _, variant = name.partition(".")
        if variant and variant != ("timescale" if use_timescale else "plain"):
            continue
        chosen[version] = f
    return sorted(chosen.items())


def migrate(url: str) -> list[str]:
    applied_now = []
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version text PRIMARY KEY, variant text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        use_ts = timescale_available(conn)
        log.info("TimescaleDB %s", "enabled" if use_ts else "not available - using plain PostgreSQL views")
        for version, path in plan(list(SQL_DIR.glob("*.sql")), use_ts):
            if version in done:
                continue
            log.info("applying %s", path.name)
            # Statements run one by one in autocommit: continuous aggregates cannot be
            # created inside a transaction block.
            for stmt in split_statements(path.read_text(encoding="utf-8")):
                conn.execute(stmt.encode())
            variant = path.name.removesuffix(".sql").partition(".")[2] or "common"
            conn.execute("INSERT INTO schema_migrations (version, variant) VALUES (%s, %s)", (version, variant))
            applied_now.append(path.name)
    return applied_now


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="Apply database migrations")
    p.add_argument("--config", help="path to config.yaml (default: $CW_CONFIG or ./config.yaml)")
    p.add_argument("--database-url", help="override database url")
    args = p.parse_args()
    url = args.database_url or load_config(args.config).database.url
    applied = migrate(url)
    log.info("applied %d migration(s)%s", len(applied), f": {', '.join(applied)}" if applied else "")


if __name__ == "__main__":
    main()
