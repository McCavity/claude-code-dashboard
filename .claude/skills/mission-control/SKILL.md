---
name: mission-control
description: Background dispatcher that materializes scheduled tasks, runs them via `claude -p`, parses DECISION:/INBOX: markers from streaming output, and writes a live state row per session. Operates on the Command Centre SQLite DB.
type: skill
---

# Mission Control

This is not a user-invocable skill. It is the *daemon side* of Command
Centre: a launchd-driven Python loop that fires every 120 seconds.

## Files

| File | Role |
|------|------|
| `heartbeat.py` | launchd entry point. Tick = materialize schedules + dispatcher run + heartbeat row. |
| `dispatcher.py` | Picks pending tasks, spawns `claude -p` children, parses streamed output. |
| `task_tracker.py` | Atomic ops_tasks operations (claim, complete, fail). |
| `skill_router.py` | Optional Haiku call that picks a skill for unassigned tasks. |
| `session_state_hook.py` | Claude Code hook target — writes `live_session_state` rows. |

## Concurrency model

* `MAX_CONCURRENT` (env, default 3) tasks may run at once.
* Each child gets a marker file at
  `<data>/.tmp/mission-control-queue/pids/<pid>` so the dashboard's
  emergency-stop can SIGTERM them without false-positives on
  unrelated `claude -p` terminals.
* Tasks are claimed atomically: `UPDATE ops_tasks SET status='running'
  WHERE id=? AND status='pending'` — only the row whose rowcount is 1
  proceeds. Daemon and `--once` runs cannot race.

## Markers Claude can write

Inside any `claude -p` output (stream or classic mode), prefix a line
with one of:

* `DECISION: <prompt>` — surfaces a HITL question on the dashboard.
  Block the run for ≤ TASK_TIMEOUT_SECONDS or until answered.
* `INBOX: <body>` — non-blocking note posted to the user inbox.

Markers inside triple-backtick fenced blocks are ignored.

## Hook target

`session_state_hook.py` is wired into Claude Code's settings.json hooks
array by `setup_otel.py` so the dashboard's LiveSessionsCard can show
real-time `state` and `current_tool` for every session.
