#!/usr/bin/env bash
# Command Centre launcher shim.
#
#   cc start       — boot the server
#   cc stop        — kill it
#   cc restart     — stop + start
#   cc doctor      — green/red health checks (no LLM)
#   cc setup otel  — run the OTEL wizard
#   cc setup telegram — run the Telegram wizard
#   cc sync        — fire one JSONL sync tick
#   cc logs        — tail server.log

set -euo pipefail

# Locate install dir. The shim itself lives at $INSTALL_DIR/bin/cc, so
# we walk one level up. Allow override via CC_INSTALL_DIR.
SHIM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${CC_INSTALL_DIR:-$(cd "$SHIM_DIR/.." && pwd)}"

if [[ ! -f "$INSTALL_DIR/config" ]]; then
  echo "× $INSTALL_DIR/config not found — run install.sh first" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$INSTALL_DIR/config"
[[ -f "$INSTALL_DIR/.env" ]] && set -a && . "$INSTALL_DIR/.env" && set +a

usage() {
  sed -n '/^# Command Centre launcher/,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# *//'
  exit 1
}

SERVER_PLIST="$HOME/Library/LaunchAgents/com.commandcentre.server.plist"
SERVER_LABEL="com.commandcentre.server"
USE_LAUNCHD=1
[[ -f "$SERVER_PLIST" ]] || USE_LAUNCHD=0

cmd="${1:-}"
case "$cmd" in
  start)
    if [[ "$USE_LAUNCHD" -eq 1 ]]; then
      # Idempotent load + kickstart. If already loaded, load is a no-op
      # (stderr suppressed). kickstart -k forces a clean restart.
      launchctl load -w "$SERVER_PLIST" 2>/dev/null || true
      launchctl kickstart -k "gui/$(id -u)/$SERVER_LABEL" 2>/dev/null || true
    else
      pkill -f "scripts.server" 2>/dev/null || true
      nohup "$INSTALL_DIR/start.sh" > "$INSTALL_DIR/logs/server.log" 2>&1 &
    fi
    sleep 0.8
    echo "✓ started on http://127.0.0.1:${CC_PORT:-8765}"
    ;;
  stop)
    if [[ "$USE_LAUNCHD" -eq 1 ]]; then
      # bootout removes the agent so launchd won't respawn it. Use
      # `cc start` to bring it back.
      launchctl bootout "gui/$(id -u)/$SERVER_LABEL" 2>/dev/null \
        || launchctl unload "$SERVER_PLIST" 2>/dev/null || true
      echo "✓ server stopped (launchd unload)"
    else
      "$INSTALL_DIR/stop.sh"
    fi
    ;;
  restart)
    if [[ "$USE_LAUNCHD" -eq 1 ]]; then
      launchctl load -w "$SERVER_PLIST" 2>/dev/null || true
      launchctl kickstart -k "gui/$(id -u)/$SERVER_LABEL"
      sleep 0.6
      echo "✓ restarted"
    else
      "$INSTALL_DIR/stop.sh" 2>/dev/null || true
      sleep 0.5
      pkill -f "scripts.server" 2>/dev/null || true
      nohup "$INSTALL_DIR/start.sh" > "$INSTALL_DIR/logs/server.log" 2>&1 &
      sleep 0.6
      echo "✓ restarted"
    fi
    ;;
  doctor)
    cd "$INSTALL_DIR"
    "$PYTHON" -m scripts.doctor
    ;;
  setup)
    sub="${2:-}"
    case "$sub" in
      otel)
        cd "$INSTALL_DIR"
        CC_INSTALL_DIR="$INSTALL_DIR" "$PYTHON" -m scripts.setup_otel "${@:3}"
        ;;
      telegram)
        cd "$INSTALL_DIR"
        CC_INSTALL_DIR="$INSTALL_DIR" "$PYTHON" -m scripts.setup_telegram "${@:3}"
        ;;
      *) echo "usage: cc setup {otel|telegram}" >&2; exit 1 ;;
    esac
    ;;
  sync)
    cd "$INSTALL_DIR"
    "$PYTHON" -m scripts.sync_sessions
    ;;
  logs)
    tail -F "$INSTALL_DIR/logs/server.log"
    ;;
  ""|-h|--help|help)
    usage
    ;;
  *)
    echo "unknown command: $cmd" >&2
    usage
    ;;
esac
