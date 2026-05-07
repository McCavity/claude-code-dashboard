#!/usr/bin/env bash
# Command Centre — one-shot installer.
#
# Creates the runtime layout under ~/.command-centre/, sets up a
# Python venv, copies the built UI, optionally registers launchd
# agents, and walks the OTEL setup wizard.
#
# Args:
#   --yes                 skip every interactive prompt
#   --project-root=PATH   override CLAUDE_CODE projects dir
#   --port=N              dashboard port (default 8765)
#   --model=M             MISSION_CONTROL_DEFAULT_MODEL
#   --no-otel             skip the OTEL wizard
#   --no-launchd          do not load launchd agents
#   --telegram            run the Telegram wizard at the end
#   --no-telegram         explicitly skip the Telegram offer
#   --no-start            don't start the server at the end
#   --install-dir=PATH    override ~/.command-centre

set -euo pipefail

# ---- defaults ----
INSTALL_DIR="${HOME}/.command-centre"
PORT=8765
DEFAULT_MODEL="claude-sonnet-4-6"
PROJECT_ROOT_OVERRIDE=""
ASSUME_YES=0
SKIP_OTEL=0
SKIP_LAUNCHD=0
SKIP_START=0
TELEGRAM_MODE="ask"   # ask | yes | skip

usage() {
  sed -n '/^# Args:/,/^$/p' "$0" | sed 's/^# *//'
  exit 1
}

for arg in "$@"; do
  case "$arg" in
    --yes) ASSUME_YES=1 ;;
    --project-root=*) PROJECT_ROOT_OVERRIDE="${arg#*=}" ;;
    --port=*) PORT="${arg#*=}" ;;
    --model=*) DEFAULT_MODEL="${arg#*=}" ;;
    --install-dir=*) INSTALL_DIR="${arg#*=}" ;;
    --no-otel) SKIP_OTEL=1 ;;
    --no-launchd) SKIP_LAUNCHD=1 ;;
    --telegram) TELEGRAM_MODE="yes" ;;
    --no-telegram) TELEGRAM_MODE="skip" ;;
    --no-start) SKIP_START=1 ;;
    -h|--help) usage ;;
    *) echo "unknown arg: $arg" >&2; usage ;;
  esac
done

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Command Centre · install"
echo "========================"
echo "  install dir: $INSTALL_DIR"
echo "  port: $PORT"
echo "  default model: $DEFAULT_MODEL"

# ---- python detection ----
detect_python() {
  local candidates=(
    "/opt/homebrew/opt/python@3.14/libexec/bin/python3"
    "/opt/homebrew/opt/python@3.13/libexec/bin/python3"
    "/opt/homebrew/opt/python@3.12/libexec/bin/python3"
    "/opt/homebrew/opt/python@3.11/libexec/bin/python3"
    "/opt/homebrew/opt/python@3.10/libexec/bin/python3"
    "/usr/local/opt/python@3.12/libexec/bin/python3"
    "/usr/local/opt/python@3.11/libexec/bin/python3"
    "$(command -v python3.14 2>/dev/null || true)"
    "$(command -v python3.13 2>/dev/null || true)"
    "$(command -v python3.12 2>/dev/null || true)"
    "$(command -v python3.11 2>/dev/null || true)"
    "$(command -v python3.10 2>/dev/null || true)"
    "$(command -v python3.9 2>/dev/null || true)"
    "$(command -v python3 2>/dev/null || true)"
  )
  for c in "${candidates[@]}"; do
    if [[ -n "$c" && -x "$c" ]]; then
      "$c" -c 'import sys; (sys.exit(0) if sys.version_info >= (3,9) else sys.exit(1))' 2>/dev/null && {
        echo "$c"
        return 0
      }
    fi
  done
  return 1
}

PYTHON="$(detect_python || true)"
if [[ -z "${PYTHON:-}" ]]; then
  echo "× could not find a usable python3 (need 3.9+, prefer 3.10+)" >&2
  exit 2
fi
PY_VER="$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
echo "  python: $PYTHON ($PY_VER)"

# ---- project root resolution ----
if [[ -z "$PROJECT_ROOT_OVERRIDE" ]]; then
  PROJECT_ROOT="${HOME}/.claude/projects"
else
  PROJECT_ROOT="$PROJECT_ROOT_OVERRIDE"
fi
echo "  jsonl source: $PROJECT_ROOT"

# ---- cowork detection ----
COWORK_DIR_DEFAULT="$HOME/Library/Application Support/Claude/local-agent-mode-sessions"
COWORK_DIR=""
if [[ -d "$COWORK_DIR_DEFAULT" ]]; then
  COWORK_DIR="$COWORK_DIR_DEFAULT"
  echo "  cowork sessions: $COWORK_DIR"
fi

