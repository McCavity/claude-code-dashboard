# Command Centre

A local Claude Code dashboard that runs entirely on your Mac. No cloud,
no account, no outbound telemetry.

```
~/.command-centre  →  http://127.0.0.1:8765
```

## What it shows you

- Live sessions in flight, with tool-call timelines and a follow-up box
  for stream-mode tasks.
- Today's tokens, session outcomes, cache hit rate.
- Per-tool latency (p50/p95/max) and error rates.
- MCP servers ranked by p95 latency, drill down per tool.
- Skill registry with autonomy controls.
- Decisions and inbox messages from Mission Control tasks.
- A task board you can queue from the UI.

## Install

```bash
git clone <this repo>
cd claude-code-dashboard
./install.sh
```

The installer creates `~/.command-centre/`, a venv, a SQLite DB, copies
the built UI, optionally registers launchd agents, and walks an OTEL
setup wizard.

## Status

All twelve phases landed. See `ARCHITECTURE.md` for the system shape and
`HANDOVER.md` for the operational guide.

- [x] Phase 1 — Schema & Skeleton (16 tables + 1 internal aggregation)
- [x] Phase 2 — JSONL Sync (incremental, 281 file scan in ~1 s, idempotent)
- [x] Phase 3 — OTEL Ingest (`/v1/logs`, `/v1/metrics`, MCP sub-parse)
- [x] Phase 4 — API Surface (50+ endpoints; raw SQL; local-time day buckets)
- [x] Phase 5 — Mission Control Dispatcher (heartbeat, stream/classic, PID markers, launchd)
- [x] Phase 6 — UI Skeleton (Vite + React 18 + TS + Tailwind + TanStack Router)
- [x] Phase 7 — Command page panels (system, KPIs, live, usage, observability, HITL, mission)
- [x] Phase 8 — Activity & Skills/MCP pages (drill-down centerpiece, firehose SSE)
- [x] Phase 9 — HITL & live streaming (decisions/inbox flows, follow-up box)
- [x] Phase 10 — Setup UX (`install.sh`, `setup_otel`, `setup_telegram`, `doctor`, `cc` shim)
- [x] Phase 11 — Playwright e2e (home, activity, palette, schedule composer)
- [x] Phase 12 — Polish + ARCHITECTURE.md + HANDOVER.md

## OTEL note

The installer writes 6 OTEL keys into `~/.claude/settings.json` (with
backup) so every Claude Code session, regardless of project, is observable
in the dashboard. This is a deliberate exception to the org-level rule
"keep configuration project-scoped" — without it the dashboard would only
see a single project at a time, defeating the purpose. Decline the wizard
to keep settings.json untouched.
