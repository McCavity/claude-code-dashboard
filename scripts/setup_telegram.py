"""Interactive Telegram setup wizard.

Walks the user through the BotFather flow, tests the credentials, and
appends ``TELEGRAM_BOT_TOKEN`` + ``TELEGRAM_DASH_CHAT_ID`` to the
install-dir ``.env`` (chmod 600).

The wizard refuses to share a bot with the existing
``~/.claude/plugins/marketplaces/.../telegram/`` plugin: parallel
long-poll consumers on one bot drop updates between processes. We
require a separate token.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests


BOT_FATHER_URL = "https://t.me/BotFather"
USER_INFO_BOT_URL = "https://t.me/userinfobot"


def install_dir() -> Path:
    env = os.environ.get("CC_INSTALL_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".command-centre"


def _existing_plugin_token() -> Path | None:
    candidate = Path.home() / ".claude" / "channels" / "telegram" / ".env"
    return candidate if candidate.exists() else None


def _test_bot(token: str, chat_id: str) -> tuple[bool, str]:
    """Send a probe message. Returns (ok, detail)."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = {
        "chat_id": chat_id,
        "text": "✓ Command Centre is wired up.",
    }
    try:
        r = requests.post(url, json=body, timeout=10)
    except requests.RequestException as exc:
        return False, f"network error: {exc}"
    if not r.ok:
        try:
            j = r.json()
            return False, f"telegram API: {j.get('description', r.text)}"
        except Exception:
            return False, f"telegram API: HTTP {r.status_code}"
    try:
        j = r.json()
    except Exception:
        return False, "invalid JSON from Telegram API"
    if not j.get("ok"):
        return False, f"telegram API: {j.get('description')}"
    return True, "probe message delivered"


def _append_env(env_path: Path, token: str, chat_id: str) -> None:
    env_path.parent.mkdir(parents=True, exist_ok=True)
    existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    lines = [line for line in existing.splitlines() if not line.startswith(("TELEGRAM_BOT_TOKEN=", "TELEGRAM_DASH_CHAT_ID="))]
    lines.append(f"TELEGRAM_BOT_TOKEN={token}")
    lines.append(f"TELEGRAM_DASH_CHAT_ID={chat_id}")
    env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    try:
        env_path.chmod(0o600)
    except OSError:
        pass


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="Skip prompts and use TELEGRAM_BOT_TOKEN / TELEGRAM_DASH_CHAT_ID env vars.")
    parser.add_argument("--token", help="Bot token (otherwise prompt)")
    parser.add_argument("--chat-id", help="Chat id (otherwise prompt)")
    args = parser.parse_args(argv)

    print("Telegram bridge setup")
    print("=====================")
    plugin = _existing_plugin_token()
    if plugin is not None:
        print(
            "⚠ The Telegram marketplace plugin is installed at\n"
            f"  {plugin}\n"
            "  Two long-poll consumers on the same bot will drop updates\n"
            "  between processes. Create a SEPARATE bot for the dashboard."
        )
        print()

    print("1) Open BotFather:", BOT_FATHER_URL)
    print("   Send /newbot, follow the prompts, copy the HTTP API token.")
    print()
    print("2) Open @userinfobot:", USER_INFO_BOT_URL)
    print("   Send anything — it replies with your numeric chat id.")
    print()

    token = args.token or os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token and not args.yes:
        token = input("Bot token: ").strip()
    chat_id = args.chat_id or os.environ.get("TELEGRAM_DASH_CHAT_ID")
    if not chat_id and not args.yes:
        chat_id = input("Chat id: ").strip()

    if not token or not chat_id:
        print("× missing token or chat id; aborting.", file=sys.stderr)
        return 1

    print("\n→ sending probe message…")
    ok, detail = _test_bot(token, chat_id)
    if not ok:
        print(f"× {detail}", file=sys.stderr)
        return 2
    print(f"✓ {detail}")

    env_path = install_dir() / ".env"
    _append_env(env_path, token, chat_id)
    print(f"✓ wrote credentials to {env_path} (chmod 600).")
    print()
    print("Now restart the server:  cc restart")
    print("Notifications will start landing on dashboard events.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
