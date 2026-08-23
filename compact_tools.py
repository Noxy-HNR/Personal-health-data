"""Compact server-side Oura analytics tools."""
from __future__ import annotations
from statistics import mean
from typing import Any
from oura_service import _date_range, _fetch_collection, mcp

_COLLECTIONS = {
    "daily_activity": {"steps", "active_calories", "score"},
    "daily_sleep": {"score"},
    "daily_readiness": {"score", "temperature_deviation"},
    "daily_stress": {"stress_high", "recovery_high", "day_summary"},
}

def _record_day(record: dict[str, Any]) -> str | None:
    for key in ("day", "date", "timestamp", "start_datetime"):
        value = record.get(key)
        if isinstance(value, str): return value[:10]
    return None

def _pick(record: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k in allowed and isinstance(v, (int, float, str, bool))}

def _fetch_compact(start: str, end: str, max_records: int):
    errors: dict[str, str] = {}
    by_day: dict[str, dict[str, Any]] = {}
    for name, allowed in _COLLECTIONS.items():
        try:
            payload = _fetch_collection(name, start_date=start, end_date=end, max_records=max_records)
            records = payload.get("data", []) if isinstance(payload, dict) else []
            if isinstance(records, dict): records = [records]
            for record in records:
                if not isinstance(record, dict): continue
                day = _record_day(record)
                if day: by_day.setdefault(day, {})[name] = _pick(record, allowed)
        except Exception as exc:
            errors[name] = f"{type(exc).__name__}: {exc}"
    return by_day, errors

def _values(daily, collection: str, field: str) -> list[float]:
    out = []
    for row in daily:
        value = row.get(collection, {}).get(field) if isinstance(row.get(collection), dict) else None
        if isinstance(value, (int, float)): out.append(float(value))
    return out

def _aggregate(daily, collection: str, field: str):
    values = _values(daily, collection, field)
    if not values: return None
    return {"mean": round(mean(values), 2), "min": round(min(values), 2), "max": round(max(values), 2), "n": len(values), "change_first_to_last": round(values[-1] - values[0], 2) if len(values) > 1 else 0}

def _build_analysis(days: int, include_recent: int) -> dict[str, Any]:
    days = max(1, min(int(days), 90))
    include_recent = max(0, min(int(include_recent), 5))
    start, end = _date_range(None, None, days=days)
    by_day, errors = _fetch_compact(start, end, max_records=days + 10)
    ordered = sorted(by_day.items())
    daily = [{"date": day, **row} for day, row in ordered]
    specs = {
        "sleep_score": ("daily_sleep", "score"),
        "readiness_score": ("daily_readiness", "score"),
        "activity_score": ("daily_activity", "score"),
        "steps": ("daily_activity", "steps"),
        "active_calories": ("daily_activity", "active_calories"),
        "stress_high": ("daily_stress", "stress_high"),
        "recovery_high": ("daily_stress", "recovery_high"),
    }
    metrics = {}
    for name, (collection, field) in specs.items():
        result = _aggregate(daily, collection, field)
        if result is not None: metrics[name] = result
    recent = []
    for day, row in reversed(ordered[-include_recent:]):
        recent.append({"date": day, **{k: round(v, 2) if isinstance(v, float) else v for k, v in row.items()}})
    return {"period": {"start": start, "end": end, "requested_days": days}, "metrics": metrics, "recent": recent, "days_with_data": len(ordered), "errors": {k: str(v)[:160] for k, v in errors.items()}}

try: mcp.remove_tool("get_health_snapshot_compact")
except Exception: pass

@mcp.tool(name="get_health_snapshot", description="Server-side Oura analytics for normal health questions. Returns averages, ranges, sample counts, first-to-last changes, and up to 5 recent days. Does not return raw Oura records or time-series arrays.")
def get_health_snapshot(days: int = 14, include_detail: bool = False) -> dict[str, Any]:
    return _build_analysis(days, 3 if include_detail else 0)

try: mcp.remove_tool("get_recent_activity_and_recovery")
except Exception: pass

@mcp.tool(name="get_recent_activity_and_recovery", description="Server-side aggregate of recent Oura activity, sleep, readiness and stress. Returns only period averages/ranges and optional recent days; never raw records.")
def get_recent_activity_and_recovery(days: int = 14) -> dict[str, Any]:
    result = _build_analysis(days, 3)
    result["averages"] = {k: v["mean"] for k, v in result["metrics"].items() if k in {"activity_score", "sleep_score", "readiness_score", "stress_high"}}
    return result
