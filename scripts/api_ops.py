"""HITL, tasks, schedules.

These endpoints back the Mission Control panels and the dispatcher
loop. Writes go through small CRUD helpers; reads are raw SQL.

Validation and side-effects:

  * ``POST /api/decisions`` uses ``INSERT OR IGNORE`` against the
    partial UNIQUE index ``uq_ops_decisions_session_prompt`` so the
    dispatcher can re-emit the same DECISION marker without spawning
    duplicates.
  * ``POST /api/decisions/{id}/answer`` writes the answer to a queue
    file ``.tmp/mission-control-queue/answers/{id}`` so the dispatcher
    stream loop can inject it into stdin once.
  * ``POST /api/tasks/{id}/rerun`` only accepts ``status='failed'`` —
    400 otherwise.
  * ``POST /api/schedules/parse-nl`` calls Haiku via the Anthropic SDK
    when ``ANTHROPIC_API_KEY`` is set; otherwise it returns a 503 so
    the UI can fall back to manual entry.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from scripts._helpers import get_db, now_iso, parse_cron_simple, tz_name

router = APIRouter()


# ---------------------------------------------------------------------------
# Queue file helpers
# ---------------------------------------------------------------------------


def _queue_root() -> Path:
    """``$CC_QUEUE_DIR`` overrides; default
    ``<install_dir>/data/.tmp/mission-control-queue``."""
    env = os.environ.get("CC_QUEUE_DIR")
    if env:
        return Path(env).expanduser()
    home = os.environ.get("CC_DATA_DIR")
    if home:
        return Path(home).expanduser() / ".tmp" / "mission-control-queue"
    return Path.home() / ".command-centre" / "data" / ".tmp" / "mission-control-queue"


def _write_queue_file(rel: str, line: dict[str, Any]) -> Path:
    p = _queue_root() / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return p


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------


class DecisionCreate(BaseModel):
    task_id: int | None = None
    session_id: str | None = None
    prompt: str


class DecisionAnswer(BaseModel):
    answer: str


@router.get("/api/decisions")
def list_decisions(status: str = Query("pending"), limit: int = 50) -> dict[str, Any]:
    if status not in {"pending", "answered", "all"}:
        raise HTTPException(status_code=400, detail="invalid status")
    where = "" if status == "all" else "WHERE status = ?"
    params: list[Any] = [] if status == "all" else [status]
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT id, task_id, session_id, prompt, answer, status,
                   created_at, answered_at
              FROM ops_decisions
             {where}
          ORDER BY created_at DESC
             LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.post("/api/decisions")
def create_decision(payload: DecisionCreate) -> dict[str, Any]:
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO ops_decisions
              (task_id, session_id, prompt, status, created_at)
            VALUES (?, ?, ?, 'pending', ?)
            """,
            (payload.task_id, payload.session_id, payload.prompt, now_iso()),
        )
        if cur.rowcount == 0:
            existing = conn.execute(
                """
                SELECT id FROM ops_decisions
                 WHERE session_id = ? AND prompt = ?
                """,
                (payload.session_id, payload.prompt),
            ).fetchone()
            return {"id": existing["id"] if existing else None, "created": False}
        return {"id": cur.lastrowid, "created": True}


@router.post("/api/decisions/{decision_id}/answer")
def answer_decision(decision_id: int, payload: DecisionAnswer) -> dict[str, Any]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, status, session_id FROM ops_decisions WHERE id = ?",
            (decision_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="decision not found")
        if row["status"] != "pending":
            raise HTTPException(status_code=400, detail="decision already answered")
        conn.execute(
            """
            UPDATE ops_decisions
               SET answer = ?, status = 'answered', answered_at = ?
             WHERE id = ?
            """,
            (payload.answer, now_iso(), decision_id),
        )
    _write_queue_file(
        f"answers/{decision_id}.jsonl",
        {
            "decision_id": decision_id,
            "answer": payload.answer,
            "answered_at": now_iso(),
        },
    )
    return {"answered": True}


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------


class InboxCreate(BaseModel):
    task_id: int | None = None
    session_id: str | None = None
    direction: str = "agent_to_user"
    body: str


class InboxReply(BaseModel):
    body: str


