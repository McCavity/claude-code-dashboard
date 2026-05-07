"""SQLite schema, migrations, and connection helper.

Single source of truth for the Command Centre database. Every table is
``CREATE TABLE IF NOT EXISTS`` so ``init_schema()`` is safe to call on
every server boot. Column additions are handled via
``_migrate_add_column`` which tolerates pre-existing columns.

Usage:

    from scripts.db import connect, init_schema
    conn = connect()        # opens default DB, sets WAL, runs init_schema
    rows = conn.execute("SELECT * FROM sessions LIMIT 5").fetchall()
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DEFAULT_HOME = Path.home() / ".command-centre"
_DEFAULT_DB = _DEFAULT_HOME / "data" / "commandcentre.db"


def db_path() -> Path:
    """Resolve the active DB path. Honors ``CC_DB_PATH`` env override."""
    override = os.environ.get("CC_DB_PATH")
    if override:
        return Path(override).expanduser()
    return _DEFAULT_DB


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open (or create) the DB. Sets WAL, foreign keys, runs migrations."""
    target = Path(path).expanduser() if path else db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    init_schema(conn)
    return conn


# ---------------------------------------------------------------------------
# Migration helper
# ---------------------------------------------------------------------------


def _migrate_add_column(
    conn: sqlite3.Connection, table: str, col: str, sql_type: str
) -> None:
    """Add a column if missing. Idempotent."""
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {sql_type}")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


