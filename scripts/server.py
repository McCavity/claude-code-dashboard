"""Command Centre FastAPI app.

Routes:

  * ``GET  /api/health``      smoke check
  * ``POST /v1/logs``         OTLP/HTTP JSON log ingest
  * ``POST /v1/metrics``      OTLP/HTTP JSON metric ingest

Lifespan:

  * Boots the SQLite schema.
  * Spawns a background ``sync_sessions.run_loop`` task that re-scans
    ``~/.claude/projects/`` every 120 s.

Future phases extend this module with the full ``/api/*`` surface and
static UI hosting.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from scripts._csrf import csrf_origin_guard
from scripts.api_ops import router as ops_router
from scripts.api_query import router as query_router
from scripts.api_system import router as system_router
from scripts.db import connect, db_path, list_tables
from scripts.otel_parser import ingest_logs, ingest_metrics

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=os.environ.get("CC_LOG_LEVEL", "info").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("commandcentre")

_BOOTED_AT = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Boot DB.
    conn = connect()
    tables = list_tables(conn)
    log.info("db ready at %s with %d tables", db_path(), len(tables))
    app.state.tables_at_boot = tables
    app.state.last_otel_event_at = 0.0
    app.state.last_sync_tick_at = 0.0
    app.state.last_notifier_tick_at = 0.0
    app.state.otel_events_seen = 0
    app.state.otel_events_dropped = 0
    conn.close()

    # Background sync loop. We run the synchronous run_once ourselves so
    # we can stamp last_sync_tick_at on each tick (run_loop wraps it but
    # doesn't expose a hook).
    from scripts.sync_sessions import run_once as sync_run_once

    stop = asyncio.Event()
    app.state.stop_event = stop

    async def _sync_supervisor() -> None:
        while not stop.is_set():
            try:
                await asyncio.to_thread(sync_run_once)
                app.state.last_sync_tick_at = time.time()
            except Exception:  # noqa: BLE001
                log.exception("sync_sessions tick failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=120.0)
            except asyncio.TimeoutError:
                continue

    sync_task = asyncio.create_task(_sync_supervisor(), name="sync_sessions")
    app.state.sync_task = sync_task

    try:
        yield
    finally:
        log.info("commandcentre shutting down")
        stop.set()
        try:
            await asyncio.wait_for(sync_task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            sync_task.cancel()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Command Centre",
    version="0.1.0",
    description="Local Claude Code dashboard.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# CSRF: block cross-origin state-changing requests. CORS above only governs
# response readability — it does not stop a foreign page from *triggering*
# our unauthenticated mutating endpoints. See scripts/_csrf.py.
app.middleware("http")(csrf_origin_guard)

app.include_router(query_router)
app.include_router(ops_router)
app.include_router(system_router)
# NOTE: static UI hosting is registered at the bottom of this module so
# the catch-all does not shadow /api/health, /v1/logs, /v1/metrics — the
# decorators below register their routes before the catch-all gets
# attached.


# ---------------------------------------------------------------------------
# /api/health
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "uptime_seconds": round(time.time() - _BOOTED_AT, 2),
        "db": str(db_path()),
        "tables": app.state.tables_at_boot,
    }


# ---------------------------------------------------------------------------
# OTEL ingest
# ---------------------------------------------------------------------------


@app.post("/v1/logs")
async def otel_logs(request: Request) -> JSONResponse:
    """OTLP/HTTP JSON log ingest. Always returns 200 — Claude Code does
    not retry on success codes, so dropping a malformed batch is
    preferable to crashing it."""
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({}, status_code=200)

    def _ingest() -> tuple[int, int]:
        conn = connect()
        try:
            return ingest_logs(conn, payload)
        finally:
            conn.close()

    try:
        inserted, dropped = await asyncio.to_thread(_ingest)
    except Exception:  # noqa: BLE001
        log.exception("OTEL log ingest failed")
        return JSONResponse({}, status_code=200)

    if inserted:
        app.state.last_otel_event_at = time.time()
    app.state.otel_events_seen += inserted
    app.state.otel_events_dropped += dropped
    if dropped:
        log.warning("OTEL log batch: %d inserted, %d dropped", inserted, dropped)
    return JSONResponse({}, status_code=200)


@app.post("/v1/metrics")
async def otel_metrics(request: Request) -> JSONResponse:
    """OTLP/HTTP JSON metric ingest. Always returns 200."""
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({}, status_code=200)

    def _ingest() -> tuple[int, int]:
        conn = connect()
        try:
            return ingest_metrics(conn, payload)
        finally:
            conn.close()

    try:
        inserted, dropped = await asyncio.to_thread(_ingest)
    except Exception:  # noqa: BLE001
        log.exception("OTEL metric ingest failed")
        return JSONResponse({}, status_code=200)

    if dropped:
        log.warning("OTEL metric batch: %d inserted, %d dropped", inserted, dropped)
    return JSONResponse({}, status_code=200)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Static UI hosting (registered last so /api and /v1 win route resolution)
# ---------------------------------------------------------------------------


def _ui_dist_dir() -> Path | None:
    """Locate the built React bundle."""
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent / "ui" / "dist",
        Path.home() / ".command-centre" / "ui" / "dist",
    ]
    for c in candidates:
        if (c / "index.html").exists():
            return c
    return None


_UI_DIST = _ui_dist_dir()
if _UI_DIST is not None:
    log.info("serving UI from %s", _UI_DIST)
    app.mount("/assets", StaticFiles(directory=str(_UI_DIST / "assets")), name="ui-assets")

    @app.get("/", include_in_schema=False)
    async def _ui_index() -> FileResponse:
        return FileResponse(str(_UI_DIST / "index.html"))

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    async def _ui_catchall(full_path: str):
        if full_path.startswith(("api/", "v1/")):
            return JSONResponse({"detail": "not found"}, status_code=404)
        target = _UI_DIST / full_path
        if target.is_file():
            return FileResponse(str(target))
        return FileResponse(str(_UI_DIST / "index.html"))
else:
    log.warning("ui/dist not found — UI hosting disabled (run `npm run build`)")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def _run() -> None:
    import uvicorn

    host = os.environ.get("CC_HOST", "127.0.0.1")
    port = int(os.environ.get("CC_PORT", "8765"))
    uvicorn.run(
        "scripts.server:app",
        host=host,
        port=port,
        log_level=os.environ.get("CC_LOG_LEVEL", "info"),
        reload=False,
    )


if __name__ == "__main__":
    _run()