@router.get("/api/inbox")
def list_inbox(
    unread: int = 0, max_age_days: int = 30, limit: int = 100
) -> dict[str, Any]:
    clauses = ["created_at >= datetime('now', ?)"]
    params: list[Any] = [f"-{max_age_days} days"]
    if unread:
        clauses.append("read = 0")
        clauses.append("direction = 'agent_to_user'")
    where = " AND ".join(clauses)
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT id, task_id, session_id, direction, body, read, created_at
              FROM ops_inbox
             WHERE {where}
          ORDER BY created_at DESC
             LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.post("/api/inbox")
def create_inbox_message(payload: InboxCreate) -> dict[str, Any]:
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO ops_inbox
              (task_id, session_id, direction, body, read, created_at)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (
                payload.task_id,
                payload.session_id,
                payload.direction,
                payload.body,
                now_iso(),
            ),
        )
    return {"id": cur.lastrowid, "created": True}


@router.post("/api/inbox/{message_id}/read")
def mark_inbox_read(message_id: int) -> dict[str, Any]:
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE ops_inbox SET read = 1 WHERE id = ?", (message_id,)
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="message not found")
    return {"read": True}


@router.post("/api/inbox/{message_id}/reply")
def reply_inbox(message_id: int, payload: InboxReply) -> dict[str, Any]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, task_id, session_id FROM ops_inbox WHERE id = ?",
            (message_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="message not found")
        conn.execute(
            """
            INSERT INTO ops_inbox
              (task_id, session_id, direction, body, read, created_at)
            VALUES (?, ?, 'user_to_agent', ?, 1, ?)
            """,
            (row["task_id"], row["session_id"], payload.body, now_iso()),
        )
    if row["session_id"]:
        _write_queue_file(
            f"{row['session_id']}.jsonl",
            {"type": "user_reply", "body": payload.body, "ts": now_iso()},
        )
    return {"replied": True}


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


_VALID_TASK_STATUSES = {
    "pending",
    "awaiting_approval",
    "running",
    "done",
    "failed",
    "cancelled",
}
_VALID_QUADRANTS = {"do", "schedule", "delegate", "archive"}
_VALID_RISK = {"low", "medium", "high"}
_VALID_MODES = {"classic", "stream"}


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    priority: int = 50
    assigned_skill: str | None = None
    model: str | None = None
    execution_mode: str = "stream"
    scheduled_for: str | None = None
    requires_approval: bool = False
    risk_level: str = "low"
    dry_run: bool = False
    quadrant: str = "do"


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: int | None = None
    assigned_skill: str | None = None
    model: str | None = None
    execution_mode: str | None = None
    scheduled_for: str | None = None
    requires_approval: bool | None = None
    risk_level: str | None = None
    dry_run: bool | None = None
    quadrant: str | None = None


def _validate_task_inputs(
    *,
    quadrant: str | None,
    risk_level: str | None,
    execution_mode: str | None,
    status: str | None,
) -> None:
    if quadrant and quadrant not in _VALID_QUADRANTS:
        raise HTTPException(400, detail=f"invalid quadrant: {quadrant}")
    if risk_level and risk_level not in _VALID_RISK:
        raise HTTPException(400, detail=f"invalid risk_level: {risk_level}")
    if execution_mode and execution_mode not in _VALID_MODES:
        raise HTTPException(400, detail=f"invalid execution_mode: {execution_mode}")
    if status and status not in _VALID_TASK_STATUSES:
        raise HTTPException(400, detail=f"invalid status: {status}")


