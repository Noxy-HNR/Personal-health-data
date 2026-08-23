"""Compact health-analysis tools.

These tools deliberately summarize Oura responses before returning them to an LLM.
The raw get_oura_data tool remains available for targeted deep dives.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from oura_service import _date_range, _fetch_collection, mcp


# Only fields useful for conversational analysis are allowed into the compact view.
_FIELDS = {
    "daily_activity": {
        "steps", "active_calories", "total_calories", "equivalent_walking_distance",
        "high_activity_time", "medium_activity_time", "low_activity_time",
        "inactivity_alerts", "score",
    },
    "daily_sleep": {
        "score", "total_sleep_duration", "time_in_bed", "efficiency",
        "latency", "awake_time", "deep_sleep_duration", "rem_sleep_duration",
        "light_sleep_duration", "average_heart_rate", "lowest_heart_rate",
        "average_hrv", "breath_average",
    },
    "daily_readiness": {
        "score", "temperature_deviation", "temperature_trend_deviation",
        "contributors", "recovery_index", "resting_heart_rate", "hrv_balance",
    },
    "daily_stress": {"stress_high", "recovery_high", "day_summary"},
    "daily_resilience": {"level", "contributors"},
    "daily_spo2": {"average_saturation", "lowest_saturation", "breathing_disturbance_index"},
    "daily_cardiovascular_age": {"vascular_age", "score"},
    "vO2_max": {"vo2_max", "day"},
}


def _pick(record: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in allowed:
        if key not in record or record[key] is None:
            continue
        value = record[key]
        # Contributors are useful as a compact score map, but discard nested junk.
        if key == "contributors" and isinstance(value, dict):
            compact = {}
            for k, v in value.items():
                if isinstance(v, (int, float, str, bool)):
                    compact[k] = v
            if compact:
                result[key] = compact
        elif isinstance(value, (int, float, str, bool)):
            result[key] = value
    return result


def _record_day(record: dict[str, Any]) -> str | None:
    for key in ("day", "date", "timestamp"):
        value = record.get(key)
        if isinstance(value, str):
            return value[:10]
    return None


@mcp.tool()
def get_health_snapshot_compact(days: int = 7) -> dict[str, Any]:
    """Return a small, LLM-friendly Oura health summary. Prefer this for broad health questions.

    It removes IDs, minute-by-minute time series, raw contributor objects, pagination
    metadata and other API details. Use get_oura_data for a targeted deep dive.
    """
    days = max(1, min(int(days), 90))
    start, end = _date_range(None, None, days=days)
    names = list(_FIELDS)
    errors: dict[str, str] = {}
    by_day: dict[str, dict[str, Any]] = {}

    for name in names:
        try:
            payload = _fetch_collection(name, start_date=start, end_date=end, max_records=max(days * 5, 100))
            records = payload.get("data", []) if isinstance(payload, dict) else []
            if isinstance(records, dict):
                records = [records]
            for record in records:
                if not isinstance(record, dict):
                    continue
                day = _record_day(record)
                if not day:
                    continue
                target = by_day.setdefault(day, {})
                target[name] = _pick(record, _FIELDS[name])
        except Exception as exc:
            errors[name] = f"{type(exc).__name__}: {exc}"

    # Keep the response deterministic and bounded.
    recent = []
    for day in sorted(by_day, reverse=True)[:days]:
        row = {"date": day}
        row.update(by_day[day])
        recent.append(row)

    return {
        "period": {"start": start, "end": end, "days": days},
        "daily": recent,
        "days_with_data": len(recent),
        "errors": errors,
        "raw_data_available_via": "get_oura_data",
    }


# Replace the original oversized snapshot tool with the bounded version while
# keeping the established public tool name so existing clients need no changes.
try:
    mcp.remove_tool("get_health_snapshot")
except Exception:
    pass

@mcp.tool(name="get_health_snapshot", description=(
    "Return a compact, LLM-friendly multi-day Oura health snapshot. "
    "Use this first for broad questions. It intentionally excludes raw minute-by-minute "
    "series, IDs and verbose API metadata. Use get_oura_data for targeted detail."
))
def get_health_snapshot(days: int = 7, include_detail: bool = False) -> dict[str, Any]:
    """Compact replacement for the legacy oversized health snapshot."""
    return get_health_snapshot_compact(days=days)
