"""Atomic operations on ``ops_tasks``.

Every state transition that the dispatcher cares about goes through one
of these helpers so the SQL is reviewed in one place. The atomic claim
is the most important part: the dispatcher and a manual ``--once`` run
must not race.
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  (sys.path bootstrap)

import sqlite3
from typing import Any

from scripts._helpers import now_iso  # noqa: E402  (after bootstrap)


def claim_pending(conn: sqlite3.Connection, task_id: int) -> dict[str, Any] | None:
    """Atomically transition ``pending → running`` for a single task.

    Returns the row as a dict, or ``None`` if the row was already taken
    by another worker. Stamps ``started_at``."""
    cur = conn.execute(
        """
        UPDATE ops_tasks
           SET status = 'running', started_at = ?
         WHERE id = ? AND status = 'pending'
        """,
        (now_iso(), task_id),
    )
    if cur.rowcount == 0:
        return None
    row = conn.execute(
        "SELECT * FROM ops_tasks WHERE id = ?", (task_id,)
    ).fetchone()
    return dict(row) if row else None


def list_pending(conn: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    """Return up to ``limit`` runnable tasks, highest priority first.
    Honours ``scheduled_for`` — future tasks are skipped."""
    return [
        dict(r)
        for r in conn.execute(
            """
            SELECT * FROM ops_tasks
             WHERE status = 'pending'
               AND (scheduled_for IS NULL OR scheduled_for <= ?)
          ORDER BY priority DESC, created_at ASC
             LIMIT ?
            """,
            (now_iso(), limit),
        ).fetchall()
    ]


def update_session(conn: sqlite3.Connection, task_id: int, session_id: str) -> None:
    conn.execute(
        "UPDATE ops_tasks SET session_id = ? WHERE id = ?",
        (session_id, task_id),
    )


def promote_to_awaiting_approval(conn: sqlite3.Connection, task_id: int) -> None:
    conn.execute(
        """
        UPDATE ops_tasks
           SET status = 'awaiting_approval', started_at = NULL
         WHERE id = ? AND status = 'running'
        """,
        (task_id,),
    )


def complete_task(
    conn: sqlite3.Connection,
    task_id: int,
    *,
    output_summary: str | None = None,
    duration_ms: int | None = None,
    cost_usd: float | None = None,
) -> None:
    conn.execute(
        """
        UPDATE ops_tasks
           SET status = 'done',
               completed_at = ?,
               output_summary = ?,
               duration_ms = ?,
               cost_usd = ?,
               consecutive_failures = 0,
               error_message = NULL
         WHERE id = ?
        """,
        (now_iso(), output_summary, duration_ms, cost_usd, task_id),
    )


def fail_task(
    conn: sqlite3.Connection,
    task_id: int,
    *,
    error_message: str,
    duration_ms: int | None = None,
) -> None:
    conn.execute(
        """
        UPDATE ops_tasks
           SET status = 'failed',
               completed_at = ?,
               error_message = ?,
               duration_ms = ?,
               consecutive_failures = COALESCE(consecutive_failures, 0) + 1
         WHERE id = ?
        """,
        (now_iso(), error_message, duration_ms, task_id),
    )


def cancel_task(conn: sqlite3.Connection, task_id: int) -> None:
    conn.execute(
        """
        UPDATE ops_tasks
           SET status = 'cancelled', completed_at = ?
         WHERE id = ?
        """,
        (now_iso(), task_id),
    )