@router.get("/api/tasks")
def list_tasks(
    status: str | None = None,
    quadrant: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    clauses = []
    params: list[Any] = []
    if status:
        if status not in _VALID_TASK_STATUSES:
            raise HTTPException(400, "invalid status")
        clauses.append("status = ?")
        params.append(status)
    if quadrant:
        if quadrant not in _VALID_QUADRANTS:
            raise HTTPException(400, "invalid quadrant")
        clauses.append("quadrant = ?")
        params.append(quadrant)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM ops_tasks {where}
          ORDER BY
            CASE status
              WHEN 'awaiting_approval' THEN 0
              WHEN 'running' THEN 1
              WHEN 'pending' THEN 2
              WHEN 'failed' THEN 3
              WHEN 'done' THEN 4
              WHEN 'cancelled' THEN 5
              ELSE 6
            END,
            priority DESC,
            created_at DESC
             LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.post("/api/tasks")
def create_task(payload: TaskCreate) -> dict[str, Any]:
    _validate_task_inputs(
        quadrant=payload.quadrant,
        risk_level=payload.risk_level,
        execution_mode=payload.execution_mode,
        status=None,
    )
    initial_status = "awaiting_approval" if payload.requires_approval else "pending"
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO ops_tasks
              (title, description, status, priority, assigned_skill, model,
               execution_mode, scheduled_for, requires_approval, risk_level,
               dry_run, quadrant, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.title,
                payload.description,
                initial_status,
                payload.priority,
                payload.assigned_skill,
                payload.model,
                payload.execution_mode,
                payload.scheduled_for,
                int(payload.requires_approval),
                payload.risk_level,
                int(payload.dry_run),
                payload.quadrant,
                now_iso(),
            ),
        )
    return {"id": cur.lastrowid, "status": initial_status}


@router.patch("/api/tasks/{task_id}")
def update_task(task_id: int, payload: TaskUpdate) -> dict[str, Any]:
    _validate_task_inputs(
        quadrant=payload.quadrant,
        risk_level=payload.risk_level,
        execution_mode=payload.execution_mode,
        status=payload.status,
    )
    fields: dict[str, Any] = {}
    for col, val in payload.model_dump(exclude_none=True).items():
        if col in ("requires_approval", "dry_run"):
            fields[col] = int(val)
        else:
            fields[col] = val
    if not fields:
        return {"updated": False}
    sets = ", ".join(f"{k} = ?" for k in fields)
    params = list(fields.values()) + [task_id]
    with get_db() as conn:
        cur = conn.execute(
            f"UPDATE ops_tasks SET {sets} WHERE id = ?", params
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "task not found")
    return {"updated": True}


@router.delete("/api/tasks/{task_id}")
def delete_task(task_id: int) -> dict[str, Any]:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM ops_tasks WHERE id = ?", (task_id,))
    return {"deleted": cur.rowcount > 0}


