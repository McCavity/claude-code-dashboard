"""Read-only analytics endpoints.

Every query uses local-time day bucketing
(``DATE(timestamp, 'localtime')``) so a session that runs across
midnight UTC still lands in the right human-perceived day.

All endpoints accept ``range=today|7d|30d`` where applicable. The
helper ``range_to_dates`` resolves that into a ``(start_iso, end_iso)``
pair the queries filter on.

No row-level pagination magic: the dashboard polls every 30 s, so
returning a small bounded set per query keeps each tick cheap.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from scripts._helpers import (
    get_db,
    home_strip,
    percentile,
    range_to_dates,
    range_to_iso_window,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# /api/summary
# ---------------------------------------------------------------------------


@router.get("/api/summary")
def summary() -> dict[str, Any]:
    """Today's KPIs: sessions, tokens, tools, errors."""
    with get_db() as conn:
        sess_row = conn.execute(
            """
            SELECT COUNT(*) AS sessions,
                   COALESCE(SUM(error_count), 0) AS errors
              FROM sessions
             WHERE DATE(started_at, 'localtime') = DATE('now', 'localtime')
            """
        ).fetchone()
        tokens_row = conn.execute(
            """
            SELECT
              COALESCE(SUM(input_tokens), 0) AS input_tokens,
              COALESCE(SUM(output_tokens), 0) AS output_tokens,
              COALESCE(SUM(cache_read_tokens), 0) AS cache_read_tokens,
              COALESCE(SUM(cache_create_tokens), 0) AS cache_create_tokens
              FROM token_usage
             WHERE date = DATE('now', 'localtime')
            """
        ).fetchone()
        tools = conn.execute(
            """
            SELECT COUNT(*) FROM tool_calls
             WHERE DATE(ts, 'localtime') = DATE('now', 'localtime')
            """
        ).fetchone()[0]
    total_tokens = (
        tokens_row["input_tokens"]
        + tokens_row["output_tokens"]
        + tokens_row["cache_read_tokens"]
        + tokens_row["cache_create_tokens"]
    )
    return {
        "sessions": sess_row["sessions"],
        "tokens": total_tokens,
        "input_tokens": tokens_row["input_tokens"],
        "output_tokens": tokens_row["output_tokens"],
        "cache_read_tokens": tokens_row["cache_read_tokens"],
        "cache_create_tokens": tokens_row["cache_create_tokens"],
        "tool_calls": tools,
        "errors": sess_row["errors"],
    }


# ---------------------------------------------------------------------------
# /api/sessions
# ---------------------------------------------------------------------------


