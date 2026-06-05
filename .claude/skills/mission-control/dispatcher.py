"""Task dispatcher.

The dispatcher runs in a worker thread per claimed task. It spawns a
``claude -p`` child, marks the PID, and either:

* **classic** mode — captures stdout via ``communicate(timeout=...)``,
  writes a single ``output_summary`` row when the child exits.
* **stream** mode — keeps stdin open, drains stdout NDJSON via a reader
  thread, parses ``DECISION:`` / ``INBOX:`` markers from assistant text
  blocks, polls the per-session queue file for user follow-ups.

Concurrency is intentionally simple: we never run more than
``MAX_CONCURRENT`` workers per heartbeat tick. The next tick (120 s
later, driven by launchd) picks up new work.
"""

from __future__ import annotations

import _bootstrap  # noqa: F401

import json
import logging
import os
import queue
import re
import shlex
import shutil
import signal
import sqlite3
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from scripts._helpers import now_iso  # noqa: E402
from scripts.db import connect  # noqa: E402

import task_tracker  # noqa: E402  (sibling)
import skill_router  # noqa: E402  (sibling)
from claude_invocation import classic_cmd  # noqa: E402  (sibling)

log = logging.getLogger("commandcentre.dispatcher")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def _max_concurrent() -> int:
    try:
        return max(1, int(os.environ.get("MISSION_CONTROL_MAX_CONCURRENT", "3")))
    except ValueError:
        return 3


def _task_timeout() -> int:
    try:
        return max(60, int(os.environ.get("MISSION_CONTROL_TASK_TIMEOUT_SECONDS", "1800")))
    except ValueError:
        return 1800


def _default_model() -> str:
    return os.environ.get("MISSION_CONTROL_DEFAULT_MODEL", "claude-sonnet-4-6")


def _claude_bin() -> str:
    return os.environ.get("CLAUDE_BIN") or shutil.which("claude") or "claude"


def _queue_root() -> Path:
    env = os.environ.get("CC_QUEUE_DIR")
    if env:
        return Path(env).expanduser()
    home = os.environ.get("CC_DATA_DIR")
    if home:
        return Path(home).expanduser() / ".tmp" / "mission-control-queue"
    return Path.home() / ".command-centre" / "data" / ".tmp" / "mission-control-queue"


def _pid_dir() -> Path:
    return _queue_root() / "pids"


def _answers_dir() -> Path:
    return _queue_root() / "answers"


# ---------------------------------------------------------------------------
# PID markers
# ---------------------------------------------------------------------------


def _mark_child_pid(pid: int) -> None:
    d = _pid_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / str(pid)).touch()


def _unmark_child_pid(pid: int) -> None:
    (_pid_dir() / str(pid)).unlink(missing_ok=True)


def _sweep_stale_pids() -> int:
    d = _pid_dir()
    if not d.exists():
        return 0
    swept = 0
    for entry in d.iterdir():
        try:
            pid = int(entry.name)
        except ValueError:
            entry.unlink(missing_ok=True)
            continue
        try:
            os.kill(pid, 0)
        except OSError:
            entry.unlink(missing_ok=True)
            swept += 1
    return swept


# ---------------------------------------------------------------------------
# Emergency stop check
# ---------------------------------------------------------------------------


def _emergency_stop_set(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT value FROM system_state WHERE key = 'emergency_stop'"
    ).fetchone()
    return bool(row) and (row["value"] == "1")


# ---------------------------------------------------------------------------
# Skill / model / autonomy resolution
# ---------------------------------------------------------------------------


