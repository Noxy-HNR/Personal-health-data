"""Small server-side Oura analytics endpoints.

The model should receive aggregates, not raw Oura collections. All collection
fetching, date alignment, filtering, and arithmetic happen in this module.

This is the single Oura analytics module -- it used to be split across
analytics_tools.py and health_analysis_tools.py, both of which independently
re-fetched daily collections and built their own aggregates. health_analysis_tools.py
was a near-duplicate of get_health_snapshot/get_recent_activity_and_recovery below
and was deleted outright. analytics_tools.py's snapshot-style tool was likewise a
duplicate, but its trend/comparison/anomaly/correlation/sleep-debt/regularity tools
were not available anywhere else, so those were migrated here rather than deleted --
they already returned compact, pre-aggregated results (mean/slope/r_squared/pearson_r,
never raw rows), which is the same discipline this module was designed around.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from math import sqrt
from statistics import mean, median
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
        # "day" is requested explicitly alongside each collection's own allowed
        # fields so Oura's response stays sparse -- this used to fetch every
        # field of every collection and rely on _pick() to discard the rest
        # after the fact, which cost unnecessary Oura API bandwidth.
        fields = ",".join(["day"] + sorted(_COLLECTION_FIELDS[name]))
        return name, _fetch_collection(name, start_date=start, end_date=end, fields=fields, max_records=100)

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
        "median": round(median(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "n": len(values),
        "change_first_to_last": round(values[-1] - values[0], 2) if len(values) > 1 else 0,
    }


def _expected_dates(start: str, end: str) -> list[str]:
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    days = []
    d = s
    while d <= e:
        days.append(d.isoformat())
        d += timedelta(days=1)
    return days


def _coverage_gaps(by_day: dict[str, dict[str, Any]], expected: list[str]) -> dict[str, Any]:
    """Report which requested dates are missing data, per metric -- only for
    metrics that actually have a gap, so a fully-covered window costs nothing
    extra in the response."""
    gaps: dict[str, Any] = {}
    for name, (collection, field) in _METRICS.items():
        missing = [
            day for day in expected
            if not (isinstance(by_day.get(day, {}).get(collection), dict) and by_day[day][collection].get(field) is not None)
        ]
        if missing:
            gaps[name] = {"days_with_data": len(expected) - len(missing), "missing_dates": missing}
    return gaps


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
        "coverage_gaps": _coverage_gaps(by_day, _expected_dates(start, end)),
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


# ------------------------------------------------------------------
# Trend / comparison / anomaly / correlation tools.
# Migrated from analytics_tools.py (deleted) -- these fetch a metric's raw
# Oura rows internally and immediately collapse them into a statistic
# (slope, r_squared, pearson_r, std-dev, ...); no raw row ever leaves
# these functions, matching the same discipline as get_health_snapshot.
# ------------------------------------------------------------------

_TREND_METRICS = {
    "sleep_score": ("daily_sleep", "score"),
    "readiness_score": ("daily_readiness", "score"),
    "activity_score": ("daily_activity", "score"),
    "stress_high": ("daily_stress", "stress_high"),
    "resting_heart_rate": ("daily_readiness", "contributors.resting_heart_rate"),
    "hrv_balance": ("daily_readiness", "contributors.hrv_balance"),
    "recovery_index": ("daily_readiness", "contributors.recovery_index"),
    "temperature_deviation": ("daily_readiness", "temperature_deviation"),
}


def _nums(rows: list[dict[str, Any]], *keys: str) -> list[float]:
    out = []
    for r in rows:
        v = r
        for k in keys:
            v = v.get(k) if isinstance(v, dict) else None
        if isinstance(v, (int, float)):
            out.append(float(v))
    return out


def _pearson(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n < 3:
        return 0.0
    a = a[:n]; b = b[:n]
    ma = mean(a); mb = mean(b)
    da = [x - ma for x in a]; db = [x - mb for x in b]
    den = sqrt(sum(x * x for x in da) * sum(x * x for x in db))
    return sum(x * y for x, y in zip(da, db)) / den if den else 0.0


def _trend(values: list[float]) -> dict[str, Any]:
    n = len(values)
    if n < 3:
        return {"direction": "insufficient_data", "slope": 0, "r_squared": 0, "change_percent": 0, "n": n}
    x = list(range(n)); mx = mean(x); my = mean(values)
    den = sum((i - mx) ** 2 for i in x)
    slope = sum((i - mx) * (v - my) for i, v in zip(x, values)) / den if den else 0
    ss_tot = sum((v - my) ** 2 for v in values)
    ss_res = sum((v - (my + slope * (i - mx))) ** 2 for i, v in zip(x, values))
    r2 = 1 - ss_res / ss_tot if ss_tot else 0
    pct = (values[-1] - values[0]) / abs(values[0]) * 100 if values[0] else 0
    return {
        "direction": "rising" if slope > 0.05 else "falling" if slope < -0.05 else "stable",
        "slope_per_day": round(slope, 4),
        "r_squared": round(max(0, r2), 4),
        "change_percent": round(pct, 2),
        "n": n,
    }


def _iqr(values: list[float]) -> tuple[float, float]:
    if len(values) < 4:
        return (min(values), max(values))
    s = sorted(values)
    def q(p):
        x = (len(s) - 1) * p; i = int(x); f = x - i
        return s[i] + (s[min(i + 1, len(s) - 1)] - s[i]) * f
    q1 = q(.25); q3 = q(.75); d = q3 - q1
    return q1 - 1.5 * d, q3 + 1.5 * d


@mcp.tool()
def get_personal_baseline(days: int = 30) -> dict[str, Any]:
    """Calculate personal baselines for major daily Oura metrics over the requested window."""
    end = date.today(); start = end - timedelta(days=max(1, min(days, 365)) - 1)
    result: dict[str, Any] = {"window_days": days, "start_date": start.isoformat(), "end_date": end.isoformat(), "metrics": {}}
    for name, (collection, key) in _TREND_METRICS.items():
        rows = _fetch_collection(collection, start.isoformat(), end.isoformat(), max_records=1000).get("data", [])
        vals = _nums(rows, *key.split('.'))
        if vals:
            lo, hi = _iqr(vals)
            result["metrics"][name] = {
                "mean": round(mean(vals), 2), "median": round(median(vals), 2),
                "min": round(min(vals), 2), "max": round(max(vals), 2),
                "iqr_expected_range": [round(lo, 2), round(hi, 2)], "n": len(vals),
            }
    return result


@mcp.tool()
def find_metric_trends(metric: str = "readiness_score", days: int = 30) -> dict[str, Any]:
    """Find the trend of a major Oura daily metric. Supported metrics: sleep_score, readiness_score, activity_score, stress_high, resting_heart_rate, hrv_balance, recovery_index, temperature_deviation."""
    if metric not in _TREND_METRICS:
        raise ValueError(f"Unsupported metric. Choose from: {', '.join(_TREND_METRICS)}")
    end = date.today(); start = end - timedelta(days=max(3, min(days, 365)) - 1)
    collection, key = _TREND_METRICS[metric]
    rows = _fetch_collection(collection, start.isoformat(), end.isoformat(), max_records=2000).get("data", [])
    vals = _nums(rows, *key.split('.'))
    return {
        "metric": metric, "period_days": days, "trend": _trend(vals),
        "baseline": round(mean(vals), 2) if vals else None,
        "recent": round(vals[-1], 2) if vals else None,
    }


@mcp.tool()
def compare_periods(metric: str = "readiness_score", recent_days: int = 14, baseline_days: int = 30) -> dict[str, Any]:
    """Compare a recent Oura metric window against the preceding baseline window."""
    if metric not in _TREND_METRICS:
        raise ValueError("Unsupported metric")
    end = date.today(); recent_start = end - timedelta(days=recent_days - 1); base_start = recent_start - timedelta(days=baseline_days)
    collection, key = _TREND_METRICS[metric]
    rows = _fetch_collection(collection, base_start.isoformat(), end.isoformat(), max_records=3000).get("data", [])
    vals = _nums(rows, *key.split('.'))
    # Collection ordering is chronological in Oura responses; use last windows conservatively.
    recent = vals[-recent_days:]; baseline = vals[-(recent_days + baseline_days):-recent_days]
    a = mean(recent) if recent else 0; b = mean(baseline) if baseline else 0
    return {
        "metric": metric,
        "recent": {"days": len(recent), "mean": round(a, 2)},
        "baseline": {"days": len(baseline), "mean": round(b, 2)},
        "absolute_change": round(a - b, 2) if baseline else None,
        "percent_change": round((a - b) / abs(b) * 100, 2) if b else None,
    }


@mcp.tool()
def find_anomalies(metric: str = "readiness_score", days: int = 30) -> dict[str, Any]:
    """Find unusually high/low daily values using a personal IQR rule."""
    if metric not in _TREND_METRICS:
        raise ValueError("Unsupported metric")
    end = date.today(); start = end - timedelta(days=max(7, min(days, 365)) - 1)
    collection, key = _TREND_METRICS[metric]
    rows = _fetch_collection(collection, start.isoformat(), end.isoformat(), max_records=3000).get("data", [])
    vals = _nums(rows, *key.split('.')); lo, hi = _iqr(vals) if vals else (0, 0)
    return {
        "metric": metric, "window_days": days, "expected_range": [round(lo, 2), round(hi, 2)],
        "anomalies": [{"value": v, "index": i} for i, v in enumerate(vals) if v < lo or v > hi],
        "n": len(vals),
    }


@mcp.tool()
def calculate_sleep_debt(days: int = 14) -> dict[str, Any]:
    """Estimate sleep debt against a configurable 8-hour target using Oura daily sleep duration."""
    end = date.today(); start = end - timedelta(days=max(1, min(days, 90)) - 1)
    rows = _fetch_collection("daily_sleep", start.isoformat(), end.isoformat(), max_records=1000).get("data", [])
    # Prefer contributors.total_sleep_duration when present; fall back to total_sleep_duration.
    vals = []
    for r in rows:
        v = r.get("contributors", {}).get("total_sleep_duration", r.get("total_sleep_duration"))
        if isinstance(v, (int, float)):
            vals.append(float(v))
    target = 8 * 3600; debt = sum(max(0, target - v) for v in vals); avg = mean(vals) / 3600 if vals else None
    return {
        "days_with_data": len(vals), "target_hours": 8,
        "average_sleep_hours": round(avg, 2) if avg else None,
        "estimated_debt_hours": round(debt / 3600, 2),
    }


@mcp.tool()
def calculate_sleep_regularity(days: int = 30) -> dict[str, Any]:
    """Measure sleep/wake timing regularity from detailed Oura sleep records."""
    from datetime import datetime
    end = date.today(); start = end - timedelta(days=max(7, min(days, 90)) - 1)
    rows = _fetch_collection("sleep", start.isoformat(), end.isoformat(), max_records=2000).get("data", [])
    starts: list[float] = []; ends: list[float] = []
    for r in rows:
        for field, target in (("bedtime_start", starts), ("bedtime_end", ends)):
            v = r.get(field)
            if v:
                try:
                    target.append(datetime.fromisoformat(v.replace('Z', '+00:00')).timestamp() % 86400)
                except Exception:
                    pass
    def sd(a):
        if len(a) < 2:
            return None
        m = mean(a); return sqrt(sum((x - m) ** 2 for x in a) / len(a)) / 3600
    return {
        "window_days": days, "records": len(rows),
        "bedtime_std_hours": round(sd(starts), 2) if sd(starts) is not None else None,
        "wake_time_std_hours": round(sd(ends), 2) if sd(ends) is not None else None,
        "interpretation": "lower variation means more regular timing",
    }


@mcp.tool()
def correlate_oura_metrics(metric_a: str = "sleep_score", metric_b: str = "readiness_score", days: int = 90) -> dict[str, Any]:
    """Calculate Pearson correlation between two daily Oura metrics over the same period."""
    if metric_a not in _TREND_METRICS or metric_b not in _TREND_METRICS:
        raise ValueError("Unsupported metric")
    end = date.today(); start = end - timedelta(days=max(7, min(days, 365)) - 1)
    ra = _fetch_collection(_TREND_METRICS[metric_a][0], start.isoformat(), end.isoformat(), max_records=3000).get("data", [])
    rb = _fetch_collection(_TREND_METRICS[metric_b][0], start.isoformat(), end.isoformat(), max_records=3000).get("data", [])

    def keyed(rows, key):
        out = {}
        for r in rows:
            d = r.get("day") or str(r.get("timestamp", ""))[:10]
            v = r
            for k in key.split('.'):
                v = v.get(k) if isinstance(v, dict) else None
            if d and isinstance(v, (int, float)):
                out[d] = float(v)
        return out

    a = keyed(ra, _TREND_METRICS[metric_a][1]); b = keyed(rb, _TREND_METRICS[metric_b][1])
    dayset = sorted(set(a) & set(b)); av = [a[d] for d in dayset]; bv = [b[d] for d in dayset]
    r = _pearson(av, bv)
    return {
        "metric_a": metric_a, "metric_b": metric_b, "days": len(dayset), "pearson_r": round(r, 4),
        "strength": "strong" if abs(r) >= .7 else "moderate" if abs(r) >= .4 else "weak" if abs(r) >= .2 else "minimal",
        "direction": "positive" if r > 0 else "negative" if r < 0 else "none",
        "warning": "Correlation does not establish causation.",
    }