@router.get("/api/sessions")
def list_sessions(
    range: str = Query("30d"),
    source: str | None = None,
    model: str | None = None,
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    q: str | None = None,
) -> dict[str, Any]:
    start, _ = range_to_dates(range)
    clauses = ["DATE(started_at, 'localtime') >= ?"]
    params: list[Any] = [start]
    if source:
        clauses.append("source = ?")
        params.append(source)
    if model:
        clauses.append("model = ?")
        params.append(model)
    if q:
        clauses.append("(title LIKE ? OR cwd LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like])
    where = " AND ".join(clauses)
    with get_db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM sessions WHERE {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT session_id, source, cwd, git_branch, model, title,
                   started_at, ended_at, total_tokens, effective_tokens,
                   cost_usd, duration_ms, error_count, rate_limit_hit,
                   stop_reason
              FROM sessions
             WHERE {where}
          ORDER BY COALESCE(ended_at, started_at) DESC
             LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        ).fetchall()
    items = [
        {
            **dict(r),
            "cwd_short": home_strip(r["cwd"]),
        }
        for r in rows
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


# ---------------------------------------------------------------------------
# /api/sessions/{id}/details
# ---------------------------------------------------------------------------


@router.get("/api/sessions/{session_id}/details")
def session_details(session_id: str) -> dict[str, Any]:
    with get_db() as conn:
        sess = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if sess is None:
            raise HTTPException(status_code=404, detail="session not found")
        tools = conn.execute(
            """
            SELECT tool_use_id, tool_name, ts, duration_ms, error
              FROM tool_calls
             WHERE session_id = ?
          ORDER BY ts ASC
            """,
            (session_id,),
        ).fetchall()
        breakdown = conn.execute(
            """
            SELECT date, model, source,
                   input_tokens, output_tokens,
                   cache_read_tokens, cache_create_tokens
              FROM session_token_breakdown
             WHERE session_id = ?
          ORDER BY date
            """,
            (session_id,),
        ).fetchall()
    return {
        "session": dict(sess),
        "tool_calls": [dict(r) for r in tools],
        "token_breakdown": [dict(r) for r in breakdown],
    }


# ---------------------------------------------------------------------------
# /api/sessions/outcomes
# ---------------------------------------------------------------------------


@router.get("/api/sessions/outcomes")
def session_outcomes(range: str = "7d") -> dict[str, Any]:
    """Mutually exclusive buckets per day in priority order:

      errored > rate_limited > truncated > unfinished > ok
    """
    start, _ = range_to_dates(range)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT DATE(started_at, 'localtime') AS date,
                   error_count, rate_limit_hit, ended_at, stop_reason
              FROM sessions
             WHERE DATE(started_at, 'localtime') >= ?
            """,
            (start,),
        ).fetchall()
    daily: dict[str, dict[str, int]] = {}
    truncated_reasons = {"max_tokens", "max_output_tokens", "stop_sequence"}
    for r in rows:
        d = r["date"] or "1970-01-01"
        bucket = daily.setdefault(
            d,
            {"errored": 0, "rate_limited": 0, "truncated": 0, "unfinished": 0, "ok": 0},
        )
        if (r["error_count"] or 0) > 0 or (r["stop_reason"] or "") == "error":
            bucket["errored"] += 1
        elif (r["rate_limit_hit"] or 0) == 1:
            bucket["rate_limited"] += 1
        elif (r["stop_reason"] or "") in truncated_reasons:
            bucket["truncated"] += 1
        elif r["ended_at"] is None:
            bucket["unfinished"] += 1
        else:
            bucket["ok"] += 1
    daily_list = [{"date": d, **counts} for d, counts in sorted(daily.items())]
    totals = {"errored": 0, "rate_limited": 0, "truncated": 0, "unfinished": 0, "ok": 0}
    for d in daily_list:
        for k in totals:
            totals[k] += d[k]
    return {"range": range, "daily": daily_list, "totals": totals}


# ---------------------------------------------------------------------------
# /api/sessions/by-project
# ---------------------------------------------------------------------------


@router.get("/api/sessions/by-project")
def sessions_by_project(range: str = "30d") -> dict[str, Any]:
    start, _ = range_to_dates(range)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT cwd,
                   COUNT(*)               AS sessions,
                   COALESCE(SUM(effective_tokens), 0) AS effective_tokens,
                   COALESCE(SUM(total_tokens), 0)     AS total_tokens
              FROM sessions
             WHERE DATE(started_at, 'localtime') >= ?
          GROUP BY cwd
          ORDER BY effective_tokens DESC
             LIMIT 50
            """,
            (start,),
        ).fetchall()
        tools = conn.execute(
            """
            SELECT s.cwd, COUNT(tc.tool_use_id) AS tool_calls
              FROM sessions s
              LEFT JOIN tool_calls tc ON tc.session_id = s.session_id
             WHERE DATE(s.started_at, 'localtime') >= ?
          GROUP BY s.cwd
            """,
            (start,),
        ).fetchall()
    tool_count: dict[str | None, int] = {r["cwd"]: r["tool_calls"] for r in tools}
    total_eff = sum(r["effective_tokens"] for r in rows) or 1
    items = [
        {
            "cwd": r["cwd"] or "(unknown)",
            "cwd_short": home_strip(r["cwd"]) or "(unknown)",
            "sessions": r["sessions"],
            "effective_tokens": r["effective_tokens"],
            "total_tokens": r["total_tokens"],
            "tool_calls": tool_count.get(r["cwd"], 0),
            "share_pct": round(100.0 * r["effective_tokens"] / total_eff, 1),
        }
        for r in rows
    ]
    return {"items": items}


# ---------------------------------------------------------------------------
# /api/usage/tokens
# ---------------------------------------------------------------------------


@router.get("/api/usage/tokens")
def usage_tokens(range: str = "7d") -> dict[str, Any]:
    start, end = range_to_dates(range)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT date, model, source,
                   input_tokens, output_tokens,
                   cache_read_tokens, cache_create_tokens
              FROM token_usage
             WHERE date >= ?
          ORDER BY date
            """,
            (start,),
        ).fetchall()
    daily: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, int]] = {}
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_create": 0}
    for r in rows:
        d = r["date"]
        bucket = daily.setdefault(
            d,
            {"date": d, "input": 0, "output": 0, "cache_read": 0, "cache_create": 0, "total": 0},
        )
        bucket["input"] += r["input_tokens"]
        bucket["output"] += r["output_tokens"]
        bucket["cache_read"] += r["cache_read_tokens"]
        bucket["cache_create"] += r["cache_create_tokens"]
        bucket["total"] = (
            bucket["input"] + bucket["output"] + bucket["cache_read"] + bucket["cache_create"]
        )
        m = by_model.setdefault(
            r["model"],
            {"input": 0, "output": 0, "cache_read": 0, "cache_create": 0},
        )
        m["input"] += r["input_tokens"]
        m["output"] += r["output_tokens"]
        m["cache_read"] += r["cache_read_tokens"]
        m["cache_create"] += r["cache_create_tokens"]
        totals["input"] += r["input_tokens"]
        totals["output"] += r["output_tokens"]
        totals["cache_read"] += r["cache_read_tokens"]
        totals["cache_create"] += r["cache_create_tokens"]
    daily_list = [daily[k] for k in sorted(daily.keys())]
    return {
        "range": range,
        "start": start,
        "end": end,
        "daily": daily_list,
        "by_model": [{"model": k, **v} for k, v in by_model.items()],
        "totals": totals,
    }


# ---------------------------------------------------------------------------
# /api/usage/cache
# ---------------------------------------------------------------------------


@router.get("/api/usage/cache")
def usage_cache(range: str = "7d") -> dict[str, Any]:
    start, _ = range_to_dates(range)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT date,
                   SUM(input_tokens)        AS input_tokens,
                   SUM(output_tokens)       AS output_tokens,
                   SUM(cache_read_tokens)   AS cache_read_tokens,
                   SUM(cache_create_tokens) AS cache_create_tokens
              FROM token_usage
             WHERE date >= ?
          GROUP BY date
          ORDER BY date
            """,
            (start,),
        ).fetchall()
    daily = []
    overall_billable = 0
    overall_read = 0
    for r in rows:
        billable = (r["input_tokens"] or 0) + (r["cache_read_tokens"] or 0) + (
            r["cache_create_tokens"] or 0
        )
        read = r["cache_read_tokens"] or 0
        rate = (read / billable) if billable else 0.0
        daily.append(
            {
                "date": r["date"],
                "input_tokens": r["input_tokens"] or 0,
                "cache_read_tokens": r["cache_read_tokens"] or 0,
                "cache_create_tokens": r["cache_create_tokens"] or 0,
                "billable": billable,
                "hit_rate": round(rate, 4),
            }
        )
        overall_billable += billable
        overall_read += read
    overall_rate = (overall_read / overall_billable) if overall_billable else 0.0
    return {
        "range": range,
        "daily": daily,
        "overall_hit_rate": round(overall_rate, 4),
        "billable_tokens": overall_billable,
        "low_sample": overall_billable < 10_000,
        "target": 0.70,
    }