# ---- create layout ----
mkdir -p \
  "$INSTALL_DIR/scripts" \
  "$INSTALL_DIR/.claude/skills/mission-control" \
  "$INSTALL_DIR/.claude/skills/telegram" \
  "$INSTALL_DIR/ui/dist" \
  "$INSTALL_DIR/data" \
  "$INSTALL_DIR/logs" \
  "$INSTALL_DIR/bin" \
  "$INSTALL_DIR/templates/launchd"

# ---- copy python sources ----
echo "→ copying scripts and skills"
cp -R "$REPO_DIR/scripts/." "$INSTALL_DIR/scripts/"
cp -R "$REPO_DIR/.claude/skills/." "$INSTALL_DIR/.claude/skills/"
cp -R "$REPO_DIR/templates/." "$INSTALL_DIR/templates/"
cp "$REPO_DIR/requirements.txt" "$INSTALL_DIR/"

# ---- copy built UI ----
if [[ -d "$REPO_DIR/ui/dist" && -f "$REPO_DIR/ui/dist/index.html" ]]; then
  rm -rf "$INSTALL_DIR/ui/dist"
  cp -R "$REPO_DIR/ui/dist" "$INSTALL_DIR/ui/dist"
  echo "✓ UI bundle copied"
else
  echo "! ui/dist missing; building locally now"
  if command -v npm >/dev/null 2>&1; then
    (cd "$REPO_DIR/ui" && npm install --silent --no-audit --no-fund && npm run build)
    cp -R "$REPO_DIR/ui/dist" "$INSTALL_DIR/ui/dist"
  else
    echo "× npm not found — skipping UI build. Dashboard backend will run, UI will not." >&2
  fi
fi

# ---- venv ----
echo "→ creating venv"
"$PYTHON" -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip >/dev/null
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
echo "✓ venv ready"

# ---- seed config + .env ----
# Note on quoting: bash's ${VAR:+ALT} construct strips surrounding
# quotes from ALT during parameter expansion (even inside an unquoted
# heredoc), so paths with spaces — e.g. ~/Library/Application Support/
# — would land in the file unquoted and break ``source config``. We
# write the optional, space-prone CC_COWORK_SESSIONS_DIR line outside
# the heredoc using printf %q to guarantee it's safely quoted.
CONFIG_FILE="$INSTALL_DIR/config"
cat > "$CONFIG_FILE" <<EOF
# install-time snapshot. Do not edit by hand — re-run install.sh to update.
INSTALL_DIR="$INSTALL_DIR"
PYTHON="$INSTALL_DIR/.venv/bin/python"
CC_PORT=$PORT
CC_HOST=127.0.0.1
CC_DB_PATH="$INSTALL_DIR/data/commandcentre.db"
CC_DATA_DIR="$INSTALL_DIR/data"
CC_CLAUDE_PROJECTS_DIR="$PROJECT_ROOT"
MISSION_CONTROL_DEFAULT_MODEL="$DEFAULT_MODEL"
MISSION_CONTROL_MAX_CONCURRENT=3
MISSION_CONTROL_TASK_TIMEOUT_SECONDS=1800
EOF
if [[ -n "$COWORK_DIR" ]]; then
  printf 'CC_COWORK_SESSIONS_DIR=%q\n' "$COWORK_DIR" >> "$CONFIG_FILE"
fi

if [[ ! -f "$INSTALL_DIR/.env" ]]; then
  cp "$REPO_DIR/.env.example" "$INSTALL_DIR/.env"
  chmod 600 "$INSTALL_DIR/.env"
fi

# ---- launchers ----
cat > "$INSTALL_DIR/start.sh" <<'EOSTART'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/config"
[[ -f "$HERE/.env" ]] && set -a && . "$HERE/.env" && set +a
cd "$HERE"
exec "$PYTHON" -m scripts.server
EOSTART
chmod +x "$INSTALL_DIR/start.sh"

cat > "$INSTALL_DIR/stop.sh" <<'EOSTOP'
#!/usr/bin/env bash
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDS=$(lsof -ti:"$(grep -E '^CC_PORT=' "$HERE/config" | cut -d= -f2)" 2>/dev/null || true)
if [[ -n "$PIDS" ]]; then
  kill $PIDS && echo "stopped: $PIDS"
else
  echo "no server running"
fi
EOSTOP
chmod +x "$INSTALL_DIR/stop.sh"

# ---- cc shim ----
cp "$REPO_DIR/cc" "$INSTALL_DIR/bin/cc"
chmod +x "$INSTALL_DIR/bin/cc"

# Try a symlink into ~/.local/bin if it's on PATH.
if [[ ":$PATH:" == *":$HOME/.local/bin:"* ]]; then
  mkdir -p "$HOME/.local/bin"
  ln -sf "$INSTALL_DIR/bin/cc" "$HOME/.local/bin/cc"
  echo "✓ symlinked $HOME/.local/bin/cc"
else
  echo "  (note) $HOME/.local/bin not on PATH — invoke as $INSTALL_DIR/bin/cc"
