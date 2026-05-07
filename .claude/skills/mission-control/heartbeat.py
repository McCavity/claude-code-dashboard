#!/usr/bin/env python3
"""launchd entry point for Mission Control.

Each tick we:

1. Materialize any due ``ops_schedules`` rows into ``ops_tasks``.
2. Invoke ``dispatcher.run_once()``.
3. Append a heartbeat row to ``activities`` so the dashboard's
   "stale dispatcher" detector turns green.

Pass ``--once`` and we exit after a single tick. Without it we loop on
the configured interval (defaults to 120 s) — useful for debugging
outside of launchd.
"""

from __future__ import annotations

import _bootstrap  # noqa: F401

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

from scripts._helpers import now_iso, parse_cron_simple  # noqa: E402
from scripts.db import connect  # noqa: E402

import dispatcher  # noqa: E402  (sibling)

log = logging.getLogger("commandcentre.heartbeat")


def _materialize_schedules(conn: sqlite3.Connection) -> int:
    """Promote due schedules into ops_tasks rows. Recompute next_run_at.

    Wrapped in BEGIN IMMEDIATE so two concurrent heartbeats can't
    double-materialize a schedule."""
    materialised = 0
    conn.execute("BEGIN IMMEDIATE")
    try:
        rows = conn.execute(
            """
            SELECT id, name, cron_expression, task_title, task_description,
                   assigned_skill
              FROM ops_schedules
             WHERE enabled = 1
               AND (next_run_at IS NULL OR next_run_at <= ?)
            """,
            (now_iso(),),
        ).fetchall()
        for r in rows:
            conn.execute(
                """
                INSERT INTO ops_tasks
                  (title, description, status, priority, assigned_skill,
                   execution_mode, quadrant, created_at)
                VALUES (?, ?, 'pending', 50, ?, 'classic', 'do', ?)
                """,
                (
                    r["task_title"],
                    r["task_description"],
                    r["assigned_skill"],
                    now_iso(),
                ),
            )
            try:
                next_run = parse_cron_simple(r["cron_expression"]).astimezone(
                    timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            except Exception:  # noqa: BLE001
                next_run = None
            conn.execute(
                "UPDATE ops_schedules SET next_run_at = ?, last_run_at = ? WHERE id = ?",
                (next_run, now_iso(), r["id"]),
            )
            materialised += 1
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return materialised


def _heartbeat_row(conn: sqlite3.Connection, payload: dict) -> None:
    conn.execute(
        """
        INSERT INTO activities (event_type, detail, metadata, created_at)
        VALUES ('heartbeat', ?, ?, ?)
        """,
        (
            f"picked={payload.get('picked', 0)} "
            f"materialised={payload.get('materialised', 0)} "
            f"swept={payload.get('swept', 0)}",
            json.dumps(payload, ensure_ascii=False),
            now_iso(),
        ),
    )


def tick() -> dict:
    started = time.monotonic()
    conn = connect()
    try:
        materialised = _materialize_schedules(conn)
    finally:
        conn.close()
    result = dispatcher.run_once()
    payload = {**result, "materialised": materialised}
    payload["tick_elapsed_s"] = round(time.monotonic() - started, 2)
    conn = connect()
    try:
        _heartbeat_row(conn, payload)
    finally:
        conn.close()
    return payload


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run a single tick and exit")
    parser.add_argument(
        "--interval",
        type=int,
        default=int(os.environ.get("MISSION_CONTROL_HEARTBEAT_INTERVAL", "120")),
        help="Seconds between ticks when not in --once mode",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=os.environ.get("CC_LOG_LEVEL", "info").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if args.once:
        payload = tick()
        print(json.dumps(payload, indent=2))
        return 0

    while True:
        try:
            payload = tick()
            log.info("heartbeat: %s", payload)
        except Exception:  # noqa: BLE001
            log.exception("heartbeat tick failed")
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
