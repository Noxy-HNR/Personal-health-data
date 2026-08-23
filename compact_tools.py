"""Compact health-analysis tools.

These tools deliberately summarize Oura responses before returning them to an LLM.
The raw get_oura_data tool remains available for targeted deep dives.
"""
from __future__ import annotations

from typing import Any

from oura_service import _date_range, _fetch_collection, mcp

_FIELDS = {
    "daily_activity": {"steps", "active_calories", "total_calories", "equivalent_walking_distance", "high_activity_time", "medium_activity_time", "low_activity_time", "inactivity_alerts", "score"},
    "daily_sleep": {"score", "total_sleep_duration", "time_in_bed", "efficiency", "latency", "awake_time", "deep_sleep_duration", "rem_sleep_duration", "light_sleep_duration", "average_heart_rate", "lowest_heart_rate", "average_hrv", "breath_average"},
    "daily_readiness": {"score", "temperature_deviation", "temperature_trend_deviation", "contributors", "recovery_index", "resting_heart_rate", "hrv_balance"},
    "daily_stress": {"stress_high", "recovery_high", "day_summary"},
    "daily_resilience": {"level", "contributors"},
    "daily_spo2": {"average_saturation", "lowest_saturation", "breathing_disturbance_index"},
    "daily_cardiovascular_age": {"vascular_age", "score"},
    "vO2_max": {"vo2_max", "day"},
}

_RECENT_FIELDS = {
    **_FIELDS,
    "workout": {"activity", "calories", "day", "distance", "duration", "intensity", "label", "source", "start_datetime", "end_datetime"},
    "enhanced_tag": {"tag_type_code", "text", "day", "timestamp"},
    "rest_mode_period": {"day", "start_datetime", "end_datetime", "end_reason", "source"},
}


def _pick(record: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in allowed:
        value = record.get(key)
        if value is None:
            continue
        if key == "contributors" and isinstance(value, dict):
            compact = {k: v for k, v in value.items() if isinstance(v, (int, float, str, bool))}
            if compact:
                result[key] = compact
        elif isinstance(value, (int, float, str, bool)):
            result[key] = value
        elif isinstance(value, list) and len(value) <= 10 and all(isinstance(v, (int, float, str, bool)) for v in value):
            result[key] = value
    return result


def _record_day(record: dict[str, Any]) -> str | None:
    for key in ("day", "date", "timestamp", "start_datetime"):
        value = record.get(key)
        if isinstance(value, str):
            return value[:10]
    return None


def _compact_collections(names: list[str], start: str, end: str, days: int):
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
                by_day.setdefault(day, {})[name] = _pick(record, _RECENT_FIELDS.get(name, set()))
        except Exception as exc:
            errors[name] = f"{type(exc).__name__}: {exc}"
    return by_day, errors


@mcp.tool()
def get_health_snapshot_compact(days: int = 7) -> dict[str, Any]:
    """Return a small LLM-friendly Oura health summary without raw time-series arrays."""
    days = max(1, min(int(days), 90))
    start, end = _date_range(None, None, days=days)
    by_day, errors = _compact_collections(list(_FIELDS), start, end, days)
    daily = []
    for day in sorted(by_day, reverse=True)[:days]:
        row = {"date": day}
        row.update(by_day[day])
        daily.append(row)
    return {"period": {"start": start, "end": end, "days": days}, "daily": daily, "days_with_data": len(daily), "errors": errors, "raw_data_available_via": "get_oura_data"}

try:
    mcp.remove_tool("get_health_snapshot")
except Exception:
    pass

@mcp.tool(name="get_health_snapshot", description="Return a compact multi-day Oura health snapshot. Excludes raw minute-by-minute series, IDs and verbose API metadata. Use get_oura_data for targeted detail.")
def get_health_snapshot(days: int = 7, include_detail: bool = False) -> dict[str, Any]:
    return get_health_snapshot_compact(days=days)

try:
    mcp.remove_tool("get_recent_activity_and_recovery")
except Exception:
    pass

@mcp.tool(name="get_recent_activity_and_recovery", description="Return compact recent Oura activity, sleep, readiness and stress data. Never returns minute-by-minute MET/class arrays. Use get_oura_data for targeted raw detail.")
def get_recent_activity_and_recovery(days: int = 14) -> dict[str, Any]:
    """Return bounded recent Oura data; large raw Oura arrays are stripped."""
    days = max(1, min(int(days), 90))
    start, end = _date_range(None, None, days=days)
    names = ["daily_activity", "daily_sleep", "daily_readiness", "daily_stress", "daily_resilience", "workout", "enhanced_tag", "rest_mode_period"]
    by_day, errors = _compact_collections(names, start, end, days)
    daily = []
    for day in sorted(by_day, reverse=True)[:days]:
        row = {"date": day}
        row.update(by_day[day])
        daily.append(row)
    return {"period": {"start": start, "end": end, "days": days}, "daily": daily, "days_with_data": len(daily), "errors": errors, "raw_data_available_via": "get_oura_data"}
