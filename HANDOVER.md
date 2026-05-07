# Handover

A practical guide for keeping Command Centre alive and debugging when
something looks off.

## Daily check

```bash
$ cc doctor
```

Should be all green. If not, the failures tell you what to fix.

## Where things live

| Thing                              | Path                                                                 |
|------------------------------------|----------------------------------------------------------------------|
| Source of truth (this repo)        | `~/git/projects/own/claude-code-dashboard`                           |
| Runtime install                    | `~/.command-centre`                                                  |
| SQLite DB                          | `~/.command-centre/data/commandcentre.db`                            |
| WAL companion                      | `…/commandcentre.db-wal`                                             |
| Server log                         | `~/.command-centre/logs/server.log`                                  |
| Mission Control launchd log        | `~/.command-centre/logs/mission-control.{out,err}.log`               |
| Telegram launchd log               | `~/.command-centre/logs/telegram-bot.{out,err}.log`                  |
| Mission Control PID markers        | `~/.command-centre/data/.tmp/mission-control-queue/pids/`            |
| Decision answer queue              | `~/.command-centre/data/.tmp/mission-control-queue/answers/<id>.jsonl` |
| Live-session follow-up queue       | `~/.command-centre/data/.tmp/mission-control-queue/<sid>.jsonl`      |
| OTEL settings (the global ones)    | `~/.claude/settings.json` `env` block                                |

## Auto-start

Both daemons are launchd-managed. They start at login (no terminal
needed) and respawn within ~30 s of any unexpected exit (`ThrottleInterval` guard).

| Agent label                          | What it runs                                |
|--------------------------------------|---------------------------------------------|
| `com.commandcentre.server`           | The FastAPI / uvicorn dashboard server.     |
| `com.commandcentre.mission-control`  | The heartbeat → dispatcher loop (120 s tick). |
| `com.commandcentre.telegram-bot`     | (Optional) Telegram polling daemon.         |

## Restart cycle

```bash
$ cc start    # idempotent — loads + kickstarts the server agent
$ cc stop     # bootout (server stays down until cc start)
$ cc restart  # kickstart -k (clean kill+respawn under launchd)
```

For the dispatcher:

```bash
$ launchctl unload ~/Library/LaunchAgents/com.commandcentre.mission-control.plist
$ launchctl load -w ~/Library/LaunchAgents/com.commandcentre.mission-control.plist
```

## Common failure modes

### Dashboard shows zero new OTEL events

1. Did you restart Claude Code after the OTEL wizard wrote the settings?
2. `cc doctor` — confirms the 6 keys are present.
3. `tail -f ~/.command-centre/logs/server.log` while triggering Claude
   Code — you should see "OTEL log batch: …" lines.
4. Check the catch-all isn't shadowing /v1/logs:
   `curl -X POST -d '{}' http://127.0.0.1:8765/v1/logs` should return
   `{}` not a 404 JSON body.

### Mission Control daemon never checks in

1. `launchctl list | grep commandcentre` — must show `com.commandcentre.mission-control`.
2. `tail -f ~/.command-centre/logs/mission-control.err.log` — Python tracebacks land here.
3. Verify `claude` CLI is on the launchd PATH: the plist sets
   `PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin`. Adjust if
   yours lives elsewhere.

### A task is stuck in `running` forever

1. `lsof -p <pid>` on the PID file in `pids/` — is the child alive?
2. `cc doctor` — daemon tick age >> 120 s means launchd lost the agent.
3. Worst case: hit the red "Stop dispatched runs" button. Tasks
   currently in `running` flip to `failed` with `error_message='Emergency stop triggered'`.

### Emergency-stop killed your interactive `claude -p` in another terminal

It shouldn't — we PID-file gate every dispatched child and verify
`ps -p` argv before sending SIGTERM. If it does, you found a bug:

* Check `~/.command-centre/data/.tmp/mission-control-queue/pids/` for
  stale entries.
* The dispatcher cleans these on a heartbeat tick via `_sweep_stale_pids`.
* If a PID got recycled, the `_is_claude_p_process` check should still
  spare it. Capture the surrounding `ps -ef` output before re-running.

### UI builds but the page is blank

1. Open dev tools → Network. Look for a 404 on `/assets/index-*.js`.
2. `ls ~/.command-centre/ui/dist` — is the bundle there?
3. Re-run `npm run build` in the repo's `ui/` and re-`cp -R ui/dist
   ~/.command-centre/ui/dist`.

### "low sample" badges everywhere

The cache panel and edit-decisions panel are honest about small N. The
target sample for cache is 10 K billable tokens; for edit decisions it's
10 events. Run more sessions or lower the thresholds in
`scripts/api_query.py` if you want.

## Telegram

Skipped at install by default. `cc setup telegram` runs the wizard.
**Use a separate bot from the marketplace plugin** — two long-poll
consumers on the same token drop updates between processes.

## Rebuilding after edits

| What changed       | What to do                              |
|--------------------|-----------------------------------------|
| Python script      | `cc restart`                            |
| UI source          | `cd ui && npm run build && cp -R dist ~/.command-centre/ui/dist`  |
| Schema (db.py)     | `cc restart` — schema is created on boot, columns are migrated via `_migrate_add_column`. |
| Skill files        | Restart launchd agent.                  |

## Resetting the dashboard

```bash
$ cc stop
$ rm ~/.command-centre/data/commandcentre.db*
$ cc start
$ cc sync
```

This wipes all session/OTEL/HITL/task data and re-imports from the
JSONLs. OTEL events from before the wipe are gone.

## Where to look for bugs

* **Routing** — `scripts/server.py` _UI hosting_ block must stay last.
* **JSONL schema drift** — `scripts/sync_sessions.py::_process_event`
  is where new top-level event types or content-block kinds need to
  land.
* **OTEL attribute renames** — `scripts/otel_parser.py::_LOG_FIELDS`
  is the lookup table. Add new variants there.
* **Marker parser** — `dispatcher.py::_MarkerParser` skips fenced
  blocks. If markers stop firing, the regex or the fence detection is
  the suspect.
