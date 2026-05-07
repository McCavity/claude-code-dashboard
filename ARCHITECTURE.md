# Architecture

A bird's-eye look at the moving parts.

## Process map

```
                ┌──────────────────────────┐
                │  Claude Code (your IDE)  │
                │                          │
                │   reads ~/.claude/       │
                │     settings.json        │
                │   writes ~/.claude/      │
                │     projects/*.jsonl     │
                │   POSTs OTEL logs        │
                │     /metrics             │
                └────────────┬─────────────┘
                             │ HTTP
                             ▼
       ┌─────────────────────────────────────────────┐
       │      ~/.command-centre  (uvicorn process)    │
       │                                              │
       │   scripts/server.py                          │
       │     • /api/* endpoints (api_query, api_ops,  │
       │       api_system)                            │
       │     • /v1/logs, /v1/metrics  ← OTLP/JSON     │
       │     • static UI at /                         │
       │     • lifespan: sync_sessions tick / 120 s   │
       │                                              │
       │   data/commandcentre.db  (SQLite, WAL)       │
       │   data/.tmp/mission-control-queue/           │
       │     ├── pids/<pid>          marker files     │
       │     ├── answers/<id>.jsonl  decisions sink   │
       │     └── <session>.jsonl     follow-up queue  │
       └────────────────┬───────────────┬─────────────┘
                        │               │
                        │               │ subprocess.Popen
                        │               ▼
                        │   ┌────────────────────────┐
                        │   │ claude -p (dispatched) │
                        │   │ stdin/stdout NDJSON,   │
                        │   │ marker parser, PID     │
                        │   │ marker file written    │
                        │   └────────────────────────┘
                        │
                        │ launchd
                        ▼
       ┌─────────────────────────────────────────────┐
       │ com.commandcentre.mission-control            │
       │   .claude/skills/mission-control/heartbeat  │
       │   tick / 120 s                              │
       │     1. materialize ops_schedules            │
       │     2. dispatcher.run_once()                │
       │     3. activities heartbeat row             │
       └─────────────────────────────────────────────┘
```

## Tables (SQLite, WAL)

Sixteen application tables plus one internal aggregation cache:

| Table                       | Purpose                                                        |
|-----------------------------|----------------------------------------------------------------|
| `sessions`                  | One row per JSONL session, totals + metadata.                  |
| `tool_calls`                | Flattened tool_use → tool_result pairs. Indexed `(name, ts)`.  |
| `token_usage`               | Daily rollup `(date, model, source)`. Rebuilt from breakdown.  |
| `session_token_breakdown`   | Internal: per-session daily contribution. Lets us re-aggregate without double-counting. |
| `otel_events`               | Every OTLP log record, flattened to columns.                   |
| `otel_metrics`              | Every OTLP metric data point.                                  |
| `ops_tasks`                 | Mission Control queue. Status FSM.                             |
| `ops_schedules`             | Cron-driven recurring tasks.                                   |
| `ops_decisions`             | HITL Q&A. Partial UNIQUE on `(session_id, prompt)` for dedupe. |
| `ops_inbox`                 | Non-blocking agent ↔ user notes.                               |
| `activities`                | Append-only event log (heartbeat, sync_loop, loop_detected).   |
| `live_session_state`        | Realtime state row per session, written by hook.               |
| `mcp_stats`                 | Per-server measurement snapshots (tools count, total tokens).  |
| `mcp_schemas`               | Per-tool MCP schemas + token cost.                             |
| `skills`                    | Skill registry across IDE / Cowork environments.               |
| `system_state`              | KV; known key: `emergency_stop`.                               |
| `notification_log`          | Telegram dedupe. UNIQUE on `(event_type, event_key, chat_id)`. |

## Concurrency

| Concern                              | How we handle it                                                     |
|--------------------------------------|----------------------------------------------------------------------|
| Daemon + manual `--once` racing      | Atomic `UPDATE … WHERE status='pending'` then rowcount check.        |
| Two heartbeats materializing schedules concurrently | `BEGIN IMMEDIATE` around the materialise+update block.   |
| Dispatcher children outliving the heartbeat | The heartbeat exits when the batch finishes; launchd respawns it on the next tick. |
| Identifying dispatched children for emergency-stop | PID marker files in `data/.tmp/mission-control-queue/pids/`. Validated via `os.kill(pid, 0)` + `ps argv` check. |
| Sync rebuilding `token_usage` without double-count | Per-session `session_token_breakdown` table; `DELETE … FROM token_usage; INSERT … FROM session_token_breakdown` after each batch. |

## Why we don't use ps env-var scanning

macOS 12+ blocks env disclosure to non-root callers. The
`ATOMICOPS_DISPATCHED=1` we set on dispatched children is invisible to
`ps eww` at user privilege, so the only reliable way to identify "our"
children for emergency-stop is on-disk PID marker files. We still set
the env var for legacy parity but never depend on it.

## OTEL configuration scope

The installer writes the 6 OTEL keys into `~/.claude/settings.json` so
**every** Claude Code session — regardless of project — pushes telemetry
to the dashboard. This is a deliberate exception to the org-level rule
"keep configuration project-scoped." A single dashboard with a single
data source is the entire point of the build; per-project opt-in defeats
that goal.

The wizard takes a backup before patching and only adds missing keys —
it never overwrites pre-existing values.

## Routing notes

Static UI hosting registers **last** in `server.py`. The catch-all
`@app.get("/{full_path:path}")` would otherwise shadow `/api/health`,
`/v1/logs`, and `/v1/metrics`. Keep the order:

1. `app.include_router(query_router | ops_router | system_router)`
2. `@app.get("/api/health")`, `@app.post("/v1/logs")`, `@app.post("/v1/metrics")`
3. UI mount (`/assets`) and `@app.get("/")` and `@app.get("/{full_path:path}")`

## Local-time day buckets

Every analytics query buckets by `DATE(timestamp, 'localtime')`. UTC
bucketing breaks evening sessions: a session that runs from 22:00 to
01:00 local would otherwise span two UTC days, producing weird looking
trends. The `TZ` env var (or system default) decides what "local" means.
