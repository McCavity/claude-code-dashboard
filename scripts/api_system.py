"""System / live / sync / dispatcher trigger endpoints.

Includes the emergency-stop pathway. The implementation is **PID-file
based**: the dispatcher writes a marker file under
``.tmp/mission-control-queue/pids/{pid}`` for every child it spawns and
deletes it on exit. We scan that directory, verify each PID is still a
``claude -p`` process (defense against PID recycling), and SIGTERM it.

Why not env-var scanning via ``ps eww``: macOS 12+ restricts env
disclosure to root, so the ``ATOMICOPS_DISPATCHED=1`` marker we set on
spawn is invisible to us. PID files on disk are the only reliable way
to identify dispatched children at user privilege.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from scripts._helpers import get_db, is_valid_session_id, now_iso, tz_name

router = APIRouter()

_BOOT_AT = time.time()


# ---------------------------------------------------------------------------
# Queue layout (mirrored from api_ops; kept duplicated to avoid an import cycle)
# ---------------------------------------------------------------------------


def _queue_root() -> Path:
    env = os.environ.get("CC_QUEUE_DIR")
    if env:
        return Path(env).expanduser()
    home = os.environ.get("CC_DATA_DIR")
    if home:
        return Path(home).expanduser() / ".tmp" / "mission-control-queue"
    return Path.home() / ".command-centre" / "data" / ".tmp" / "mission-control-queue"


def _pid_dir() -> Path:
    return _queue_root() / "pids"


# ---------------------------------------------------------------------------
# /api/system/health
# ---------------------------------------------------------------------------


def _seconds_since(ts: str | None) -> float | None:
    if not ts:
        return None
    try:
        from datetime import datetime as _dt

        s = ts.replace("Z", "+00:00")
        return time.time() - _dt.fromisoformat(s).timestamp()
    except Exception:
        return None


@router.get("/api/system/health")
def system_health(request: Request) -> dict[str, Any]:
    state = request.app.state
    last_otel_age = (time.time() - state.last_otel_event_at) if state.last_otel_event_at else None
    last_sync_age = (time.time() - state.last_sync_tick_at) if state.last_sync_tick_at else None
    last_notifier_age = (
        (time.time() - state.last_notifier_tick_at)
        if state.last_notifier_tick_at
        else None
    )
    with get_db() as conn:
        last_heartbeat_row = conn.execute(
            """
            SELECT created_at FROM activities
             WHERE event_type = 'heartbeat'
          ORDER BY id DESC
             LIMIT 1
            """
        ).fetchone()
    last_daemon_age = _seconds_since(
        last_heartbeat_row["created_at"] if last_heartbeat_row else None
    )

    try:
        import resource

        raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS returns bytes, Linux kilobytes. Use sys.platform — heuristics
        # on the magnitude are unreliable for small processes.
        if sys.platform == "darwin":
            rss_mb = raw / 1024 / 1024
        else:
            rss_mb = raw / 1024
    except Exception:
        rss_mb = None

    return {
        "ok": True,
        "uptime_seconds": round(time.time() - _BOOT_AT, 2),
        "memory_mb": round(rss_mb, 1) if rss_mb else None,
        "last_otel_event_age_s": last_otel_age,
        "last_sync_tick_age_s": last_sync_age,
        "last_notifier_tick_age_s": last_notifier_age,
        "last_daemon_tick_age_s": last_daemon_age,
        "otel_events_seen": state.otel_events_seen,
        "otel_events_dropped": state.otel_events_dropped,
        "tz": tz_name(),
    }


# ---------------------------------------------------------------------------
# /api/system/state
# ---------------------------------------------------------------------------


@router.get("/api/system/state")
def system_state() -> dict[str, Any]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT key, value, updated_at FROM system_state"
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


# ---------------------------------------------------------------------------
# Emergency stop
# ---------------------------------------------------------------------------


def _is_claude_p_process(pid: int) -> bool:
    """Is this PID a ``claude -p ...`` invocation?"""
    try:
        out = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        ).stdout.strip()
    except Exception:
        return False
    return ("claude" in out) and (" -p" in out or out.endswith(" -p"))


@router.post("/api/system/emergency-stop")
async def emergency_stop() -> dict[str, Any]:
    pid_dir = _pid_dir()
    killed = 0
    spared = 0
    if pid_dir.exists():
        for entry in pid_dir.iterdir():
            try:
                pid = int(entry.name)
            except ValueError:
                continue
            try:
                os.kill(pid, 0)  # liveness probe
            except OSError:
                # Process gone — clean stale marker.
                entry.unlink(missing_ok=True)
                continue
            if not _is_claude_p_process(pid):
                spared += 1
                continue
            try:
                os.kill(pid, signal.SIGTERM)
                killed += 1
            except OSError:
                pass
            entry.unlink(missing_ok=True)
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO system_state (key, value, updated_at)
            VALUES ('emergency_stop', '1', ?)
            ON CONFLICT(key) DO UPDATE SET
              value = excluded.value, updated_at = excluded.updated_at
            """,
            (now_iso(),),
        )
        conn.execute(
            """
            UPDATE ops_tasks
               SET status = 'failed',
                   error_message = 'Emergency stop triggered',
                   completed_at = ?
             WHERE status = 'running'
            """,
            (now_iso(),),
        )
    return {
        "stopped": True,
        "processes_killed": killed,
        "interactive_spared": spared,
    }