_TABLES: list[str] = [
    # Session-level rollup, one row per JSONL session.
    """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id          TEXT PRIMARY KEY,
        source              TEXT NOT NULL DEFAULT 'ide',
        cwd                 TEXT,
        git_branch          TEXT,
        model               TEXT,
        started_at          TEXT,
        ended_at            TEXT,
        input_tokens        INTEGER NOT NULL DEFAULT 0,
        output_tokens       INTEGER NOT NULL DEFAULT 0,
        cache_read_tokens   INTEGER NOT NULL DEFAULT 0,
        cache_create_tokens INTEGER NOT NULL DEFAULT 0,
        total_tokens        INTEGER NOT NULL DEFAULT 0,
        effective_tokens    INTEGER NOT NULL DEFAULT 0,
        cost_usd            REAL    NOT NULL DEFAULT 0,
        duration_ms         INTEGER,
        error_count         INTEGER NOT NULL DEFAULT 0,
        rate_limit_hit      INTEGER NOT NULL DEFAULT 0,
        stop_reason         TEXT,
        title               TEXT,
        synced_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )
    """,
    # Daily token rollup, keyed by (date, model, source).
    """
    CREATE TABLE IF NOT EXISTS token_usage (
        date                TEXT NOT NULL,
        model               TEXT NOT NULL,
        source              TEXT NOT NULL,
        input_tokens        INTEGER NOT NULL DEFAULT 0,
        output_tokens       INTEGER NOT NULL DEFAULT 0,
        cache_read_tokens   INTEGER NOT NULL DEFAULT 0,
        cache_create_tokens INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (date, model, source)
    )
    """,
    # Flattened tool invocations, one row per tool_use/tool_result pair.
    """
    CREATE TABLE IF NOT EXISTS tool_calls (
        session_id   TEXT NOT NULL,
        tool_use_id  TEXT NOT NULL,
        tool_name    TEXT NOT NULL,
        ts           TEXT NOT NULL,
        duration_ms  INTEGER,
        error        TEXT,
        PRIMARY KEY (session_id, tool_use_id)
    )
    """,
    # OTLP log events.
    """
    CREATE TABLE IF NOT EXISTS otel_events (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        event_name              TEXT NOT NULL,
        session_id              TEXT,
        prompt_id               TEXT,
        timestamp               TEXT NOT NULL,
        model                   TEXT,
        tool_name               TEXT,
        tool_success            INTEGER,
        tool_duration_ms        INTEGER,
        tool_error              TEXT,
        cost_usd                REAL,
        api_duration_ms         INTEGER,
        input_tokens            INTEGER,
        output_tokens           INTEGER,
        cache_read_tokens       INTEGER,
        cache_create_tokens     INTEGER,
        speed                   REAL,
        error_message           TEXT,
        status_code             INTEGER,
        attempt_count           INTEGER,
        skill_name              TEXT,
        skill_source            TEXT,
        prompt_length           INTEGER,
        decision                TEXT,
        decision_source         TEXT,
        request_id              TEXT,
        tool_result_size_bytes  INTEGER,
        mcp_server_scope        TEXT,
        plugin_name             TEXT,
        plugin_version          TEXT,
        marketplace_name        TEXT,
        install_trigger         TEXT,
        mcp_server_name         TEXT,
        mcp_tool_name           TEXT,
        received_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )
    """,
    # OTLP metrics.
    """
    CREATE TABLE IF NOT EXISTS otel_metrics (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        metric_name TEXT NOT NULL,
        metric_type TEXT NOT NULL,
        value       REAL NOT NULL,
        session_id  TEXT,
        model       TEXT,
        timestamp   TEXT NOT NULL
    )
    """,
    # Mission Control task queue.
    """
    CREATE TABLE IF NOT EXISTS ops_tasks (
        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        title                 TEXT NOT NULL,
        description           TEXT,
        status                TEXT NOT NULL DEFAULT 'pending',
        priority              INTEGER NOT NULL DEFAULT 50,
        assigned_skill        TEXT,
        model                 TEXT,
        execution_mode        TEXT NOT NULL DEFAULT 'classic',
        scheduled_for         TEXT,
        requires_approval     INTEGER NOT NULL DEFAULT 0,
        risk_level            TEXT NOT NULL DEFAULT 'low',
        dry_run               INTEGER NOT NULL DEFAULT 0,
        quadrant              TEXT NOT NULL DEFAULT 'do',
        approved_at           TEXT,
        session_id            TEXT,
        started_at            TEXT,
        completed_at          TEXT,
        duration_ms           INTEGER,
        cost_usd              REAL,
        output_summary        TEXT,
        error_message         TEXT,
        consecutive_failures  INTEGER NOT NULL DEFAULT 0,
        created_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )
    """,
    # Recurring schedules — materialize into ops_tasks on each tick.
    """
    CREATE TABLE IF NOT EXISTS ops_schedules (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        name              TEXT NOT NULL,
        cron_expression   TEXT NOT NULL,
        task_title        TEXT NOT NULL,
        task_description  TEXT,
        assigned_skill    TEXT,
        enabled           INTEGER NOT NULL DEFAULT 1,
        next_run_at       TEXT,
        last_run_at       TEXT,
        created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )
    """,
    # Human-in-the-loop decisions surfaced from DECISION: markers.
    """
    CREATE TABLE IF NOT EXISTS ops_decisions (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id      INTEGER,
        session_id   TEXT,
        prompt       TEXT NOT NULL,
        answer       TEXT,
        status       TEXT NOT NULL DEFAULT 'pending',
        created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        answered_at  TEXT
    )
    """,
    # Non-blocking agent ↔ user messaging.
    """
    CREATE TABLE IF NOT EXISTS ops_inbox (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id     INTEGER,
        session_id  TEXT,
        direction   TEXT NOT NULL,
        body        TEXT NOT NULL,
        read        INTEGER NOT NULL DEFAULT 0,
        created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )
    """,
    # Append-only activity log (heartbeats, sync, loop-detected events).
    """
    CREATE TABLE IF NOT EXISTS activities (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type  TEXT NOT NULL,
        detail      TEXT,
        metadata    TEXT,
        created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )
    """,
    # Realtime session state, written by session_state_hook.py.
    """
    CREATE TABLE IF NOT EXISTS live_session_state (
        session_id    TEXT PRIMARY KEY,
        state         TEXT,
        current_tool  TEXT,
        updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )
    """,
    # MCP server-level stats (from mcp_analyzer / sync).
    """
    CREATE TABLE IF NOT EXISTS mcp_stats (
        server        TEXT PRIMARY KEY,
        tools         INTEGER,
        total_tokens  INTEGER,
        error         TEXT,
        measured_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )
    """,
    # MCP per-tool schemas + token cost.
    """
    CREATE TABLE IF NOT EXISTS mcp_schemas (
        server        TEXT NOT NULL,
        tool          TEXT NOT NULL,
        schema_json   TEXT,
        tokens        INTEGER,
        collected_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        PRIMARY KEY (server, tool)
    )
    """,
    # Skill registry. ``environment`` differentiates ide:project /
    # ide:global / cowork:plugin / cowork:scheduled.
    """
    CREATE TABLE IF NOT EXISTS skills (
        name             TEXT NOT NULL,
        environment      TEXT NOT NULL,
        description      TEXT,
        path             TEXT,
        autonomy_level   TEXT NOT NULL DEFAULT 'review',
        user_invocable   INTEGER NOT NULL DEFAULT 0,
        script_count     INTEGER NOT NULL DEFAULT 0,
        last_modified    TEXT,
        PRIMARY KEY (name, environment)
    )
    """,
    # Generic key-value system state. Known keys: emergency_stop.
    """
    CREATE TABLE IF NOT EXISTS system_state (
        key         TEXT PRIMARY KEY,
        value       TEXT,
        updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )
    """,
    # Internal: per-session daily token contribution. Lets us rebuild
    # token_usage idempotently on incremental re-syncs without
    # double-counting. Not part of the public API surface.
    """
    CREATE TABLE IF NOT EXISTS session_token_breakdown (
        session_id          TEXT NOT NULL,
        date                TEXT NOT NULL,
        model               TEXT NOT NULL,
        source              TEXT NOT NULL,
        input_tokens        INTEGER NOT NULL DEFAULT 0,
        output_tokens       INTEGER NOT NULL DEFAULT 0,
        cache_read_tokens   INTEGER NOT NULL DEFAULT 0,
        cache_create_tokens INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (session_id, date, model, source)
    )
    """,
    # Telegram dedup ledger.
    """
    CREATE TABLE IF NOT EXISTS notification_log (
        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type            TEXT NOT NULL,
        event_key             TEXT NOT NULL,
        sent_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        chat_id               TEXT,
        telegram_message_id   INTEGER,
        snoozed_until         TEXT,
        UNIQUE (event_type, event_key, chat_id)
    )
    """,
]


_INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_tool_calls_name_ts        ON tool_calls(tool_name, ts)",
    "CREATE INDEX IF NOT EXISTS idx_tool_calls_session        ON tool_calls(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_otel_events_ts            ON otel_events(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_otel_events_event_name    ON otel_events(event_name, timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_otel_events_session       ON otel_events(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_otel_metrics_name_ts      ON otel_metrics(metric_name, timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_started          ON sessions(started_at)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_ended            ON sessions(ended_at)",
    "CREATE INDEX IF NOT EXISTS idx_ops_tasks_status          ON ops_tasks(status, priority)",
    "CREATE INDEX IF NOT EXISTS idx_ops_tasks_session         ON ops_tasks(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_ops_schedules_next_run    ON ops_schedules(enabled, next_run_at)",
    "CREATE INDEX IF NOT EXISTS idx_activities_event_ts       ON activities(event_type, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_ops_decisions_status      ON ops_decisions(status, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_ops_inbox_unread          ON ops_inbox(read, direction, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_session_breakdown_date    ON session_token_breakdown(date, model, source)",
    # Partial UNIQUE on ops_decisions to dedupe duplicate marker lines
    # without blocking ad-hoc decisions that lack a session_id.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_ops_decisions_session_prompt
    ON ops_decisions(session_id, prompt)
    WHERE session_id IS NOT NULL
    """,
]


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


def init_schema(conn: sqlite3.Connection) -> None:
    """Create every missing table + index. Run idempotent migrations."""
    for ddl in _TABLES:
        conn.execute(ddl)
    for ddl in _INDEXES:
        conn.execute(ddl)
    # Migration helpers go here once we ship column additions in later
    # phases. They are no-ops on a freshly created DB.


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def list_tables(conn: sqlite3.Connection) -> list[str]:
    return [
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]


if __name__ == "__main__":
    c = connect()
    print(f"db: {db_path()}")
    print("tables:")
    for t in list_tables(c):
        print(f"  - {t}")
    integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
    print(f"integrity: {integrity}")
