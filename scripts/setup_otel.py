"""Interactive OTEL setup wizard.

Patches ``~/.claude/settings.json`` so every Claude Code session this
user starts pushes telemetry to the local dashboard. We:

1. Show which of the 6 OTEL keys are missing.
2. Prompt for confirmation (skipped with ``--yes``).
3. Back up ``settings.json`` to ``settings.json.bak.<timestamp>``.
4. Merge in only the missing keys — never overwrite the user's
   existing values.

The hook for ``session_state_hook.py`` is added under
``hooks.PreToolUse / PostToolUse / Stop`` only when the wizard is run
with ``--with-hook`` so a user who declined live-session tracking can
keep their hooks file untouched.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REQUIRED_KEYS: dict[str, str] = {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:8765",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_LOG_TOOL_DETAILS": "1",
}

HOOK_EVENTS = ["PreToolUse", "PostToolUse", "Stop", "SubagentStop", "SessionEnd"]


def settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _read_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"× Cannot parse {path} — {exc}", file=sys.stderr)
        return {}


def _missing_keys(env: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in REQUIRED_KEYS.items():
        if k not in env or env[k] in (None, "", False):
            out[k] = v
    return out


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_suffix(f".json.bak.{ts}")
    shutil.copy2(path, backup)
    return backup


def _add_hook_command(settings: dict[str, Any], hook_path: str) -> None:
    """Wire up session_state_hook.py to the lifecycle events we care about.
    Only adds the entry if the same command isn't already registered."""
    hooks = settings.setdefault("hooks", {})
    for event in HOOK_EVENTS:
        arr = hooks.setdefault(event, [])
        if not isinstance(arr, list):
            continue
        # Each entry: {"matcher": ..., "hooks": [{"type":"command","command":"..."}]}
        already = False
        for entry in arr:
            if not isinstance(entry, dict):
                continue
            inner = entry.get("hooks") or []
            if not isinstance(inner, list):
                continue
            for h in inner:
                if isinstance(h, dict) and h.get("command") == hook_path:
                    already = True
                    break
            if already:
                break
        if already:
            continue
        arr.append({
            "matcher": "*",
            "hooks": [{"type": "command", "command": hook_path}],
        })


def _hook_path() -> str:
    install_dir = os.environ.get("CC_INSTALL_DIR")
    if install_dir:
        return str(Path(install_dir).expanduser() / ".claude" / "skills" / "mission-control" / "session_state_hook.py")
    return str(Path.home() / ".command-centre" / ".claude" / "skills" / "mission-control" / "session_state_hook.py")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Wire Claude Code OTEL into Command Centre.")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    parser.add_argument("--with-hook", action="store_true", help="Also register session_state_hook.py")
    parser.add_argument("--no-hook", action="store_true", help="Skip the hook registration even when interactive")
    parser.add_argument("--dry-run", action="store_true", help="Print the diff and exit; touch nothing")
    args = parser.parse_args(argv)

    target = settings_path()
    settings = _read_settings(target)
    env = settings.setdefault("env", {})
    if not isinstance(env, dict):
        print("× existing settings.json has 'env' that isn't a dict — refusing to overwrite", file=sys.stderr)
        return 1

    missing = _missing_keys(env)
    if missing:
        print("→ Will add these keys to settings.json[env]:")
        for k, v in missing.items():
            print(f"    {k} = {v}")
    else:
        print("✓ All 6 OTEL keys already set.")

    install_hook = bool(args.with_hook)
    if install_hook is False and not args.no_hook and not args.yes:
        ans = input("Wire session_state_hook.py for live-session tracking? [Y/n] ").strip().lower()
        install_hook = ans in ("", "y", "yes")
    if install_hook:
        print(f"→ Will add hook command to PreToolUse/PostToolUse/Stop: {_hook_path()}")

    if not (missing or install_hook):
        print("Nothing to do.")
        return 0

    if args.dry_run:
        print("--dry-run; not writing.")
        return 0

    if not args.yes:
        ans = input(f"Patch {target}? [Y/n] ").strip().lower()
        if ans not in ("", "y", "yes"):
            print("aborted.")
            return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    backup = _backup(target)
    if backup is not None:
        print(f"backup written to {backup}")

    for k, v in missing.items():
        env[k] = v
    if install_hook:
        _add_hook_command(settings, _hook_path())

    target.write_text(
        json.dumps(settings, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(f"✓ wrote {target}")
    print()
    print("Restart Claude Code (quit + reopen) so it picks up the new settings.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