fi

# ---- launchd plists ----
if [[ "$SKIP_LAUNCHD" -eq 0 ]]; then
  PLIST_DIR="$HOME/Library/LaunchAgents"
  mkdir -p "$PLIST_DIR"
  HEARTBEAT_PATH="$INSTALL_DIR/.claude/skills/mission-control/heartbeat.py"

  # Detect where ``claude`` lives so the launchd-managed dispatcher can
  # find it. launchd starts with a minimal PATH; if claude is in
  # ~/.local/bin (the default for the Anthropic-shipped CLI) we MUST
  # add that to PATH or shutil.which("claude") returns None.
  CLAUDE_BIN_PATH="$(command -v claude 2>/dev/null || true)"
  if [[ -n "$CLAUDE_BIN_PATH" ]]; then
    CLAUDE_DIR="$(cd "$(dirname "$CLAUDE_BIN_PATH")" && pwd)"
    LAUNCHD_PATH="$CLAUDE_DIR:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
    echo "  claude CLI: $CLAUDE_BIN_PATH (added to launchd PATH)"
  else
    LAUNCHD_PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
    echo "  ! claude CLI not on PATH; using default launchd PATH (Mission Control will not dispatch)"
  fi

  for tpl in "$INSTALL_DIR/templates/launchd"/*.plist.template; do
    [[ -f "$tpl" ]] || continue
    out="$PLIST_DIR/$(basename "${tpl%.template}")"
    sed \
      -e "s|{{PYTHON}}|$INSTALL_DIR/.venv/bin/python|g" \
      -e "s|{{INSTALL_DIR}}|$INSTALL_DIR|g" \
      -e "s|{{HEARTBEAT}}|$HEARTBEAT_PATH|g" \
      -e "s|{{LOG_DIR}}|$INSTALL_DIR/logs|g" \
      -e "s|{{DEFAULT_MODEL}}|$DEFAULT_MODEL|g" \
      -e "s|{{HOME}}|$HOME|g" \
      -e "s|{{PATH}}|$LAUNCHD_PATH|g" \
      "$tpl" > "$out"
    echo "  rendered $out"
  done

  # Mission Control dispatcher
  launchctl unload "$PLIST_DIR/com.commandcentre.mission-control.plist" 2>/dev/null || true
  launchctl load -w "$PLIST_DIR/com.commandcentre.mission-control.plist"
  echo "✓ launchd: mission-control loaded"

  # Dashboard server — kill any stale detached instance from earlier
  # installs before launchd takes over supervision.
  pkill -f "scripts.server" 2>/dev/null || true
  sleep 0.4
  launchctl unload "$PLIST_DIR/com.commandcentre.server.plist" 2>/dev/null || true
  launchctl load -w "$PLIST_DIR/com.commandcentre.server.plist"
  echo "✓ launchd: server loaded (auto-starts at login, restarts on crash)"
fi

# ---- OTEL wizard ----
if [[ "$SKIP_OTEL" -eq 0 ]]; then
  echo
  echo "→ OTEL wizard"
  CC_INSTALL_DIR="$INSTALL_DIR" "$INSTALL_DIR/.venv/bin/python" -m scripts.setup_otel \
    $([[ "$ASSUME_YES" -eq 1 ]] && echo --yes) \
    $([[ "$ASSUME_YES" -eq 1 ]] && echo --with-hook) || true
fi

# ---- Telegram wizard ----
if [[ "$TELEGRAM_MODE" == "ask" && "$ASSUME_YES" -ne 1 ]]; then
  read -r -p "Set up Telegram bridge now? [y/N] " ans
  case "${ans:-n}" in y|Y|yes|YES) TELEGRAM_MODE=yes ;; *) TELEGRAM_MODE=skip ;; esac
fi
if [[ "$TELEGRAM_MODE" == "yes" ]]; then
  CC_INSTALL_DIR="$INSTALL_DIR" "$INSTALL_DIR/.venv/bin/python" -m scripts.setup_telegram || true
fi

# ---- start server ----
# launchd already started the server when we loaded the plist above
# (RunAtLoad=true). If the user passed --no-launchd we fall back to a
# detached nohup so the server is at least running once.
if [[ "$SKIP_START" -eq 0 && "$SKIP_LAUNCHD" -eq 1 ]]; then
  echo
  echo "→ starting server detached (no launchd supervision)"
  pkill -f "scripts.server" 2>/dev/null || true
  ( cd "$INSTALL_DIR" && nohup ./start.sh > "$INSTALL_DIR/logs/server.log" 2>&1 & )
  sleep 1.0
fi

echo
echo "Done."
echo "  Open:   http://127.0.0.1:$PORT"
echo "  Doctor: $INSTALL_DIR/bin/cc doctor"
echo
echo "If OTEL was just enabled, quit and reopen Claude Code to pick it up."
