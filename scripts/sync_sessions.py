"""JSONL session sync.

Walks ``~/.claude/projects/<hash>/<session-id>.jsonl`` (or whatever
``CC_CLAUDE_PROJECTS_DIR`` points at), parses each file event-by-event,
and upserts:

  * ``sessions``                   one row per session
  * ``tool_calls``                 paired tool_use/tool_result blocks
  * ``session_token_breakdown``    per-session daily token contribution
  * ``token_usage``                rebuilt from the breakdown after each pass

The walker is incremental: a session is re-parsed only when the file
mtime is newer than ``sessions.synced_at`` *or* the row does not yet
exist *or* the row's ``ended_at`` is NULL (active session).

Public API:

    run_once(conn, projects_dir=None, source='ide') -> SyncStats
    run_loop(stop_event, interval=120) -> async generator (lifespan use)

Both entry points tolerate per-file and per-line failures: a malformed
JSON line increments a counter and is logged to stderr, the rest of the
file continues. Same for sessions — one bad session does not poison the
batch.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from scripts.db import connect

log = logging.getLogger("commandcentre.sync_sessions")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"
_TOOL_DURATION_CAP_MS = 10 * 60 * 1000  # 10 minutes


def projects_dir() -> Path:
    """Resolve the active JSONL root. ``CC_CLAUDE_PROJECTS_DIR`` overrides."""
    env = os.environ.get("CC_CLAUDE_PROJECTS_DIR")
    return Path(env).expanduser() if env else _DEFAULT_PROJECTS_DIR


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@dataclass
class SyncStats:
    files_seen: int = 0
    files_parsed: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    bad_lines: int = 0
    sessions_upserted: int = 0
    tool_calls_written: int = 0
    elapsed_s: float = 0.0


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


@dataclass
class _SessionAccum:
    """Mutable accumulator for one session worth of JSONL events."""

    session_id: str
    source: str
    cwd: str | None = None
    git_branch: str | None = None
    model: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    title: str | None = None
    custom_title: str | None = None
    first_user_text: str | None = None
    stop_reason: str | None = None
    error_count: int = 0
    rate_limit_hit: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_create_tokens: int = 0
    # tool_use_id -> (tool_name, ts_iso, error_str_or_none, duration_ms_or_none)
    tool_calls: dict[str, dict[str, Any]] = field(default_factory=dict)
    # (date_local, model) -> {input, output, cache_read, cache_create}
    daily: dict[tuple[str, str], dict[str, int]] = field(default_factory=dict)


def _parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        # Python 3.11+ accepts 'Z'. Strip just in case for older runtimes.
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _local_date(ts: str) -> str | None:
    dt = _parse_iso(ts)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().date().isoformat()


def _content_blocks(message: Any) -> Iterable[dict[str, Any]]:
    """Yield content-block dicts. ``content`` may be missing, a string,
    or a list of blocks (some of which can themselves be strings)."""
    if not isinstance(message, dict):
        return
    content = message.get("content")
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict):
                yield b
    # string content has no tool_use/tool_result blocks — skip.


def _add_usage(acc: _SessionAccum, usage: dict[str, Any], ts: str) -> None:
    if not isinstance(usage, dict):
        return
    inp = int(usage.get("input_tokens") or 0)
    out = int(usage.get("output_tokens") or 0)
    cr = int(usage.get("cache_read_input_tokens") or 0)
    cc = int(usage.get("cache_creation_input_tokens") or 0)
    acc.input_tokens += inp
    acc.output_tokens += out
    acc.cache_read_tokens += cr
    acc.cache_create_tokens += cc
    date = _local_date(ts) or "1970-01-01"
    model = acc.model or "unknown"
    bucket = acc.daily.setdefault((date, model), {"i": 0, "o": 0, "cr": 0, "cc": 0})
    bucket["i"] += inp
    bucket["o"] += out
    bucket["cr"] += cr
    bucket["cc"] += cc


def _process_event(acc: _SessionAccum, event: dict[str, Any]) -> None:
    typ = event.get("type")
    ts = event.get("timestamp") or ""

    # Universal context fields (constant across most events of a session).
    if not acc.cwd and event.get("cwd"):
        acc.cwd = event["cwd"]
    if not acc.git_branch and event.get("gitBranch"):
        acc.git_branch = event["gitBranch"]

    # Bracket the session lifetime.
    if ts:
        if not acc.started_at or ts < acc.started_at:
            acc.started_at = ts
        if not acc.ended_at or ts > acc.ended_at:
            acc.ended_at = ts

    if typ == "custom-title":
        acc.custom_title = event.get("customTitle")
        return

    if typ == "system":
        if (event.get("level") or "").lower() == "error":
            acc.error_count += 1
        sub = (event.get("subtype") or "").lower()
        if "rate_limit" in sub:
            acc.rate_limit_hit = 1
        return

    if typ == "assistant":
        msg = event.get("message") or {}
        if not acc.model and msg.get("model"):
            acc.model = msg["model"]
        if msg.get("stop_reason"):
            acc.stop_reason = msg["stop_reason"]
        usage = msg.get("usage")
        if usage:
            _add_usage(acc, usage, ts)
        for block in _content_blocks(msg):
            if block.get("type") == "tool_use":
                tu_id = block.get("id")
                if tu_id:
                    rec = acc.tool_calls.setdefault(
                        tu_id, {"tool_name": block.get("name"), "ts": ts}
                    )
                    rec["tool_name"] = block.get("name") or rec.get("tool_name")
                    rec["ts"] = ts or rec.get("ts")
        return

    if typ == "user":
        msg = event.get("message") or {}
        # Capture first text-like content for title fallback.
        if acc.first_user_text is None:
            content = msg.get("content")
            if isinstance(content, str):
                acc.first_user_text = content
            elif isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "text":
                        acc.first_user_text = b.get("text")
                        break
        for block in _content_blocks(msg):
            if block.get("type") == "tool_result":
                tu_id = block.get("tool_use_id")
                if not tu_id:
                    continue
                rec = acc.tool_calls.setdefault(
                    tu_id, {"tool_name": None, "ts": ts}
                )
                if block.get("is_error"):
                    acc.error_count += 1
                    rec["error"] = "is_error=true"
                start = _parse_iso(rec.get("ts") or "")
                end = _parse_iso(ts)
                if start and end:
                    delta = int((end - start).total_seconds() * 1000)
                    if 0 <= delta <= _TOOL_DURATION_CAP_MS:
                        rec["duration_ms"] = delta
        return

    if typ == "attachment":
        att = event.get("attachment") or {}
        if att.get("exitCode") not in (None, 0):
            acc.error_count += 1
        return


# ---------------------------------------------------------------------------
# Title heuristic
# ---------------------------------------------------------------------------


def _derive_title(acc: _SessionAccum) -> str | None:
    if acc.custom_title:
        return acc.custom_title
    if acc.first_user_text:
        cleaned = acc.first_user_text.strip()
        # Strip leading <command-message>foo</command-message> markers.
        if cleaned.startswith("<command-message>"):
            end = cleaned.find("</command-message>")
            if end >= 0:
                cleaned = cleaned[end + len("</command-message>") :].strip()
        cleaned = cleaned.replace("\n", " ").strip()
        if cleaned:
            return cleaned[:120]
    return None


# ---------------------------------------------------------------------------
# Per-file pipeline
# ---------------------------------------------------------------------------


def _parse_file(path: Path, source: str) -> tuple[_SessionAccum, int]:
    """Return (accumulator, bad_line_count). Caller handles persistence."""
    session_id = path.stem
    acc = _SessionAccum(session_id=session_id, source=source)
    bad = 0
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            try:
                _process_event(acc, event)
            except Exception as exc:  # noqa: BLE001
                bad += 1
                log.debug("event-process error in %s: %s", path.name, exc)
    return acc, bad


def _persist(conn: sqlite3.Connection, acc: _SessionAccum) -> int:
    """Write one session's results to the DB. Returns tool_calls written."""
    title = _derive_title(acc)
    duration_ms = None
    s, e = _parse_iso(acc.started_at or ""), _parse_iso(acc.ended_at or "")
    if s and e and e >= s:
        duration_ms = int((e - s).total_seconds() * 1000)
    total = acc.input_tokens + acc.output_tokens + acc.cache_read_tokens + acc.cache_create_tokens
    effective = acc.output_tokens + acc.cache_create_tokens
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "DELETE FROM tool_calls WHERE session_id = ?", (acc.session_id,)
        )
        conn.execute(
            "DELETE FROM session_token_breakdown WHERE session_id = ?",
            (acc.session_id,),
        )

        tool_rows = 0
        for tu_id, rec in acc.tool_calls.items():
            conn.execute(
                """
                INSERT INTO tool_calls
                  (session_id, tool_use_id, tool_name, ts, duration_ms, error)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    acc.session_id,
                    tu_id,
                    rec.get("tool_name") or "<unknown>",
                    rec.get("ts") or "",
                    rec.get("duration_ms"),
                    rec.get("error"),
                ),
            )
            tool_rows += 1

        for (date, model), bucket in acc.daily.items():
            conn.execute(
                """
                INSERT INTO session_token_breakdown
                  (session_id, date, model, source,
                   input_tokens, output_tokens,
                   cache_read_tokens, cache_create_tokens)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    acc.session_id,
                    date,
                    model,
                    acc.source,
                    bucket["i"],
                    bucket["o"],
                    bucket["cr"],
                    bucket["cc"],
                ),
            )

        conn.execute(
            """
            INSERT INTO sessions
              (session_id, source, cwd, git_branch, model,
               started_at, ended_at,
               input_tokens, output_tokens,
               cache_read_tokens, cache_create_tokens,
               total_tokens, effective_tokens,
               cost_usd, duration_ms, error_count, rate_limit_hit,
               stop_reason, title, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
              source              = excluded.source,
              cwd                 = excluded.cwd,
              git_branch          = excluded.git_branch,
              model               = excluded.model,
              started_at          = excluded.started_at,
              ended_at            = excluded.ended_at,
              input_tokens        = excluded.input_tokens,
              output_tokens       = excluded.output_tokens,
              cache_read_tokens   = excluded.cache_read_tokens,
              cache_create_tokens = excluded.cache_create_tokens,
              total_tokens        = excluded.total_tokens,
              effective_tokens    = excluded.effective_tokens,
              cost_usd            = excluded.cost_usd,
              duration_ms         = excluded.duration_ms,
              error_count         = excluded.error_count,
              rate_limit_hit      = excluded.rate_limit_hit,
              stop_reason         = excluded.stop_reason,
              title               = excluded.title,
              synced_at           = excluded.synced_at
            """,
            (
                acc.session_id,
                acc.source,
                acc.cwd,
                acc.git_branch,
                acc.model,
                acc.started_at,
                acc.ended_at,
                acc.input_tokens,
                acc.output_tokens,
                acc.cache_read_tokens,
                acc.cache_create_tokens,
                total,
                effective,
                0.0,  # cost_usd — populated from OTEL where available
                duration_ms,
                acc.error_count,
                acc.rate_limit_hit,
                acc.stop_reason,
                title,
                now_iso,
            ),
        )
        conn.execute("COMMIT")
        return tool_rows
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _rebuild_token_usage(conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM token_usage")
        conn.execute(
            """
            INSERT INTO token_usage
              (date, model, source,
               input_tokens, output_tokens,
               cache_read_tokens, cache_create_tokens)
            SELECT date, model, source,
                   SUM(input_tokens),
                   SUM(output_tokens),
                   SUM(cache_read_tokens),
                   SUM(cache_create_tokens)
              FROM session_token_breakdown
             GROUP BY date, model, source
            """
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def _existing_synced_at(conn: sqlite3.Connection) -> dict[str, tuple[str, str | None]]:
    """Map session_id -> (synced_at, ended_at)."""
    return {
        r["session_id"]: (r["synced_at"] or "", r["ended_at"])
        for r in conn.execute("SELECT session_id, synced_at, ended_at FROM sessions")
    }


def _file_mtime_iso(p: Path) -> str:
    return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )


def run_once(
    conn: sqlite3.Connection | None = None,
    root: Path | None = None,
    source: str = "ide",
    *,
    force: bool = False,
) -> SyncStats:
    """Process every JSONL whose mtime exceeds its last synced_at."""
    started = time.time()
    own_conn = conn is None
    conn = conn or connect()
    stats = SyncStats()
    root = root or projects_dir()
    if not root.exists():
        log.warning("projects dir %s does not exist", root)
        stats.elapsed_s = time.time() - started
        return stats

    known = _existing_synced_at(conn)

    files = sorted(root.glob("*/*.jsonl"))
    stats.files_seen = len(files)

    for path in files:
        sid = path.stem
        try:
            mtime_iso = _file_mtime_iso(path)
        except FileNotFoundError:
            continue
        prior = known.get(sid)
        if not force and prior is not None:
            synced_at, ended_at = prior
            if ended_at is not None and mtime_iso <= synced_at:
                stats.files_skipped += 1
                continue
        try:
            acc, bad = _parse_file(path, source)
            stats.bad_lines += bad
            if acc.started_at is None:
                # No usable events in file — skip without writing a row.
                stats.files_skipped += 1
                continue
            tool_rows = _persist(conn, acc)
            stats.tool_calls_written += tool_rows
            stats.sessions_upserted += 1
            stats.files_parsed += 1
        except Exception as exc:  # noqa: BLE001
            stats.files_failed += 1
            log.exception("failed to sync %s: %s", path, exc)

    if stats.sessions_upserted:
        try:
            _rebuild_token_usage(conn)
        except Exception:  # noqa: BLE001
            log.exception("failed to rebuild token_usage aggregate")

    if own_conn:
        conn.close()

    stats.elapsed_s = round(time.time() - started, 2)
    log.info(
        "sync_sessions: seen=%d parsed=%d skipped=%d failed=%d "
        "tool_calls=%d bad_lines=%d in %.2fs",
        stats.files_seen,
        stats.files_parsed,
        stats.files_skipped,
        stats.files_failed,
        stats.tool_calls_written,
        stats.bad_lines,
        stats.elapsed_s,
    )
    return stats


async def run_loop(stop: asyncio.Event, interval: float = 120.0) -> None:
    """Background task: run_once every ``interval`` seconds. Cancellable
    via ``stop.set()``."""
    while not stop.is_set():
        try:
            await asyncio.to_thread(run_once)
        except Exception:  # noqa: BLE001
            log.exception("sync_sessions tick failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _main(argv: list[str]) -> int:
    logging.basicConfig(level=os.environ.get("CC_LOG_LEVEL", "info").upper())
    force = "--force" in argv
    stats = run_once(force=force)
    print(json.dumps(stats.__dict__, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
