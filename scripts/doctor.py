"""Deterministic health check.

No LLM calls. Each check prints a coloured pass/fail line and
contributes to the overall exit code: 0 when every critical check
passes, non-zero otherwise.

Use this from the launcher (``cc doctor``) or from CI to verify a
fresh install without touching the dashboard backend.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

try:
    import requests  # type: ignore
except ImportError:
    requests = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Pretty printing
# ---------------------------------------------------------------------------


GREEN = "\x1b[32m"
RED = "\x1b[31m"
YELLOW = "\x1b[33m"
DIM = "\x1b[2m"
RESET = "\x1b[0m"


def _ok(label: str, detail: str = "") -> None:
    print(f"  {GREEN}✓{RESET} {label}{(' · ' + detail) if detail else ''}")


def _warn(label: str, detail: str = "") -> None:
    print(f"  {YELLOW}!{RESET} {label}{(' · ' + detail) if detail else ''}")


def _fail(label: str, detail: str = "") -> None:
    print(f"  {RED}×{RESET} {label}{(' · ' + detail) if detail else ''}")


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_python(critical: list[bool]) -> None:
    v = sys.version_info
    if v.major == 3 and v.minor >= 10:
        _ok("Python", f"{v.major}.{v.minor}.{v.micro}")
    elif v.major == 3 and v.minor == 9:
        _warn("Python 3.9", "OK but PEP 604 unions outside annotations may bite — prefer 3.10+")
        critical.append(True)
    else:
        _fail("Python", f"{v.major}.{v.minor}.{v.micro} — need 3.10+")
        critical.append(False)


def check_claude_cli(critical: list[bool]) -> None:
    path = shutil.which("claude")
    if not path:
        _warn("claude CLI", "not on PATH — Mission Control can't dispatch tasks")
        return
    try:
        r = subprocess.run(
            ["claude", "--version"], capture_output=True, text=True, timeout=5
        )
        version = r.stdout.strip() or r.stderr.strip()
    except Exception:
        version = "(version unknown)"
    _ok("claude CLI", f"{path} · {version}")


def check_settings_json(critical: list[bool]) -> None:
    p = Path.home() / ".claude" / "settings.json"
    if not p.exists():
        _fail("~/.claude/settings.json", "missing — run `cc setup otel`")
        critical.append(False)
        return
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _fail("~/.claude/settings.json", f"invalid JSON ({exc})")
        critical.append(False)
        return
    env = data.get("env") or {}
    required = [
        "CLAUDE_CODE_ENABLE_TELEMETRY",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_PROTOCOL",
        "OTEL_METRICS_EXPORTER",
        "OTEL_LOGS_EXPORTER",
        "OTEL_LOG_TOOL_DETAILS",
    ]
    missing = [k for k in required if k not in env or env[k] in (None, "", False)]
    if missing:
        _fail("OTEL keys", f"missing: {', '.join(missing)} — run `cc setup otel`")
        critical.append(False)
    else:
        _ok("OTEL keys", "all 6 set")


def check_projects_dir(critical: list[bool]) -> None:
    p = Path.home() / ".claude" / "projects"
    if not p.exists():
        _warn("~/.claude/projects", "missing — start a Claude Code session to populate")
        return
    files = list(p.glob("*/*.jsonl"))
    if not files:
        _warn("~/.claude/projects", "no session files yet")
    else:
        _ok("~/.claude/projects", f"{len(files)} sessions on disk")


def check_port(port: int, critical: list[bool]) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        try:
            s.connect(("127.0.0.1", port))
            _ok(f"port {port}", "dashboard listening")
        except (socket.error, OSError):
            _warn(f"port {port}", "not reachable — start with `cc start`")


def check_health_endpoint(port: int, critical: list[bool]) -> None:
    if requests is None:
        return
    try:
        r = requests.get(f"http://127.0.0.1:{port}/api/system/health", timeout=2)
    except requests.RequestException:
        return
    if not r.ok:
        _warn("/api/system/health", f"HTTP {r.status_code}")
        return
    j = r.json()
    bits = []
    if j.get("uptime_seconds") is not None:
        bits.append(f"up {int(j['uptime_seconds'])}s")
    if j.get("memory_mb"):
        bits.append(f"{j['memory_mb']:.0f} MB")
    if j.get("last_otel_event_age_s") is not None:
        bits.append(f"otel age {int(j['last_otel_event_age_s'])}s")
    if j.get("last_daemon_tick_age_s") is not None:
        bits.append(f"daemon age {int(j['last_daemon_tick_age_s'])}s")
    _ok("/api/system/health", " · ".join(bits) or "ok")


def check_launchd(name: str, critical: list[bool]) -> None:
    try:
        r = subprocess.run(
            ["launchctl", "list"], capture_output=True, text=True, timeout=4
        )
    except Exception as exc:  # noqa: BLE001
        _warn(f"launchctl ({name})", str(exc))
        return
    if name in r.stdout:
        _ok(f"launchd · {name}", "loaded")
    else:
        _warn(f"launchd · {name}", "not loaded — `cc start` to enable")


def check_telegram() -> None:
    if requests is None:
        return
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=4)
        if r.ok and r.json().get("ok"):
            _ok("Telegram bot", r.json()["result"].get("username", "(no username)"))
        else:
            _warn("Telegram bot", "getMe returned not-ok")
    except requests.RequestException as exc:
        _warn("Telegram bot", f"network: {exc}")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> int:
    port = int(os.environ.get("CC_PORT", "8765"))
    print("Command Centre · doctor")
    print("=======================")
    critical: list[bool] = []
    check_python(critical)
    check_claude_cli(critical)
    check_settings_json(critical)
    check_projects_dir(critical)
    project_root = os.environ.get("CC_PROJECT_ROOT")
    if project_root:
        _ok("CC_PROJECT_ROOT", project_root)
    else:
        _warn("CC_PROJECT_ROOT", "unset (only relevant when launching from skill scripts)")
    check_port(port, critical)
    check_health_endpoint(port, critical)
    check_launchd("com.commandcentre.server", critical)
    check_launchd("com.commandcentre.mission-control", critical)
    check_launchd("com.commandcentre.telegram-bot", critical)
    check_telegram()

    print()
    if all(critical):
        print(f"{GREEN}all critical checks passed{RESET}")
        return 0
    print(f"{RED}critical checks failed — see above{RESET}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