def _skill_meta(conn: sqlite3.Connection, name: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT name, autonomy_level, description
          FROM skills WHERE name = ?
      ORDER BY environment LIMIT 1
        """,
        (name,),
    ).fetchone()
    return dict(row) if row else None


def _resolve_skill_and_model(
    conn: sqlite3.Connection, task: dict[str, Any]
) -> tuple[str | None, str, str]:
    """Returns (skill_name, model, autonomy)."""
    skill_name = task.get("assigned_skill")
    if not skill_name:
        skill_name = skill_router.pick_skill(
            conn, task.get("title") or "", task.get("description")
        )
    autonomy = "auto"
    if skill_name:
        meta = _skill_meta(conn, skill_name)
        if meta:
            autonomy = (meta.get("autonomy_level") or "auto").lower()
    model = task.get("model") or _default_model()
    return skill_name, model, autonomy


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


def _build_prompt(task: dict[str, Any], skill_name: str | None) -> str:
    parts: list[str] = []
    if skill_name:
        parts.append(f"Use the {skill_name} skill if it fits this task.")
    parts.append(task.get("title") or "")
    if task.get("description"):
        parts.append(task["description"])
    if task.get("dry_run"):
        parts.append(
            "DRY RUN: do not execute side effects, do not commit, do not modify "
            "files. Outline what you would do."
        )
    return "\n\n".join(p for p in parts if p)


def _build_env(model: str) -> dict[str, str]:
    env = os.environ.copy()
    env["ATOMICOPS_DISPATCHED"] = "1"  # legacy marker; PID files are real safety gate.
    # Forward telemetry settings so the dispatched session lights up the
    # dashboard the same way an interactive one does.
    env.setdefault("CLAUDE_CODE_ENABLE_TELEMETRY", "1")
    _otel_port = env.get("CC_PORT", "8765")
    env.setdefault(
        "OTEL_EXPORTER_OTLP_ENDPOINT", f"http://localhost:{_otel_port}"
    )
    env.setdefault("OTEL_EXPORTER_OTLP_PROTOCOL", "http/json")
    env.setdefault("OTEL_METRICS_EXPORTER", "otlp")
    env.setdefault("OTEL_LOGS_EXPORTER", "otlp")
    env.setdefault("OTEL_LOG_TOOL_DETAILS", "1")
    env["MISSION_CONTROL_TASK_MODEL"] = model
    return env


# ---------------------------------------------------------------------------
# Marker parsing
# ---------------------------------------------------------------------------


_DECISION_RE = re.compile(r"^DECISION:\s*(.+)$")
_INBOX_RE = re.compile(r"^INBOX:\s*(.+)$")


class _MarkerParser:
    """Line-oriented parser that tracks triple-backtick fence state.

    Markers inside fenced code blocks are ignored. Each marker is yielded
    once."""

    def __init__(self) -> None:
        self._fence_depth = 0
        self._buf = ""

    def feed(self, text: str) -> Iterable[tuple[str, str]]:
        """Yield ``(kind, payload)`` for each completed line that
        matched a marker. ``kind`` is ``decision`` or ``inbox``."""
        self._buf += text
        while "\n" in self._buf:
            line, _, rest = self._buf.partition("\n")
            self._buf = rest
            stripped = line.strip()
            if stripped.startswith("```"):
                self._fence_depth ^= 1
                continue
            if self._fence_depth:
                continue
            m = _DECISION_RE.match(stripped)
            if m:
                yield ("decision", m.group(1).strip())
                continue
            m = _INBOX_RE.match(stripped)
            if m:
                yield ("inbox", m.group(1).strip())


# ---------------------------------------------------------------------------
# Decision sink
# ---------------------------------------------------------------------------


def _record_decision(
    conn: sqlite3.Connection,
    task_id: int,
    session_id: str | None,
    prompt: str,
) -> int | None:
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO ops_decisions
          (task_id, session_id, prompt, status, created_at)
        VALUES (?, ?, ?, 'pending', ?)
        """,
        (task_id, session_id, prompt, now_iso()),
    )
    if cur.rowcount > 0:
        return cur.lastrowid
    existing = conn.execute(
        "SELECT id FROM ops_decisions WHERE session_id = ? AND prompt = ?",
        (session_id, prompt),
    ).fetchone()
    return existing["id"] if existing else None


def _record_inbox(
    conn: sqlite3.Connection,
    task_id: int,
    session_id: str | None,
    body: str,
) -> None:
    conn.execute(
        """
        INSERT INTO ops_inbox
          (task_id, session_id, direction, body, read, created_at)
        VALUES (?, ?, 'agent_to_user', ?, 0, ?)
        """,
        (task_id, session_id, body, now_iso()),
    )


def _wait_for_decision_answer(
    decision_id: int, deadline: float
) -> str | None:
    """Poll the DB + answers queue file until either an answer lands or
    we hit ``deadline`` (monotonic)."""
    answers_file = _answers_dir() / f"{decision_id}.jsonl"
    while time.monotonic() < deadline:
        if answers_file.exists():
            try:
                with answers_file.open("r", encoding="utf-8") as f:
                    lines = [ln for ln in f if ln.strip()]
                if lines:
                    payload = json.loads(lines[-1])
                    answer = payload.get("answer")
                    if answer is not None:
                        # Consume the file so we don't re-inject.
                        answers_file.unlink(missing_ok=True)
                        return str(answer)
            except Exception:  # noqa: BLE001
                pass
        try:
            conn = connect()
            try:
                row = conn.execute(
                    "SELECT answer FROM ops_decisions WHERE id = ? AND status='answered'",
                    (decision_id,),
                ).fetchone()
            finally:
                conn.close()
            if row and row["answer"] is not None:
                return str(row["answer"])
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2.0)
    return None


