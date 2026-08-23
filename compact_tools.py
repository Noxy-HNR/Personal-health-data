"""Compact health-analysis tools.

These tools deliberately summarize Oura responses before returning them to an LLM.
The raw get_oura_data tool remains available for targeted deep dives.
"""
from __future__ import annotations

from typing import Any
from oura_service import _date_range, _fetch_collection, mcp

_FIELDS = {
    "daily_activity": {"steps", "active_calories", "score"},
    "daily_sleep": {"score"},
    "daily_readiness": {"score", "temperature_deviation"},
    "daily_stress": {"stress_high", "recovery_high", "day_summary"},
}


def _pick(record: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    return {k: record[k] for k in allowed if k in record and isinstance(record[k], (int, float, str, bool))}


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
            payload = _fetch_collection(name, start_date=start, end_date=end, max_records=max(days + 5, 20))
            records = payload.get("data", []) if isinstance(payload, dict) else []
            if isinstance(records, dict):
                records = [records]
            for record in records:
                if not isinstance(record, dict):
                    continue
                day = _record_day(record)
                if day:
                    picked = _pick(record, _FIELDS.get(name, set()))
                    if picked:
                        by_day.setdefault(day, {})[name] = picked
        except Exception as exc:
            # Keep failures tiny so an unavailable Oura endpoint cannot consume context.
            errors[name] = type(exc).__name__
    return by_day, errors


@mcp.tool()
def get_health_snapshot_compact(days: int = 3) -> dict[str, Any]:
    """Return an extremely small LLM-friendly Oura summary. Never returns raw time-series data."""
    days = max(1, min(int(days), 30))
    start, end = _date_range(None, None, days=days)
    by_day, errors = _compact_collections(list(_FIELDS), start, end, days)
    daily = []
    for day in sorted(by_day, reverse=True)[:days]:
        daily.append({"date": day, **by_day[day]})
    return {"period": {"start": start, "end": end, "days": days}, "daily": daily, "days_with_data": len(daily), "errors": errors}

try:
    mcp.remove_tool("get_health_snapshot")
except Exception:
    pass

@mcp.tool(name="get_health_snapshot", description="Return a tiny compact Oura snapshot. Defaults to 3 days and excludes detail, contributors, raw arrays, IDs and verbose metadata.")
def get_health_snapshot(days: int = 3, include_detail: bool = False) -> dict[str, Any]:
    return get_health_snapshot_compact(days=days)

try:
    mcp.remove_tool("get_recent_activity_and_recovery")
except Exception:
    pass

@mcp.tool(name="get_recent_activity_and_recovery", description="Return a tiny compact recent Oura summary. Defaults to 3 days. Never returns minute-by-minute data, workouts, tags or verbose metadata.")
def get_recent_activity_and_recovery(days: int = 3) -> dict[str, Any]:
    days = max(1, min(int(days), 30))
    start, end = _date_range(None, None, days=days)
    by_day, errors = _compact_collections(["daily_activity", "daily_sleep", "daily_readiness", "daily_stress"], start, end, days)
    daily = [{"date": day, **by_day[day]} for day in sorted(by_day, reverse=True)[:days]]
    return {"period": {"start": start, "end": end, "days": days}, "daily": daily, "days_with_data": len(daily), "errors": errors}
