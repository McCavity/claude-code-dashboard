#!/usr/bin/env python3
"""Claude Code hook target that mirrors session lifecycle events into
``live_session_state``.

Wired up in ``~/.claude/settings.json`` by the OTEL setup wizard (or by
hand) under every relevant hook event. Reads a single JSON payload
from stdin; **must complete fast** — hooks run synchronously inside
Claude Code's tool loop. If anything fails we exit silently with code
0 so we never block the host.

Settings.json snippet emitted by the wizard:

    "hooks": {
      "PreToolUse":  [{"matcher": "*", "hooks": [{"type":"command","command":"<install>/.claude/skills/mission-control/session_state_hook.py"}]}],
      "PostToolUse": [{"matcher": "*", "hooks": [{"type":"command","command":"<install>/.claude/skills/mission-control/session_state_hook.py"}]}],
      "Stop":        [{"matcher": "*", "hooks": [{"type":"command","command":"<install>/.claude/skills/mission-control/session_state_hook.py"}]}]
    }
"""

from __future__ import annotations

import _bootstrap  # noqa: F401

import json
import sys
from typing import Any

from scripts._helpers import now_iso  # noqa: E402
from scripts.db import connect  # noqa: E402


_EVENT_TO_STATE = {
    "SessionStart": "starting",
    "UserPromptSubmit": "thinking",
    "PreToolUse": "tool_use",
    "PostToolUse": "thinking",
    "Stop": "idle",
    "SubagentStop": "idle",
    "SessionEnd": "ended",
    "Notification": "notification",
}


def _read_payload() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def main() -> int:
    payload = _read_payload()
    if not payload:
        return 0
    session_id = (
        payload.get("session_id")
        or payload.get("sessionId")
        or (payload.get("session") or {}).get("id")
    )
    if not session_id:
        return 0
    hook_event = payload.get("hook_event_name") or payload.get("event")
    state = _EVENT_TO_STATE.get(hook_event or "", "active")
    tool_name: str | None = None
    tool = payload.get("tool_use") or payload.get("tool") or {}
    if isinstance(tool, dict):
        tool_name = tool.get("name")
    if not tool_name:
        tool_name = payload.get("tool_name")

    try:
        conn = connect()
        try:
            conn.execute(
                """
                INSERT INTO live_session_state (session_id, state, current_tool, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                  state = excluded.state,
                  current_tool = COALESCE(excluded.current_tool, live_session_state.current_tool),
                  updated_at = excluded.updated_at
                """,
                (session_id, state, tool_name, now_iso()),
            )
        finally:
            conn.close()
    except Exception:
        # Never break the host loop on a DB hiccup.
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