# ---------------------------------------------------------------------------
# Reader thread
# ---------------------------------------------------------------------------


def _reader(stream, q: queue.Queue) -> None:
    try:
        for raw in iter(stream.readline, ""):
            if not raw:
                break
            q.put(raw)
    finally:
        q.put(None)


# ---------------------------------------------------------------------------
# Per-task execution
# ---------------------------------------------------------------------------


def _execute_classic(
    task: dict[str, Any], prompt: str, model: str
) -> tuple[bool, str, int | None]:
    # Prompt is fed via stdin, never argv, to avoid a ps/cmdline leak.
    cmd = classic_cmd(_claude_bin(), model)
    env = _build_env(model)
    timeout = _task_timeout()
    started = time.monotonic()
    try:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, text=True, start_new_session=True,
        )
    except FileNotFoundError:
        return False, "claude binary not found", None

    _mark_child_pid(proc.pid)
    try:
        stdout, stderr = proc.communicate(input=prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            stdout, stderr = proc.communicate(timeout=5.0)
        except subprocess.TimeoutExpired:
            stdout, stderr = "", "kill timeout"
        elapsed = int((time.monotonic() - started) * 1000)
        return False, f"timeout after {timeout}s\n{stderr or ''}", elapsed
    finally:
        _unmark_child_pid(proc.pid)

    elapsed = int((time.monotonic() - started) * 1000)
    if proc.returncode != 0:
        msg = (stderr or stdout or "non-zero exit").strip()
        return False, msg[:2000], elapsed
    summary = (stdout or "").strip()
    return True, summary[-4000:], elapsed


def _execute_stream(
    conn_factory, task: dict[str, Any], prompt: str, model: str
) -> tuple[bool, str, int | None]:
    # NOTE: this stream path is pre-existing and currently non-functional --
    # `claude --print --output-format=stream-json` refuses to run without
    # `--verbose`, and even with it, holding stdin open (for follow-ups) means
    # claude never exits, so this loop times out. Moving the prompt off argv
    # (the argv-leak fix) is entangled with that redesign, so it is handled
    # separately. The classic path below is fixed. See the follow-up loop.
    cmd = [
        _claude_bin(), "-p", prompt, "--model", model,
        "--output-format", "stream-json",
        "--input-format", "stream-json",
    ]
    env = _build_env(model)
    timeout = _task_timeout()
    started = time.monotonic()
    deadline = started + timeout
    try:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env, text=True, bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError:
        return False, "claude binary not found", None

    _mark_child_pid(proc.pid)
    out_q: queue.Queue = queue.Queue()
    threading.Thread(target=_reader, args=(proc.stdout, out_q), daemon=True).start()

    parser = _MarkerParser()
    summary_parts: list[str] = []
    session_id_for_task: str | None = None
    # Follow-up queue is session-keyed (matches API writers + ARCHITECTURE.md).
    # Computed lazily once Claude reports its session_id via the init event.
    queue_file: Path | None = None
    followup_offset = 0
    decisions_in_flight: set[int] = set()

    try:
        while True:
            now = time.monotonic()
            if now >= deadline:
                proc.kill()
                elapsed = int((now - started) * 1000)
                return False, f"timeout after {timeout}s", elapsed
            # Drain stdout NDJSON.
            try:
                line = out_q.get(timeout=0.5)
            except queue.Empty:
                line = ""
            if line is None:
                break  # reader hit EOF
            if line:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "system" and event.get("subtype") == "init":
                    sid = event.get("session_id")
                    if sid:
                        session_id_for_task = sid
                        if queue_file is None:
                            queue_file = _queue_root() / f"{sid}.jsonl"
                        try:
                            conn = conn_factory()
                            try:
                                task_tracker.update_session(conn, task["id"], sid)
                            finally:
                                conn.close()
                        except Exception:  # noqa: BLE001
                            log.exception("update_session failed")
                if event.get("type") == "assistant":
                    msg = event.get("message") or {}
                    content = msg.get("content") or []
                    if isinstance(content, list):
                        for b in content:
                            if isinstance(b, dict) and b.get("type") == "text":
                                txt = b.get("text") or ""
                                summary_parts.append(txt)
                                for kind, payload in parser.feed(txt):
                                    try:
                                        conn = conn_factory()
                                        try:
                                            if kind == "decision":
                                                did = _record_decision(
                                                    conn, task["id"], session_id_for_task, payload
                                                )
                                                if did and did not in decisions_in_flight:
                                                    decisions_in_flight.add(did)
                                                    answer = _wait_for_decision_answer(
                                                        did, deadline
                                                    )
                                                    if answer is not None and proc.stdin:
                                                        try:
                                                            proc.stdin.write(
                                                                json.dumps({
                                                                    "type": "user",
                                                                    "message": {"role": "user", "content": answer},
                                                                }) + "\n"
                                                            )
                                                            proc.stdin.flush()
                                                        except Exception:  # noqa: BLE001
                                                            pass
                                            elif kind == "inbox":
                                                _record_inbox(
                                                    conn, task["id"], session_id_for_task, payload
                                                )
                                        finally:
                                            conn.close()
                                    except Exception:  # noqa: BLE001
                                        log.exception("marker handling failed")
            # Poll user follow-up queue file (only after session_id is known).
            if queue_file is not None and queue_file.exists():
                try:
                    size = queue_file.stat().st_size
                    if size > followup_offset:
                        with queue_file.open("r", encoding="utf-8") as f:
                            f.seek(followup_offset)
                            for ln in f:
                                ln = ln.strip()
                                if not ln:
                                    continue
                                try:
                                    payload = json.loads(ln)
                                except json.JSONDecodeError:
                                    continue
                                body = payload.get("body") or ""
                                if not body or not proc.stdin:
                                    continue
                                try:
                                    proc.stdin.write(
                                        json.dumps({
                                            "type": "user",
                                            "message": {"role": "user", "content": body},
                                        }) + "\n"
                                    )
                                    proc.stdin.flush()
                                except Exception:  # noqa: BLE001
                                    pass
                            followup_offset = f.tell()
                except FileNotFoundError:
                    pass
            if proc.poll() is not None and out_q.empty():
                break
    finally:
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
        _unmark_child_pid(proc.pid)

    elapsed = int((time.monotonic() - started) * 1000)
    summary = " ".join(summary_parts).strip()
    if proc.returncode and proc.returncode != 0:
        return False, summary[-2000:] or f"exit {proc.returncode}", elapsed
    return True, summary[-4000:], elapsed


# ---------------------------------------------------------------------------
# Single task driver
# ---------------------------------------------------------------------------


def _execute_one_task(task: dict[str, Any]) -> None:
    conn = connect()
    try:
        claimed = task_tracker.claim_pending(conn, task["id"])
    finally:
        conn.close()
    if claimed is None:
        return  # taken by another worker

    conn = connect()
    try:
        skill_name, model, autonomy = _resolve_skill_and_model(conn, claimed)
        if autonomy in {"manual", "review"}:
            task_tracker.promote_to_awaiting_approval(conn, claimed["id"])
            return
        prompt = _build_prompt(claimed, skill_name)
    finally:
        conn.close()

    if (claimed.get("execution_mode") or "classic") == "stream":
        success, summary, elapsed_ms = _execute_stream(connect, claimed, prompt, model)
    else:
        success, summary, elapsed_ms = _execute_classic(claimed, prompt, model)

    conn = connect()
    try:
        if success:
            task_tracker.complete_task(
                conn, claimed["id"], output_summary=summary, duration_ms=elapsed_ms
            )
        else:
            task_tracker.fail_task(
                conn, claimed["id"], error_message=summary, duration_ms=elapsed_ms
            )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def run_once() -> dict[str, Any]:
    """One dispatcher tick. Safe to call concurrently — the atomic claim
    serialises actual execution."""
    started = time.monotonic()
    conn = connect()
    try:
        if _emergency_stop_set(conn):
            return {"emergency_stop": True}
        swept = _sweep_stale_pids()
        max_c = _max_concurrent()
        # Subtract currently running.
        running = conn.execute(
            "SELECT COUNT(*) FROM ops_tasks WHERE status = 'running'"
        ).fetchone()[0]
        budget = max(0, max_c - running)
        pending = task_tracker.list_pending(conn, budget) if budget > 0 else []
    finally:
        conn.close()

    if not pending:
        return {"swept": swept, "running": running, "picked": 0, "elapsed_s": round(time.monotonic() - started, 2)}

    with ThreadPoolExecutor(max_workers=len(pending)) as ex:
        futs = [ex.submit(_execute_one_task, t) for t in pending]
        for f in as_completed(futs):
            try:
                f.result()
            except Exception:  # noqa: BLE001
                log.exception("task worker raised")

    return {
        "swept": swept,
        "picked": len(pending),
        "elapsed_s": round(time.monotonic() - started, 2),
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=os.environ.get("CC_LOG_LEVEL", "info").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    print(json.dumps(run_once(), indent=2))