# ---------------------------------------------------------------------------
# /api/tools/latency
# ---------------------------------------------------------------------------


@router.get("/api/tools/latency")
def tools_latency(range: str = "7d") -> dict[str, Any]:
    start, _ = range_to_dates(range)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT tool_name, duration_ms, error
              FROM tool_calls
             WHERE DATE(ts, 'localtime') >= ?
            """,
            (start,),
        ).fetchall()
    by_tool: dict[str, dict[str, Any]] = {}
    for r in rows:
        t = r["tool_name"] or "<unknown>"
        bucket = by_tool.setdefault(t, {"durations": [], "errors": 0, "calls": 0})
        bucket["calls"] += 1
        if r["error"]:
            bucket["errors"] += 1
        if r["duration_ms"] is not None:
            bucket["durations"].append(float(r["duration_ms"]))
    items = []
    for t, b in by_tool.items():
        d = b["durations"]
        items.append(
            {
                "tool_name": t,
                "calls": b["calls"],
                "errors": b["errors"],
                "error_rate": round(b["errors"] / b["calls"], 4) if b["calls"] else 0,
                "p50_ms": int(percentile(d, 50)) if d else None,
                "p95_ms": int(percentile(d, 95)) if d else None,
                "max_ms": int(max(d)) if d else None,
            }
        )
    items.sort(key=lambda x: (x["p95_ms"] or 0), reverse=True)
    return {"range": range, "items": items}


# ---------------------------------------------------------------------------
# /api/tools/agent-fanout
# ---------------------------------------------------------------------------


@router.get("/api/tools/agent-fanout")
def tools_agent_fanout(range: str = "7d") -> dict[str, Any]:
    start, _ = range_to_dates(range)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT s.session_id, s.title, s.model, s.cwd,
                   COUNT(tc.tool_use_id) AS agent_calls
              FROM sessions s
              JOIN tool_calls tc ON tc.session_id = s.session_id
             WHERE tc.tool_name = 'Agent'
               AND DATE(s.started_at, 'localtime') >= ?
          GROUP BY s.session_id
          ORDER BY agent_calls DESC
             LIMIT 30
            """,
            (start,),
        ).fetchall()
    return {
        "range": range,
        "items": [
            {
                "session_id": r["session_id"],
                "title": r["title"],
                "model": r["model"],
                "cwd_short": home_strip(r["cwd"]),
                "agent_calls": r["agent_calls"],
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# /api/tools/edit-decisions
# ---------------------------------------------------------------------------


@router.get("/api/tools/edit-decisions")
def tools_edit_decisions(range: str = "7d") -> dict[str, Any]:
    start_iso, _ = range_to_iso_window(range)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT tool_name, decision, COUNT(*) AS n
              FROM otel_events
             WHERE event_name = 'tool_decision'
               AND tool_name IN ('Edit','MultiEdit','Write','NotebookEdit')
               AND timestamp >= ?
          GROUP BY tool_name, decision
            """,
            (start_iso,),
        ).fetchall()
    by_tool: dict[str, dict[str, int]] = {}
    for r in rows:
        b = by_tool.setdefault(
            r["tool_name"], {"accept": 0, "reject": 0, "other": 0, "total": 0}
        )
        d = (r["decision"] or "").lower()
        if d in ("accept", "approve", "approved"):
            b["accept"] += r["n"]
        elif d in ("reject", "deny", "rejected"):
            b["reject"] += r["n"]
        else:
            b["other"] += r["n"]
        b["total"] += r["n"]
    items = []
    total_n = 0
    for t, b in by_tool.items():
        items.append(
            {
                "tool_name": t,
                "accept": b["accept"],
                "reject": b["reject"],
                "other": b["other"],
                "total": b["total"],
                "accept_rate": round(b["accept"] / b["total"], 4) if b["total"] else 0,
            }
        )
        total_n += b["total"]
    return {
        "range": range,
        "items": items,
        "low_sample": total_n < 10,
        "n": total_n,
    }


# ---------------------------------------------------------------------------
# /api/hooks/activity
# ---------------------------------------------------------------------------


@router.get("/api/hooks/activity")
def hooks_activity(range: str = "7d") -> dict[str, Any]:
    start_iso, _ = range_to_iso_window(range)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT event_name, session_id, timestamp,
                   tool_name, tool_duration_ms
              FROM otel_events
             WHERE event_name IN ('hook_execution_start','hook_execution_complete')
               AND timestamp >= ?
          ORDER BY timestamp
            """,
            (start_iso,),
        ).fetchall()
    fires = 0
    durations: list[int] = []
    in_flight: dict[str, list[str]] = {}
    daily: dict[str, int] = {}
    for r in rows:
        ts = r["timestamp"]
        d = ts[:10] if ts else "?"
        daily[d] = daily.get(d, 0) + (1 if r["event_name"] == "hook_execution_start" else 0)
        if r["event_name"] == "hook_execution_start":
            fires += 1
            in_flight.setdefault(r["session_id"] or "_", []).append(ts)
        else:
            queue = in_flight.get(r["session_id"] or "_") or []
            if queue:
                start_ts = queue.pop(0)
                try:
                    from datetime import datetime as _dt

                    s = _dt.fromisoformat(start_ts.replace("Z", "+00:00"))
                    e = _dt.fromisoformat(ts.replace("Z", "+00:00"))
                    delta = int((e - s).total_seconds() * 1000)
                    if 0 <= delta <= 60_000:
                        durations.append(delta)
                except Exception:
                    pass
    durations.sort()
    return {
        "range": range,
        "total_fires": fires,
        "paired_count": len(durations),
        "p50_ms": int(percentile([float(x) for x in durations], 50)) if durations else None,
        "p95_ms": int(percentile([float(x) for x in durations], 95)) if durations else None,
        "max_ms": durations[-1] if durations else None,
        "daily": [{"date": k, "fires": v} for k, v in sorted(daily.items())],
    }


# ---------------------------------------------------------------------------
# /api/activity/productivity
# ---------------------------------------------------------------------------


@router.get("/api/activity/productivity")
def activity_productivity(range: str = "30d") -> dict[str, Any]:
    start_iso, _ = range_to_iso_window(range)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT metric_name,
                   DATE(timestamp, 'localtime') AS date,
                   SUM(value) AS total
              FROM otel_metrics
             WHERE metric_name IN (
                     'claude_code.commit.count',
                     'claude_code.pull_request.count',
                     'claude_code.lines_of_code.count'
                   )
               AND timestamp >= ?
          GROUP BY metric_name, date
          ORDER BY date
            """,
            (start_iso,),
        ).fetchall()
    daily: dict[str, dict[str, float]] = {}
    totals: dict[str, float] = {}
    for r in rows:
        d = r["date"]
        bucket = daily.setdefault(d, {"commits": 0, "prs": 0, "lines": 0})
        if r["metric_name"] == "claude_code.commit.count":
            bucket["commits"] = r["total"] or 0
            totals["commits"] = totals.get("commits", 0) + (r["total"] or 0)
        elif r["metric_name"] == "claude_code.pull_request.count":
            bucket["prs"] = r["total"] or 0
            totals["prs"] = totals.get("prs", 0) + (r["total"] or 0)
        elif r["metric_name"] == "claude_code.lines_of_code.count":
            bucket["lines"] = r["total"] or 0
            totals["lines"] = totals.get("lines", 0) + (r["total"] or 0)
    daily_list = [{"date": k, **v} for k, v in sorted(daily.items())]
    return {"range": range, "daily": daily_list, "totals": totals}


# ---------------------------------------------------------------------------
# /api/system/pressure
# ---------------------------------------------------------------------------


@router.get("/api/system/pressure")
def system_pressure(range: str = "7d") -> dict[str, Any]:
    import os as _os

    try:
        threshold = int(_os.environ.get("CLAUDE_CODE_MAX_RETRIES", "10"))
    except ValueError:
        threshold = 10
    start_iso, _e = range_to_iso_window(range)
    with get_db() as conn:
        retry = conn.execute(
            """
            SELECT COUNT(*) FROM otel_events
             WHERE event_name = 'api_request'
               AND attempt_count >= ?
               AND timestamp >= ?
            """,
            (threshold, start_iso),
        ).fetchone()[0]
        compactions = conn.execute(
            """
            SELECT COUNT(*) FROM otel_events
             WHERE event_name = 'compaction' AND timestamp >= ?
            """,
            (start_iso,),
        ).fetchone()[0]
        recent_errors = conn.execute(
            """
            SELECT timestamp, model, error_message, status_code, attempt_count
              FROM otel_events
             WHERE event_name = 'api_error'
               AND timestamp >= ?
          ORDER BY timestamp DESC
             LIMIT 10
            """,
            (start_iso,),
        ).fetchall()
    return {
        "range": range,
        "max_retries_threshold": threshold,
        "retry_exhausted": retry,
        "compactions": compactions,
        "recent_api_errors": [dict(r) for r in recent_errors],
    }


# ---------------------------------------------------------------------------
# /api/mcp
# ---------------------------------------------------------------------------


@router.get("/api/mcp")
def mcp_overview(range: str = "30d") -> dict[str, Any]:
    """List MCP servers with calls + avg + p95 latency. Sources, in
    priority order: OTEL events with mcp_server_name (precise),
    tool_calls with the legacy ``mcp__<server>__<tool>`` naming."""
    start_iso, _ = range_to_iso_window(range)
    with get_db() as conn:
        otel_rows = conn.execute(
            """
            SELECT mcp_server_name AS server, tool_duration_ms AS duration_ms
              FROM otel_events
             WHERE event_name = 'tool_result'
               AND mcp_server_name IS NOT NULL
               AND timestamp >= ?
            """,
            (start_iso,),
        ).fetchall()
        tool_rows = conn.execute(
            """
            SELECT tool_name, duration_ms FROM tool_calls
             WHERE tool_name LIKE 'mcp__%'
               AND DATE(ts, 'localtime') >= DATE(?, 'localtime')
            """,
            (start_iso,),
        ).fetchall()
        stats_rows = conn.execute(
            "SELECT server, tools, total_tokens, error, measured_at FROM mcp_stats"
        ).fetchall()

    by_server: dict[str, dict[str, Any]] = {}
    for r in otel_rows:
        s = r["server"]
        b = by_server.setdefault(s, {"durations": [], "calls": 0})
        b["calls"] += 1
        if r["duration_ms"] is not None:
            b["durations"].append(float(r["duration_ms"]))
    for r in tool_rows:
        # Fallback: parse mcp__<server>__<tool> naming.
        parts = (r["tool_name"] or "").split("__", 2)
        if len(parts) < 3:
            continue
        s = parts[1]
        b = by_server.setdefault(s, {"durations": [], "calls": 0})
        # Don't double-count: only used when no otel data exists.
        if not [r2 for r2 in otel_rows if r2["server"] == s]:
            b["calls"] += 1
            if r["duration_ms"] is not None:
                b["durations"].append(float(r["duration_ms"]))

    stats_by_server = {r["server"]: dict(r) for r in stats_rows}
    items = []
    for s, b in by_server.items():
        d = b["durations"]
        meta = stats_by_server.get(s, {})
        items.append(
            {
                "server": s,
                "calls": b["calls"],
                "avg_ms": int(sum(d) / len(d)) if d else None,
                "p50_ms": int(percentile(d, 50)) if d else None,
                "p95_ms": int(percentile(d, 95)) if d else None,
                "max_ms": int(max(d)) if d else None,
                "tools": meta.get("tools"),
                "total_tokens": meta.get("total_tokens"),
                "measured_at": meta.get("measured_at"),
            }
        )
    items.sort(key=lambda x: (x["p95_ms"] or 0), reverse=True)
    return {"range": range, "items": items}


# ---------------------------------------------------------------------------
# /api/mcp/{server}/tools
# ---------------------------------------------------------------------------


@router.get("/api/mcp/{server}/tools")
def mcp_server_tools(server: str, range: str = "7d") -> dict[str, Any]:
    start_iso, _ = range_to_iso_window(range)
    with get_db() as conn:
        otel_rows = conn.execute(
            """
            SELECT mcp_tool_name AS tool,
                   tool_duration_ms AS duration_ms,
                   tool_error AS error,
                   tool_success AS success
              FROM otel_events
             WHERE event_name = 'tool_result'
               AND mcp_server_name = ?
               AND timestamp >= ?
            """,
            (server, start_iso),
        ).fetchall()
        tool_rows = conn.execute(
            """
            SELECT tool_name, duration_ms, error
              FROM tool_calls
             WHERE tool_name LIKE ?
               AND DATE(ts, 'localtime') >= DATE(?, 'localtime')
            """,
            (f"mcp__{server}__%", start_iso),
        ).fetchall()
    by_tool: dict[str, dict[str, Any]] = {}
    seen_otel = bool(otel_rows)
    for r in otel_rows:
        t = r["tool"] or "<unknown>"
        b = by_tool.setdefault(t, {"durations": [], "errors": 0, "calls": 0})
        b["calls"] += 1
        if (r["success"] is not None and not r["success"]) or r["error"]:
            b["errors"] += 1
        if r["duration_ms"] is not None:
            b["durations"].append(float(r["duration_ms"]))
    if not seen_otel:
        for r in tool_rows:
            parts = (r["tool_name"] or "").split("__", 2)
            t = parts[2] if len(parts) >= 3 else r["tool_name"] or "<unknown>"
            b = by_tool.setdefault(t, {"durations": [], "errors": 0, "calls": 0})
            b["calls"] += 1
            if r["error"]:
                b["errors"] += 1
            if r["duration_ms"] is not None:
                b["durations"].append(float(r["duration_ms"]))
    items = []
    for t, b in by_tool.items():
        d = b["durations"]
        items.append(
            {
                "tool": t,
                "calls": b["calls"],
                "errors": b["errors"],
                "error_rate": round(b["errors"] / b["calls"], 4) if b["calls"] else 0,
                "p50_ms": int(percentile(d, 50)) if d else None,
                "p95_ms": int(percentile(d, 95)) if d else None,
                "max_ms": int(max(d)) if d else None,
            }
        )
    items.sort(key=lambda x: (x["p95_ms"] or 0), reverse=True)
    return {"server": server, "range": range, "items": items}


# ---------------------------------------------------------------------------
# /api/skills
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# /api/context-health  — read-only scan of ~/.claude/settings.json + CLAUDE.md
# ---------------------------------------------------------------------------


@router.get("/api/context-health")
def context_health() -> dict[str, Any]:
    """Cheap, deterministic scan of the user's Claude config. NOT an
    LLM call — just file stats."""
    import os as _os
    home = Path.home()
    settings = home / ".claude" / "settings.json"
    claude_md = home / ".claude" / "CLAUDE.md"

    def _stat(p: Path) -> dict[str, Any]:
        if not p.exists():
            return {"path": str(p), "exists": False}
        try:
            text = p.read_text(encoding="utf-8")
            lines = text.count("\n") + 1
        except Exception:
            text, lines = "", 0
        return {
            "path": str(p),
            "exists": True,
            "size_bytes": p.stat().st_size,
            "lines": lines,
            "modified_at": datetime.fromtimestamp(
                p.stat().st_mtime, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        }

    settings_meta = _stat(settings)
    claude_md_meta = _stat(claude_md)

    mcp_count = 0
    hook_count = 0
    permission_count = 0
    plugins_enabled: list[str] = []
    if settings_meta.get("exists"):
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        mcp = data.get("mcpServers") or data.get("mcp_servers") or {}
        mcp_count = len(mcp) if isinstance(mcp, dict) else 0
        hooks = data.get("hooks") or {}
        if isinstance(hooks, dict):
            for arr in hooks.values():
                if isinstance(arr, list):
                    for entry in arr:
                        if isinstance(entry, dict):
                            inner = entry.get("hooks") or []
                            hook_count += len(inner) if isinstance(inner, list) else 1
        perms = data.get("permissions") or {}
        if isinstance(perms, dict):
            allow = perms.get("allow") or []
            if isinstance(allow, list):
                permission_count = len(allow)
        ep = data.get("enabledPlugins") or {}
        if isinstance(ep, dict):
            plugins_enabled = list(ep.keys())

    return {
        "settings_json": settings_meta,
        "claude_md": claude_md_meta,
        "mcp_servers": mcp_count,
        "hooks_registered": hook_count,
        "permissions_allowed": permission_count,
        "plugins_enabled": plugins_enabled,
    }


# ---------------------------------------------------------------------------
# /api/skills/economics  — token cost per skill from sessions data
# ---------------------------------------------------------------------------


@router.get("/api/skills/economics")
def skill_economics(range: str = "30d") -> dict[str, Any]:
    """Approximate token cost per skill. Right now we only know which
    skill ran via OTEL events (skill.name attribute). When OTEL is off
    this returns an empty list rather than a fabricated estimate."""
    start_iso, _ = range_to_iso_window(range)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT skill_name,
                   COUNT(*) AS calls,
                   COALESCE(SUM(input_tokens), 0)        AS input_tokens,
                   COALESCE(SUM(output_tokens), 0)       AS output_tokens,
                   COALESCE(SUM(cache_read_tokens), 0)   AS cache_read_tokens,
                   COALESCE(SUM(cache_create_tokens), 0) AS cache_create_tokens,
                   COALESCE(SUM(cost_usd), 0)            AS cost_usd
              FROM otel_events
             WHERE skill_name IS NOT NULL
               AND timestamp >= ?
          GROUP BY skill_name
          ORDER BY (COALESCE(SUM(output_tokens), 0) + COALESCE(SUM(cache_create_tokens), 0)) DESC
            """,
            (start_iso,),
        ).fetchall()
    return {
        "range": range,
        "items": [
            {
                **dict(r),
                "effective_tokens": (r["output_tokens"] or 0) + (r["cache_create_tokens"] or 0),
                "total_tokens": (r["input_tokens"] or 0)
                + (r["output_tokens"] or 0)
                + (r["cache_read_tokens"] or 0)
                + (r["cache_create_tokens"] or 0),
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# /api/failures  — crashed/errored sessions for the UnifiedFailures panel
# ---------------------------------------------------------------------------


@router.get("/api/failures")
def failures(range: str = "7d", limit: int = 30) -> dict[str, Any]:
    start, _ = range_to_dates(range)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT session_id, title, model, cwd, error_count,
                   rate_limit_hit, stop_reason, started_at, ended_at
              FROM sessions
             WHERE DATE(started_at, 'localtime') >= ?
               AND (error_count > 0 OR stop_reason = 'error' OR rate_limit_hit = 1)
          ORDER BY started_at DESC
             LIMIT ?
            """,
            (start, limit),
        ).fetchall()
    return {
        "range": range,
        "items": [
            {**dict(r), "cwd_short": home_strip(r["cwd"])} for r in rows
        ],
    }


@router.get("/api/skills")
def list_skills(
    environment: str | None = None,
    user_invocable: bool | None = None,
) -> dict[str, Any]:
    clauses = []
    params: list[Any] = []
    if environment:
        clauses.append("environment = ?")
        params.append(environment)
    if user_invocable is not None:
        clauses.append("user_invocable = ?")
        params.append(1 if user_invocable else 0)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT name, environment, description, path,
                   autonomy_level, user_invocable, script_count, last_modified
              FROM skills {where}
          ORDER BY name
            """,
            params,
        ).fetchall()
    return {"items": [dict(r) for r in rows]}
