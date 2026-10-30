from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from checkweigher.api.routes import router
from checkweigher.config import AppConfig, load_config
from checkweigher.db.pool import open_pool
from checkweigher.shifts import DEFAULT_SHIFTS, ShiftResolver

log = logging.getLogger("cw.api")


class SPAStaticFiles(StaticFiles):
    """Serve the built React app; unknown paths fall back to index.html (client-side routing)."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            # path uses OS separators (api\x on Windows)
            if e.status_code != 404 or path.replace("\\", "/").startswith("api/"):
                raise
            return FileResponse(Path(self.directory) / "index.html")  # type: ignore[arg-type]


def create_app(cfg: AppConfig | None = None) -> FastAPI:
    cfg = cfg or load_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        st = app.state
        st.cfg, st.tz = cfg, cfg.plant.tz
        st.resolver = ShiftResolver(DEFAULT_SHIFTS, st.tz)
        st.pool = await open_pool(cfg.database.url, min_size=1, max_size=8, name="api")
        st.timescale = False
        try:
            async with st.pool.connection(timeout=10) as conn:
                cur = await conn.execute("SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'")
                st.timescale = await cur.fetchone() is not None
        except Exception as e:
            log.warning("database not reachable at startup: %s", e)
        yield
        await st.pool.close()

    app = FastAPI(title="Checkweigher Dashboard API", version="0.1.0", lifespan=lifespan)
    app.include_router(router)
    dist = Path(cfg.api.web_dist) if cfg.api.web_dist else Path(__file__).resolve().parents[4] / "web" / "dist"
    if (dist / "index.html").exists():
        app.mount("/", SPAStaticFiles(directory=dist, html=True), name="web")
    else:
        log.info("web build not found at %s; serving API only", dist)
    return app
