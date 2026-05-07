"""OTLP/HTTP JSON parsing for the OTEL ingest endpoints.

Handles both wire formats Claude Code can emit:

  * ``/v1/logs``    →  ExportLogsServiceRequest    →  ``otel_events`` rows
  * ``/v1/metrics`` →  ExportMetricsServiceRequest →  ``otel_metrics`` rows

The parser is deliberately lenient: it walks the structures while
tolerating missing / malformed fields, accepts both camelCase (the
canonical JSON encoding) and snake_case keys, and reports per-record
failures so a bad log doesn't drop a whole batch.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable

log = logging.getLogger("commandcentre.otel")


# ---------------------------------------------------------------------------
# AnyValue extraction
# ---------------------------------------------------------------------------


def _coerce_value(any_value: Any) -> Any:
    """Pull a Python primitive out of an OTLP AnyValue."""
    if any_value is None:
        return None
    if not isinstance(any_value, dict):
        return any_value
    for key in (
        "stringValue",
        "string_value",
        "boolValue",
        "bool_value",
        "doubleValue",
        "double_value",
    ):
        if key in any_value:
            return any_value[key]
    for key in ("intValue", "int_value"):
        if key in any_value:
            try:
                return int(any_value[key])
            except (TypeError, ValueError):
                return any_value[key]
    for key in ("arrayValue", "array_value"):
        if key in any_value:
            arr = any_value[key].get("values") or any_value[key].get("array_values") or []
            return [_coerce_value(v) for v in arr]
    for key in ("kvlistValue", "kvlist_value"):
        if key in any_value:
            return _attrs_to_dict(any_value[key].get("values") or [])
    if "bytesValue" in any_value or "bytes_value" in any_value:
        return any_value.get("bytesValue") or any_value.get("bytes_value")
    return None


def _attrs_to_dict(attrs: Iterable[Any]) -> dict[str, Any]:
    """Convert an attributes list ``[{key, value}, …]`` to a flat dict."""
    out: dict[str, Any] = {}
    for kv in attrs or []:
        if not isinstance(kv, dict):
            continue
        k = kv.get("key")
        if not k:
            continue
        out[k] = _coerce_value(kv.get("value"))
    return out


def _ts_iso(time_unix_nano: Any) -> str:
    """Convert OTLP timeUnixNano (string of nanoseconds) to ISO-8601 UTC."""
    try:
        nano = int(time_unix_nano)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    seconds, frac = divmod(nano, 1_000_000_000)
    dt = datetime.fromtimestamp(seconds, tz=timezone.utc).replace(
        microsecond=frac // 1000
    )
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


# Map of attribute key (any accepted variant) -> ``otel_events`` column.
# Multiple keys point to the same column; first match wins.
_LOG_FIELDS: list[tuple[tuple[str, ...], str]] = [
    (("event.name",), "event_name"),
    (("session.id", "session_id"), "session_id"),
    (("prompt_id", "prompt.id"), "prompt_id"),
    (("model",), "model"),
    (("tool_name",), "tool_name"),
    (("success", "tool_success"), "tool_success"),
    (("duration_ms", "tool_duration_ms"), "tool_duration_ms"),
    (("error", "tool_error"), "tool_error"),
    (("cost_usd",), "cost_usd"),
    (("api_duration_ms", "duration"), "api_duration_ms"),
    (("input_tokens",), "input_tokens"),
    (("output_tokens",), "output_tokens"),
    (("cache_read_tokens", "cache_read_input_tokens"), "cache_read_tokens"),
    (("cache_creation_tokens", "cache_creation_input_tokens"), "cache_create_tokens"),
    (("speed",), "speed"),
    (("error.message", "error_message"), "error_message"),
    (("status_code", "http.status_code"), "status_code"),
    (("attempt", "attempt_count"), "attempt_count"),
    (("skill_name", "skill.name"), "skill_name"),
    (("skill_source", "skill.source"), "skill_source"),
    (("prompt_length", "prompt.length"), "prompt_length"),
    (("decision",), "decision"),
    (("decision.source", "decision_source"), "decision_source"),
    (("request_id", "request.id"), "request_id"),
    (("tool_result_size_bytes",), "tool_result_size_bytes"),
    (("mcp.server_scope", "mcp_server_scope"), "mcp_server_scope"),
    (("plugin.name", "plugin_name"), "plugin_name"),
    (("plugin.version", "plugin_version"), "plugin_version"),
    (("marketplace.name", "marketplace_name"), "marketplace_name"),
    (("install.trigger", "install_trigger"), "install_trigger"),
]


_LOG_COLUMNS = [
    "event_name",
    "session_id",
    "prompt_id",
    "timestamp",
    "model",
    "tool_name",
    "tool_success",
    "tool_duration_ms",
    "tool_error",
    "cost_usd",
    "api_duration_ms",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_create_tokens",
    "speed",
    "error_message",
    "status_code",
    "attempt_count",
    "skill_name",
    "skill_source",
    "prompt_length",
    "decision",
    "decision_source",
    "request_id",
    "tool_result_size_bytes",
    "mcp_server_scope",
    "plugin_name",
    "plugin_version",
    "marketplace_name",
    "install_trigger",
    "mcp_server_name",
    "mcp_tool_name",
]


def _parse_log_record(record: dict[str, Any], resource_attrs: dict[str, Any]) -> dict[str, Any] | None:
    """Flatten a single LogRecord into a column dict for ``otel_events``."""
    if not isinstance(record, dict):
        return None
    # Merge resource attributes underneath record attributes (record wins).
    record_attrs = _attrs_to_dict(record.get("attributes") or [])
    merged = {**resource_attrs, **record_attrs}

    row: dict[str, Any] = {col: None for col in _LOG_COLUMNS}
    row["timestamp"] = _ts_iso(
        record.get("timeUnixNano") or record.get("time_unix_nano")
    )

    for keys, col in _LOG_FIELDS:
        for k in keys:
            if k in merged:
                row[col] = merged[k]
                break

    # Bool coercion for tool_success.
    if isinstance(row["tool_success"], str):
        row["tool_success"] = 1 if row["tool_success"].lower() == "true" else 0
    elif isinstance(row["tool_success"], bool):
        row["tool_success"] = 1 if row["tool_success"] else 0

    # MCP sub-parsing: tool_parameters carries server / tool when
    # OTEL_LOG_TOOL_DETAILS=1 is set.
    if (row.get("tool_name") or "") in {"mcp_tool", "mcp__tool"}:
        params_raw = merged.get("tool_parameters") or merged.get("tool.parameters")
        if isinstance(params_raw, str):
            try:
                parsed = json.loads(params_raw)
            except json.JSONDecodeError:
                parsed = {}
        elif isinstance(params_raw, dict):
            parsed = params_raw
        else:
            parsed = {}
        row["mcp_server_name"] = parsed.get("mcp_server_name") or parsed.get("server")
        row["mcp_tool_name"] = parsed.get("mcp_tool_name") or parsed.get("tool")

    # Fallback: parse mcp__<server>__<tool> tool names from the JSONL side.
    if not row["mcp_server_name"]:
        tn = row.get("tool_name") or ""
        if tn.startswith("mcp__"):
            parts = tn.split("__", 2)
            if len(parts) >= 3:
                row["mcp_server_name"] = parts[1]
                row["mcp_tool_name"] = parts[2]

    if not row["event_name"]:
        # Fall back to a placeholder so we still capture the row.
        row["event_name"] = "unknown"

    return row


def ingest_logs(conn: sqlite3.Connection, payload: dict[str, Any]) -> tuple[int, int]:
    """Insert all log records in an OTLP ExportLogsServiceRequest payload.

    Returns ``(inserted, dropped)``.
    """
    inserted = 0
    dropped = 0
    placeholders = ", ".join("?" * len(_LOG_COLUMNS))
    columns_sql = ", ".join(_LOG_COLUMNS)

    resource_logs = payload.get("resourceLogs") or payload.get("resource_logs") or []
    for resource_log in resource_logs:
        if not isinstance(resource_log, dict):
            dropped += 1
            continue
        resource = resource_log.get("resource") or {}
        resource_attrs = _attrs_to_dict(resource.get("attributes") or [])
        scope_logs = resource_log.get("scopeLogs") or resource_log.get("scope_logs") or []
        for scope_log in scope_logs:
            if not isinstance(scope_log, dict):
                dropped += 1
                continue
            log_records = (
                scope_log.get("logRecords")
                or scope_log.get("log_records")
                or []
            )
            for record in log_records:
                try:
                    row = _parse_log_record(record, resource_attrs)
                    if row is None:
                        dropped += 1
                        continue
                    conn.execute(
                        f"INSERT INTO otel_events ({columns_sql}) VALUES ({placeholders})",
                        tuple(row[c] for c in _LOG_COLUMNS),
                    )
                    inserted += 1
                except Exception as exc:  # noqa: BLE001
                    dropped += 1
                    log.debug("log record dropped: %s", exc)
    return inserted, dropped


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _data_points(metric_body: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Return (metric_type, data_points)."""
    if "sum" in metric_body and isinstance(metric_body["sum"], dict):
        body = metric_body["sum"]
        return "counter", body.get("dataPoints") or body.get("data_points") or []
    if "gauge" in metric_body and isinstance(metric_body["gauge"], dict):
        body = metric_body["gauge"]
        return "gauge", body.get("dataPoints") or body.get("data_points") or []
    if "histogram" in metric_body and isinstance(metric_body["histogram"], dict):
        body = metric_body["histogram"]
        return "histogram", body.get("dataPoints") or body.get("data_points") or []
    return "unknown", []


