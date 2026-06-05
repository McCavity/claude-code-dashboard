"""P1 hardening — Schedule NULL next_run_at endless-materialization fix.

A schedule whose cron never matches (or is unparseable) used to keep
``next_run_at = NULL`` forever, and the heartbeat treated NULL as
"due now" → it spawned a fresh ops_task every single tick. These tests
pin the two-layer fix: the heartbeat self-disables a broken schedule
(and logs it), and the API rejects an invalid cron up front (HTTP 422).
"""

import pytest
from fastapi import HTTPException

from scripts._helpers import now_iso
from scripts.db import connect

import heartbeat
from scripts.api_ops import ScheduleCreate, ScheduleUpdate, create_schedule, update_schedule


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Point get_db() at a throwaway DB so the API tests can never touch
    the real ~/.command-centre DB (matters most on the pre-fix RED run,
    where update_schedule would otherwise reach the live UPDATE)."""
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "api.db"))


def _add_schedule(conn, cron, enabled=1, next_run_at=None):
    conn.execute(
        """
        INSERT INTO ops_schedules
          (name, cron_expression, task_title, task_description,
           assigned_skill, enabled, next_run_at, created_at)
        VALUES (?, ?, 'T', 'D', NULL, ?, ?, ?)
        """,
        ("sched", cron, enabled, next_run_at, now_iso()),
    )


# --- heartbeat layer -------------------------------------------------------

def test_never_matching_cron_self_disables(tmp_path):
    conn = connect(tmp_path / "t.db")
    _add_schedule(conn, "0 0 30 2 *")  # 30 February — never fires

    first = heartbeat._materialize_schedules(conn)
    second = heartbeat._materialize_schedules(conn)

    assert first == 1          # bootstrap tick materializes exactly once
    assert second == 0         # must NOT spam a task on the next tick
    enabled = conn.execute("SELECT enabled FROM ops_schedules").fetchone()["enabled"]
    assert enabled == 0        # schedule disabled itself
    tasks = conn.execute("SELECT COUNT(*) AS c FROM ops_tasks").fetchone()["c"]
    assert tasks == 1          # only the single bootstrap task, no spam
    logged = conn.execute(
        "SELECT COUNT(*) AS c FROM activities WHERE event_type='schedule_disabled'"
    ).fetchone()["c"]
    assert logged == 1         # the auto-disable is visible in the activity log


def test_valid_cron_keeps_running(tmp_path):
    conn = connect(tmp_path / "t.db")
    _add_schedule(conn, "*/5 * * * *")  # every 5 minutes — always has a next run

    first = heartbeat._materialize_schedules(conn)
    second = heartbeat._materialize_schedules(conn)

    assert first == 1          # NULL next_run_at + NULL last_run_at → bootstrap fires
    assert second == 0         # next_run_at now in the future → not due again
    row = conn.execute("SELECT enabled, next_run_at FROM ops_schedules").fetchone()
    assert row["enabled"] == 1
    assert row["next_run_at"] is not None


# --- API layer -------------------------------------------------------------

def test_create_schedule_rejects_unparseable_cron():
    with pytest.raises(HTTPException) as exc:
        create_schedule(
            ScheduleCreate(
                name="x", cron_expression="not a cron",
                task_title="t", task_description="d",
            )
        )
    assert exc.value.status_code == 422


def test_create_schedule_rejects_never_matching_cron():
    with pytest.raises(HTTPException) as exc:
        create_schedule(
            ScheduleCreate(
                name="x", cron_expression="0 0 30 2 *",
                task_title="t", task_description="d",
            )
        )
    assert exc.value.status_code == 422


def test_update_schedule_rejects_bad_cron():
    with pytest.raises(HTTPException) as exc:
        update_schedule(1, ScheduleUpdate(cron_expression="61 99 * * *"))
    assert exc.value.status_code == 422
