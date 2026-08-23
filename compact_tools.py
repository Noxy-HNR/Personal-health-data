"""Small server-side Oura analytics endpoints.

The model should receive aggregates, not raw Oura collections. All collection
fetching, date alignment, filtering, and arithmetic happen in this module.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import mean
from typing import Any

from oura_service import _date_range, _fetch_collection, mcp

_COLLECTION_FIELDS = {
    "daily_activity": {"steps", "active_calories", "score"},
    "daily_sleep": {"score"},
    "daily_readiness": {"score", "temperature_deviation"},
    "daily_stress": {"stress_high", "recovery_high", "day_summary"},
}

_METRICS = {
    "sleep_score": ("daily_sleep", "score"),
    "readiness_score": ("daily_readiness", "score"),
    "activity_score": ("daily_activity", "score"),
    "steps": ("daily_activity", "steps"),
    "active_calories": ("daily_activity", "active_calories"),
    "stress_high": ("daily_stress", "stress_high"),
    "recovery_high": ("daily_stress", "recovery_high"),
    "temperature_deviation": ("daily_readiness", "temperature_deviation"),
}


def _record_day(record: dict[str, Any]) -> str | None:
    for key in ("day", "date", "timestamp", "start_datetime"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value[:10]
    return None


def _pick(record: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if key in allowed and isinstance(value, (int, float, str, bool))
    }


def _fetch_compact(start: str, end: str) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Fetch only the daily fields needed for analytics, in parallel."""
    by_day: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}

    def fetch(name: str):
        return name, _fetch_collection(name, start_date=start, end_date=end, max_records=100)

    with ThreadPoolExecutor(max_workers=len(_COLLECTION_FIELDS)) as pool:
        futures = {pool.submit(fetch, name): name for name in _COLLECTION_FIELDS}
        for future in as_completed(futures):
            name = futures[future]
            try:
                _, payload = future.result()
                records = payload.get("data", []) if isinstance(payload, dict) else []
                if isinstance(records, dict):
                    records = [records]
                for record in records:
                    if not isinstance(record, dict):
                        continue
                    day = _record_day(record)
                    if day:
                        by_day.setdefault(day, {})[name] = _pick(record, _COLLECTION_FIELDS[name])
            except Exception as exc:
                errors[name] = f"{type(exc).__name__}: {exc}"

    return by_day, errors


def _values(daily: list[dict[str, Any]], collection: str, field: str) -> list[float]:
    values: list[float] = []
    for row in daily:
        record = row.get(collection)
        value = record.get(field) if isinstance(record, dict) else None
        if isinstance(value, (int, float)):
            values.append(float(value))
    return values


def _aggregate(values: list[float]) -> dict[str, Any] | None:
    if not values:
        return None
    return {
        "mean": round(mean(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "n": len(values),
        "change_first_to_last": round(values[-1] - values[0], 2) if len(values) > 1 else 0,
    }


def _build_analysis(days: int, include_recent: int = 0) -> dict[str, Any]:
    days = max(1, min(int(days), 90))
    include_recent = max(0, min(int(include_recent), 5))
    start, end = _date_range(None, None, days=days)
    by_day, errors = _fetch_compact(start, end)
    ordered = sorted(by_day.items())
    daily = [{"date": day, **row} for day, row in ordered]

    metrics: dict[str, Any] = {}
    for name, (collection, field) in _METRICS.items():
        summary = _aggregate(_values(daily, collection, field))
        if summary is not None:
            metrics[name] = summary

    recent: list[dict[str, Any]] = []
    if include_recent:
        for day, row in reversed(ordered[-include_recent:]):
            recent.append({"date": day, **row})

    return {
        "period": {"start": start, "end": end, "requested_days": days},
        "metrics": metrics,
        "recent": recent,
        "days_with_any_data": len(ordered),
        "errors": {key: value[:180] for key, value in errors.items()},
    }


@mcp.tool(
    name="get_health_snapshot",
    description=(
        "Primary Oura analytics endpoint for broad health questions. Computes server-side "
        "averages, min/max, sample counts, and first-to-last changes for sleep, readiness, "
        "activity, steps, calories, stress, recovery, and temperature. Returns no raw Oura records."
    ),
)
def get_health_snapshot(days: int = 14, include_detail: bool = False) -> dict[str, Any]:
    """Return compact Oura health statistics for the requested recent window."""
    return _build_analysis(days, 3 if include_detail else 0)


@mcp.tool(
    name="get_recent_activity_and_recovery",
    description=(
        "Compact Oura activity/recovery summary. Use for recent health questions; it returns "
        "only averages, ranges, sample counts, and a few recent daily values, never raw collections."
    ),
)
def get_recent_activity_and_recovery(days: int = 14) -> dict[str, Any]:
    """Return compact recent activity, sleep, readiness, stress, and recovery statistics."""
    result = _build_analysis(days, 3)
    result["averages"] = {
        name: summary["mean"]
        for name, summary in result["metrics"].items()
        if name in {"activity_score", "sleep_score", "readiness_score", "stress_high"}
    }
    return result
