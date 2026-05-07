"""Shared helpers for the API routers.

Pure functions only — no I/O, no globals beyond simple constants. Each
helper has a single responsibility so it can be unit-tested without a
running server.
"""

from __future__ import annotations

import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator

from scripts.db import connect

# ---------------------------------------------------------------------------
# DB dependency
# ---------------------------------------------------------------------------


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Time / range helpers
# ---------------------------------------------------------------------------


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def tz_name() -> str:
    """Local timezone name. ``TZ`` env wins if set."""
    env = os.environ.get("TZ")
    if env:
        return env
    return datetime.now().astimezone().tzname() or "local"


_RANGE_DAYS = {"today": 0, "7d": 6, "30d": 29}


def range_to_dates(range_param: str | None) -> tuple[str, str]:
    """Return (start_date, end_date) ISO strings (yyyy-mm-dd) covering the
    requested window in *local* time. End is today, start is N days back
    (inclusive)."""
    rp = (range_param or "today").lower()
    days = _RANGE_DAYS.get(rp, 0)
    today = datetime.now().astimezone().date()
    start = today - timedelta(days=days)
    return start.isoformat(), today.isoformat()


def range_to_iso_window(range_param: str | None) -> tuple[str, str]:
    """Like ``range_to_dates`` but returns full ISO timestamps suitable
    for filtering OTEL events on ``timestamp``."""
    rp = (range_param or "today").lower()
    days = _RANGE_DAYS.get(rp, 0)
    now_local = datetime.now().astimezone()
    end = now_local.replace(microsecond=0)
    start_local = (end - timedelta(days=days)).replace(hour=0, minute=0, second=0)
    return (
        start_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    )


# ---------------------------------------------------------------------------
# Cosmetic helpers
# ---------------------------------------------------------------------------


def home_strip(cwd: str | None) -> str:
    """Replace ``/Users/<user>/`` with ``~/`` in a path."""
    if not cwd:
        return ""
    return re.sub(r"^/Users/[^/]+", "~", cwd)


# ---------------------------------------------------------------------------
# Path traversal guard
# ---------------------------------------------------------------------------


_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def is_valid_session_id(sid: str) -> bool:
    return bool(sid) and bool(_UUID_RE.match(sid))


# ---------------------------------------------------------------------------
# Cron — minimal subset
# ---------------------------------------------------------------------------


def parse_cron_field(spec: str, lo: int, hi: int) -> set[int]:
    """Expand a single cron field. Supports ``*``, single ints, comma
    lists, ranges (``1-5``), and step (``*/15``)."""
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        step = 1
        if "/" in part:
            base, step_s = part.split("/", 1)
            step = max(1, int(step_s))
            part = base
        if part == "*":
            rng = range(lo, hi + 1, step)
        elif "-" in part:
            a, b = part.split("-", 1)
            rng = range(int(a), int(b) + 1, step)
        else:
            n = int(part)
            if step != 1:
                rng = range(n, hi + 1, step)
            else:
                rng = range(n, n + 1)
        out.update(rng)
    return out


def parse_cron_simple(expr: str, base: datetime | None = None) -> datetime:
    """Compute the next firing of a 5-field cron in local time.

    Fields: ``minute hour day-of-month month day-of-week`` where
    day-of-week uses Mon=0..Sun=6 (Python ``weekday()`` convention),
    matching the schedule composer.

    Cap at 366 day search; raise ValueError if no match found within."""
    parts = expr.strip().split()
    if len(parts) != 5:
        raise ValueError("cron must have 5 fields")
    minutes = parse_cron_field(parts[0], 0, 59)
    hours = parse_cron_field(parts[1], 0, 23)
    days = parse_cron_field(parts[2], 1, 31)
    months = parse_cron_field(parts[3], 1, 12)
    dows = parse_cron_field(parts[4], 0, 6)

    cur = (base or datetime.now().astimezone()).replace(
        second=0, microsecond=0
    ) + timedelta(minutes=1)
    for _ in range(366 * 24 * 60):
        if (
            cur.month in months
            and cur.day in days
            and cur.weekday() in dows
            and cur.hour in hours
            and cur.minute in minutes
        ):
            return cur
        cur += timedelta(minutes=1)
    raise ValueError("no cron match within search horizon")


# ---------------------------------------------------------------------------
# Sequence helpers
# ---------------------------------------------------------------------------


def percentile(values: list[float], p: float) -> float | None:
    """Linear-interpolated percentile. Returns None for empty input."""
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    k = (len(s) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] + (s[hi] - s[lo]) * frac