def _dp_value(dp: dict[str, Any]) -> float | None:
    for key in ("asInt", "as_int", "asDouble", "as_double"):
        if key in dp:
            try:
                return float(dp[key])
            except (TypeError, ValueError):
                return None
    if "sum" in dp:  # histogram
        try:
            return float(dp["sum"])
        except (TypeError, ValueError):
            return None
    return None


def ingest_metrics(conn: sqlite3.Connection, payload: dict[str, Any]) -> tuple[int, int]:
    """Insert all metric data points. Returns ``(inserted, dropped)``."""
    inserted = 0
    dropped = 0
    resource_metrics = (
        payload.get("resourceMetrics") or payload.get("resource_metrics") or []
    )
    for rm in resource_metrics:
        if not isinstance(rm, dict):
            dropped += 1
            continue
        scope_metrics = rm.get("scopeMetrics") or rm.get("scope_metrics") or []
        for sm in scope_metrics:
            if not isinstance(sm, dict):
                dropped += 1
                continue
            for metric in sm.get("metrics") or []:
                if not isinstance(metric, dict):
                    dropped += 1
                    continue
                name = metric.get("name") or "unknown"
                metric_type, dps = _data_points(metric)
                for dp in dps:
                    try:
                        attrs = _attrs_to_dict(dp.get("attributes") or [])
                        ts = _ts_iso(
                            dp.get("timeUnixNano") or dp.get("time_unix_nano")
                        )
                        value = _dp_value(dp)
                        if value is None:
                            dropped += 1
                            continue
                        conn.execute(
                            """
                            INSERT INTO otel_metrics
                              (metric_name, metric_type, value,
                               session_id, model, timestamp)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                name,
                                metric_type,
                                value,
                                attrs.get("session.id") or attrs.get("session_id"),
                                attrs.get("model"),
                                ts,
                            ),
                        )
                        inserted += 1
                    except Exception as exc:  # noqa: BLE001
                        dropped += 1
                        log.debug("metric dp dropped: %s", exc)
    return inserted, dropped