@router.post("/api/system/emergency-resume")
def emergency_resume() -> dict[str, Any]:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO system_state (key, value, updated_at)
            VALUES ('emergency_stop', '0', ?)
            ON CONFLICT(key) DO UPDATE SET
              value = excluded.value, updated_at = excluded.updated_at
            """,
            (now_iso(),),
        )
    return {"resumed": True}


# ---------------------------------------------------------------------------
# /api/attention
# ---------------------------------------------------------------------------


@router.get("/api/attention")
def attention() -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    with get_db() as conn:
        # Stale dispatcher: heartbeat older than 5 min
        last_hb = conn.execute(
            """
            SELECT created_at FROM activities
             WHERE event_type = 'heartbeat'
          ORDER BY id DESC
             LIMIT 1
            """
        ).fetchone()
        if not last_hb:
            issues.append(
                {
                    "kind": "dispatcher_never_started",
                    "label": "Mission Control daemon hasn't checked in",
                    "severity": "warn",
                }
            )
        else:
            age = _seconds_since(last_hb["created_at"]) or 0
            if age > 300:
                issues.append(
                    {
                        "kind": "dispatcher_stale",
                        "label": f"Dispatcher hasn't ticked in {int(age)}s",
                        "severity": "warn" if age < 900 else "error",
                    }
                )
        # Recent failed tasks
        failed = conn.execute(
            """
            SELECT id, title, error_message
              FROM ops_tasks
             WHERE status = 'failed'
               AND completed_at >= datetime('now', '-24 hours')
          ORDER BY completed_at DESC
             LIMIT 5
            """
        ).fetchall()
        for r in failed:
            issues.append(
                {
                    "kind": "task_failed",
                    "task_id": r["id"],
                    "label": f"Task #{r['id']} failed: {r['title']}",
                    "detail": r["error_message"],
                    "severity": "error",
                }
            )
        # Pending decisions
        decisions = conn.execute(
            "SELECT COUNT(*) FROM ops_decisions WHERE status = 'pending'"
        ).fetchone()[0]
        if decisions:
            issues.append(
                {
                    "kind": "decisions_pending",
                    "label": f"{decisions} decision{'s' if decisions != 1 else ''} waiting on you",
                    "severity": "warn",
                }
            )
        # Loop detected events from activities
        loops = conn.execute(
            """
            SELECT detail, created_at FROM activities
             WHERE event_type = 'loop_detected'
               AND created_at >= datetime('now', '-1 hour')
          ORDER BY id DESC LIMIT 5
            """
        ).fetchall()
        for r in loops:
            issues.append(
                {
                    "kind": "loop_detected",
                    "label": r["detail"] or "Loop detected",
                    "severity": "warn",
                }
            )
    return {"items": issues, "count": len(issues)}


# ---------------------------------------------------------------------------
# /api/firehose — SSE of recent OTEL events
# ---------------------------------------------------------------------------


async def _firehose_stream() -> AsyncIterator[bytes]:
    """Tail otel_events and emit JSON SSE frames as new rows arrive."""
    last_id = 0
    with get_db() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(id), 0) FROM otel_events"
        ).fetchone()
        last_id = row[0] or 0

    yield b": ready\n\n"
    while True:
        try:
            with get_db() as conn:
                rows = conn.execute(
                    """
                    SELECT id, event_name, session_id, model, tool_name,
                           tool_duration_ms, mcp_server_name, mcp_tool_name,
                           timestamp
                      FROM otel_events
                     WHERE id > ?
                  ORDER BY id ASC
                     LIMIT 50
                    """,
                    (last_id,),
                ).fetchall()
            for r in rows:
                last_id = r["id"]
                payload = json.dumps(dict(r), ensure_ascii=False)
                yield f"data: {payload}\n\n".encode()
            await asyncio.sleep(1.0 if rows else 2.0)
        except asyncio.CancelledError:
            return


@router.get("/api/firehose")
async def firehose() -> StreamingResponse:
    return StreamingResponse(
        _firehose_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Live sessions
# ---------------------------------------------------------------------------


@router.get("/api/sessions/live")
def sessions_live() -> dict[str, Any]:
    """Sessions whose latest tool_call is within the last 5 minutes."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT s.session_id, s.title, s.cwd, s.git_branch, s.model,
                   s.started_at, s.total_tokens,
                   MAX(tc.ts) AS last_tool_ts,
                   COUNT(tc.tool_use_id) AS tool_count,
                   ls.state AS live_state, ls.current_tool AS live_current_tool,
                   ls.updated_at AS live_updated_at
              FROM sessions s
              LEFT JOIN tool_calls tc ON tc.session_id = s.session_id
              LEFT JOIN live_session_state ls ON ls.session_id = s.session_id
             WHERE s.started_at >= datetime('now', '-1 day')
          GROUP BY s.session_id
            HAVING (last_tool_ts IS NOT NULL AND
                    julianday('now') - julianday(last_tool_ts) < (5.0 / 1440.0))
                OR (ls.updated_at IS NOT NULL AND
                    julianday('now') - julianday(ls.updated_at) < (5.0 / 1440.0))
          ORDER BY COALESCE(last_tool_ts, ls.updated_at) DESC
            """
        ).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        items.append(d)
    return {"items": items}


@router.get("/api/sessions/live/{session_id}/state")
def session_live_state(session_id: str) -> dict[str, Any]:
    if not is_valid_session_id(session_id):
        raise HTTPException(422, "invalid session id")
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT session_id, state, current_tool, updated_at
              FROM live_session_state WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
    if row is None:
        return {
            "session_id": session_id,
            "state": None,
            "current_tool": None,
            "updated_at": None,
        }
    return dict(row)


@router.get("/api/sessions/live/{session_id}/stream")
async def session_live_stream(session_id: str) -> StreamingResponse:
    if not is_valid_session_id(session_id):
        raise HTTPException(422, "invalid session id")

    async def _stream() -> AsyncIterator[bytes]:
        # Tail the JSONL file. On macOS sessions live under
        # ~/.claude/projects/<hash>/<sid>.jsonl — we have to scan for it.
        root = Path.home() / ".claude" / "projects"
        target: Path | None = None
        for candidate in root.glob(f"*/{session_id}.jsonl"):
            target = candidate
            break
        if target is None:
            yield b": session not found\n\n"
            return
        offset = target.stat().st_size  # tail from end
        yield b": ready\n\n"
        while True:
            try:
                size = target.stat().st_size
                if size > offset:
                    with target.open("r", encoding="utf-8", errors="replace") as f:
                        f.seek(offset)
                        for line in f:
                            line = line.rstrip("\n")
                            if not line:
                                continue
                            yield f"data: {line}\n\n".encode()
                        offset = f.tell()
                await asyncio.sleep(0.6)
            except asyncio.CancelledError:
                return
            except FileNotFoundError:
                yield b": session file gone\n\n"
                return

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class LiveMessage(BaseModel):
    body: str


@router.post("/api/sessions/live/{session_id}/message")
def session_live_message(session_id: str, payload: LiveMessage) -> dict[str, Any]:
    if not is_valid_session_id(session_id):
        raise HTTPException(422, "invalid session id")
    qfile = _queue_root() / f"{session_id}.jsonl"
    qfile.parent.mkdir(parents=True, exist_ok=True)
    with qfile.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {"type": "user_followup", "body": payload.body, "ts": now_iso()},
                ensure_ascii=False,
            )
            + "\n"
        )
    return {"queued": True, "queue_file": str(qfile)}


# ---------------------------------------------------------------------------
# Manual sync trigger
# ---------------------------------------------------------------------------


@router.post("/api/sync")
async def manual_sync() -> dict[str, Any]:
    from scripts.sync_sessions import run_once

    stats = await asyncio.to_thread(run_once)
    return stats.__dict__


# ---------------------------------------------------------------------------
# Dispatcher trigger
# ---------------------------------------------------------------------------


def _heartbeat_path() -> Path:
    """Resolve the on-disk path of heartbeat.py. The skill files live
    outside the ``scripts/`` package so we walk up from this file until
    we find the ``.claude/skills/mission-control/`` directory."""
    here = Path(__file__).resolve()
    for ancestor in [here.parent, *here.parents]:
        candidate = ancestor / ".claude" / "skills" / "mission-control" / "heartbeat.py"
        if candidate.exists():
            return candidate
    return Path.home() / ".command-centre" / ".claude" / "skills" / "mission-control" / "heartbeat.py"


@router.post("/api/dispatcher/trigger")
async def dispatcher_trigger() -> dict[str, Any]:
    """Spawn a one-shot dispatcher run via subprocess. Returns
    immediately; the dispatcher logs to its own stderr stream."""
    venv_python = sys.executable
    hb = _heartbeat_path()
    if not hb.exists():
        return {"triggered": False, "reason": f"heartbeat.py not found at {hb}"}
    cmd = [venv_python, str(hb), "--once"]

    def _spawn() -> int:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return proc.pid

    try:
        pid = await asyncio.to_thread(_spawn)
        return {"triggered": True, "pid": pid}
    except FileNotFoundError:
        return {"triggered": False, "reason": "python or heartbeat missing"}


# ---------------------------------------------------------------------------
# MCP / skills sync
# ---------------------------------------------------------------------------


@router.post("/api/mcp/sync")
async def mcp_sync() -> dict[str, Any]:
    try:
        from scripts.mcp_analyzer import rebuild as _rebuild

        rows = await asyncio.to_thread(_rebuild)
        return {"synced": True, "servers": rows}
    except ImportError:
        return {"synced": False, "reason": "mcp_analyzer not installed"}


@router.post("/api/mcp/measure")
async def mcp_measure() -> dict[str, Any]:
    try:
        from scripts.mcp_analyzer import measure_all as _measure

        rows = await asyncio.to_thread(_measure)
        return {"measured": True, "servers": rows}
    except ImportError:
        return {"measured": False, "reason": "mcp_analyzer not installed"}


@router.post("/api/skills/sync")
async def skills_sync() -> dict[str, Any]:
    try:
        from scripts.sync_skills import run_once as _sync

        n = await asyncio.to_thread(_sync)
        return {"synced": True, "skills": n}
    except ImportError:
        return {"synced": False, "reason": "sync_skills not installed"}


class AutonomyUpdate(BaseModel):
    autonomy_level: str
    environment: str | None = None


@router.patch("/api/skills/{name}/autonomy")
def skills_autonomy(name: str, payload: AutonomyUpdate) -> dict[str, Any]:
    if payload.autonomy_level not in {"auto", "review", "manual"}:
        raise HTTPException(400, "invalid autonomy_level")
    with get_db() as conn:
        if payload.environment:
            cur = conn.execute(
                """
                UPDATE skills SET autonomy_level = ?
                 WHERE name = ? AND environment = ?
                """,
                (payload.autonomy_level, name, payload.environment),
            )
        else:
            cur = conn.execute(
                "UPDATE skills SET autonomy_level = ? WHERE name = ?",
                (payload.autonomy_level, name),
            )
        if cur.rowcount == 0:
            raise HTTPException(404, "skill not found")
    return {"updated": cur.rowcount}