@router.post("/api/tasks/{task_id}/approve")
def approve_task(task_id: int) -> dict[str, Any]:
    with get_db() as conn:
        cur = conn.execute(
            """
            UPDATE ops_tasks
               SET status = 'pending', approved_at = ?
             WHERE id = ? AND status = 'awaiting_approval'
            """,
            (now_iso(), task_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(400, "task not awaiting approval")
    return {"approved": True}


@router.post("/api/tasks/{task_id}/rerun")
def rerun_task(task_id: int) -> dict[str, Any]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT status FROM ops_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "task not found")
        if row["status"] != "failed":
            raise HTTPException(
                400, detail="rerun only allowed on failed tasks"
            )
        conn.execute(
            """
            UPDATE ops_tasks
               SET status = 'pending',
                   error_message = NULL,
                   completed_at = NULL,
                   started_at = NULL,
                   duration_ms = NULL,
                   output_summary = NULL,
                   session_id = NULL
             WHERE id = ?
            """,
            (task_id,),
        )
    return {"rerun": True, "task_id": task_id}


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------


class ScheduleCreate(BaseModel):
    name: str
    cron_expression: str
    task_title: str
    task_description: str | None = None
    assigned_skill: str | None = None
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    name: str | None = None
    cron_expression: str | None = None
    task_title: str | None = None
    task_description: str | None = None
    assigned_skill: str | None = None
    enabled: bool | None = None


def _next_run(cron_expr: str) -> str | None:
    try:
        return parse_cron_simple(cron_expr).astimezone(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
    except Exception:
        return None


def _validate_cron(cron_expr: str) -> None:
    """Reject an unparseable or never-matching cron up front (HTTP 422).

    Without this a schedule can be stored with a next_run_at that stays
    NULL forever, which the heartbeat treats as "due now" and re-spawns a
    task on every tick."""
    try:
        parse_cron_simple(cron_expr)
    except ValueError as exc:
        raise HTTPException(422, f"invalid cron_expression: {exc}") from exc


@router.get("/api/schedules")
def list_schedules() -> dict[str, Any]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, name, cron_expression, task_title, task_description,
                   assigned_skill, enabled, next_run_at, last_run_at,
                   created_at
              FROM ops_schedules
          ORDER BY enabled DESC, name
            """
        ).fetchall()
    return {"items": [dict(r) for r in rows], "tz": tz_name()}


@router.post("/api/schedules")
def create_schedule(payload: ScheduleCreate) -> dict[str, Any]:
    _validate_cron(payload.cron_expression)
    next_run = _next_run(payload.cron_expression) if payload.enabled else None
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO ops_schedules
              (name, cron_expression, task_title, task_description,
               assigned_skill, enabled, next_run_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.name,
                payload.cron_expression,
                payload.task_title,
                payload.task_description,
                payload.assigned_skill,
                int(payload.enabled),
                next_run,
                now_iso(),
            ),
        )
    return {"id": cur.lastrowid, "next_run_at": next_run}


@router.patch("/api/schedules/{schedule_id}")
def update_schedule(schedule_id: int, payload: ScheduleUpdate) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for col, val in payload.model_dump(exclude_none=True).items():
        if col == "enabled":
            fields[col] = int(val)
        else:
            fields[col] = val
    if "cron_expression" in fields:
        _validate_cron(fields["cron_expression"])
        # Force recompute of next_run_at on cron change.
        fields["next_run_at"] = _next_run(fields["cron_expression"])
    if not fields:
        return {"updated": False}
    sets = ", ".join(f"{k} = ?" for k in fields)
    params = list(fields.values()) + [schedule_id]
    with get_db() as conn:
        cur = conn.execute(
            f"UPDATE ops_schedules SET {sets} WHERE id = ?", params
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "schedule not found")
    return {"updated": True}


@router.delete("/api/schedules/{schedule_id}")
def delete_schedule(schedule_id: int) -> dict[str, Any]:
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM ops_schedules WHERE id = ?", (schedule_id,)
        )
    return {"deleted": schedule_id, "rowcount": cur.rowcount}


@router.get("/api/schedules/{schedule_id}/runs")
def schedule_runs(schedule_id: int, limit: int = 10) -> dict[str, Any]:
    with get_db() as conn:
        sched = conn.execute(
            "SELECT task_title FROM ops_schedules WHERE id = ?", (schedule_id,)
        ).fetchone()
        if sched is None:
            raise HTTPException(404, "schedule not found")
        rows = conn.execute(
            """
            SELECT id, status, started_at, completed_at, duration_ms,
                   output_summary, error_message, created_at
              FROM ops_tasks
             WHERE title = ?
          ORDER BY created_at DESC
             LIMIT ?
            """,
            (sched["task_title"], limit),
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


class ParseNLRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)


_PARSE_NL_PROMPT = """\
You translate informal English/German scheduling phrases into 5-field cron \
expressions (minute hour day-of-month month day-of-week, where day-of-week \
uses Mon=0..Sun=6 — Python weekday() convention). Reply with ONLY the cron \
string. No prose, no quotes.

Examples:
  every weekday at 9am             0 9 * * 0,1,2,3,4
  jeden tag um 7:30                30 7 * * *
  sundays at noon                  0 12 * * 6
  every 15 minutes                 */15 * * * *

Input: {text}
"""


@router.post("/api/schedules/parse-nl")
async def parse_nl(payload: ParseNLRequest) -> dict[str, Any]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY not set — fall back to manual cron entry",
        )
    try:
        import anthropic
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="anthropic SDK not installed in this venv",
        )

    def _call() -> str:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=64,
            messages=[
                {
                    "role": "user",
                    "content": _PARSE_NL_PROMPT.format(text=payload.text),
                }
            ],
        )
        # Concatenate text blocks of the response.
        parts = []
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                parts.append(block.text)
        return "".join(parts).strip().strip("`").strip()

    import asyncio

    try:
        cron = await asyncio.to_thread(_call)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"haiku call failed: {exc}")
    # Validate by computing next_run.
    next_run = _next_run(cron)
    if not next_run:
        raise HTTPException(status_code=400, detail=f"invalid cron from model: {cron}")
    return {"cron": cron, "next_run_at": next_run}
