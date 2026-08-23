"""Compact health-analysis tools.

These tools deliberately return small, LLM-friendly summaries. Raw Oura data
remains available through get_oura_data for targeted deep dives.
"""
from __future__ import annotations

from statistics import mean
from typing import Any

from oura_service import _date_range, _fetch_collection, mcp

# Only the fields needed for a normal conversational health question.
_SNAPSHOT_FIELDS = {
    "daily_activity": {"steps", "active_calories", "score"},
    "daily_sleep": {"score"},
    "daily_readiness": {"score", "temperature_deviation"},
    "daily_stress": {"stress_high", "recovery_high", "day_summary"},
}


def _pick(record: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key in allowed and isinstance(value, (int, float, str, bool))}


def _record_day(record: dict[str, Any]) -> str | None:
    for key in ("day", "date", "timestamp", "start_datetime"):
        value = record.get(key)
        if isinstance(value, str):
            return value[:10]
    return None


def _fetch_compact(names: list[str], start: str, end: str, max_records: int = 100):
    errors: dict[str, str] = {}
    by_day: dict[str, dict[str, Any]] = {}
    for name in names:
        try:
            payload = _fetch_collection(name, start_date=start, end_date=end, max_records=max_records)
            records = payload.get("data", []) if isinstance(payload, dict) else []
            if isinstance(records, dict): records = [records]
            allowed = _SNAPSHOT_FIELDS.get(name, set())
            for record in records:
                if not isinstance(record, dict): continue
                day = _record_day(record)
                if day: by_day.setdefault(day, {})[name] = _pick(record, allowed)
        except Exception as exc:
            errors[name] = f"{type(exc).__name__}: {exc}"
    return by_day, errors


def _compact_result(period: dict[str, Any], daily: list[dict[str, Any]], errors: dict[str, str]) -> dict[str, Any]:
    short_errors = {k: str(v)[:180] for k, v in errors.items()}
    return {"period": period, "daily": daily, "days_with_data": len(daily), "errors": short_errors}


@mcp.tool()
def get_health_snapshot_compact(days: int = 2) -> dict[str, Any]:
    """Return an aggressively compact Oura snapshot for conversational questions."""
    days = max(1, min(int(days), 7))
    start, end = _date_range(None, None, days=days)
    by_day, errors = _fetch_compact(list(_SNAPSHOT_FIELDS), start, end, max_records=days + 5)
    daily = []
    for day in sorted(by_day, reverse=True)[:days]:
        row = {"date": day}; row.update(by_day[day]); daily.append(row)
    return _compact_result({"start": start, "end": end, "days": days}, daily, errors)

try:
    mcp.remove_tool("get_health_snapshot")
except Exception:
    pass

@mcp.tool(name="get_health_snapshot", description="Return a VERY small Oura health snapshot for broad questions. Defaults to the latest 2 days and only sleep, readiness, activity and stress. Never returns raw time-series arrays or verbose API metadata.")
def get_health_snapshot(days: int = 2, include_detail: bool = False) -> dict[str, Any]:
    return get_health_snapshot_compact(days=days)

try:
    mcp.remove_tool("get_recent_activity_and_recovery")
except Exception:
    pass

@mcp.tool(name="get_recent_activity_and_recovery", description="Return a compact aggregate of recent Oura activity, sleep, readiness and stress. It never returns raw records, minute-by-minute arrays, contributor maps, workouts or tags.")
def get_recent_activity_and_recovery(days: int = 7) -> dict[str, Any]:
    """Return compact daily scores plus simple period averages."""
    days = max(1, min(int(days), 30))
    start, end = _date_range(None, None, days=days)
    by_day, errors = _fetch_compact(list(_SNAPSHOT_FIELDS), start, end, max_records=days + 10)
    daily = []
    for day in sorted(by_day, reverse=True)[:days]:
        row = {"date": day}; row.update(by_day[day]); daily.append(row)
    averages: dict[str, float] = {}
    for collection, field in (("daily_activity", "score"), ("daily_sleep", "score"), ("daily_readiness", "score"), ("daily_stress", "stress_high")):
        values = [row.get(collection, {}).get(field) for row in daily if isinstance(row.get(collection), dict)]
        values = [float(v) for v in values if isinstance(v, (int, float))]
        if values: averages[f"{collection}.{field}"] = round(mean(values), 1)
    result = _compact_result({"start": start, "end": end, "days": days}, daily, errors)
    result["averages"] = averages
    return result
