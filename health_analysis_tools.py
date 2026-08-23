from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from statistics import mean
from typing import Any


def register_health_analysis_tools(mcp):
    from oura_service import _fetch_collection

    specs = {
        "sleep_score": ("daily_sleep", "score"),
        "readiness_score": ("daily_readiness", "score"),
        "activity_score": ("daily_activity", "score"),
        "steps": ("daily_activity", "steps"),
        "active_calories": ("daily_activity", "active_calories"),
        "stress_high": ("daily_stress", "stress_high"),
        "recovery_high": ("daily_stress", "recovery_high"),
        "temperature_deviation": ("daily_readiness", "temperature_deviation"),
    }

    def value(row: dict[str, Any], path: str):
        v: Any = row
        for key in path.split("."):
            v = v.get(key) if isinstance(v, dict) else None
        return v if isinstance(v, (int, float)) else None

    @mcp.tool()
    def analyze_health(days: int = 14, include_recent: int = 3) -> dict[str, Any]:
        """Analyze recent Oura data server-side and return a small conversational summary.

        Fetches the required Oura collections in parallel, aligns them by date, and
        calculates averages, ranges, simple endpoint-to-endpoint changes, and recent
        daily values. The model never receives raw Oura records from this tool.
        """
        days = max(3, min(int(days), 90))
        include_recent = max(0, min(int(include_recent), 7))
        end = date.today()
        start = end - timedelta(days=days - 1)
        collections = sorted({collection for collection, _ in specs.values()})

        payloads: dict[str, list[dict[str, Any]]] = {}
        errors: dict[str, str] = {}

        def fetch(collection: str):
            return collection, _fetch_collection(
                collection,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                max_records=days + 10,
            ).get("data", [])

        with ThreadPoolExecutor(max_workers=len(collections)) as pool:
            future_map = {pool.submit(fetch, collection): collection for collection in collections}
            for future in as_completed(future_map):
                collection = future_map[future]
                try:
                    _, rows = future.result()
                    payloads[collection] = [r for r in rows if isinstance(r, dict)]
                except Exception as exc:
                    errors[collection] = f"{type(exc).__name__}: {exc}"

        by_day: dict[str, dict[str, Any]] = {}
        for metric, (collection, path) in specs.items():
            for row in payloads.get(collection, []):
                day = row.get("day") or row.get("date") or str(row.get("timestamp", ""))[:10]
                v = value(row, path)
                if day and v is not None:
                    by_day.setdefault(str(day)[:10], {})[metric] = float(v)

        ordered = sorted(by_day.items())
        metrics: dict[str, Any] = {}
        for metric in specs:
            vals = [row[metric] for _, row in ordered if metric in row]
            if not vals:
                continue
            metrics[metric] = {
                "mean": round(mean(vals), 2),
                "min": round(min(vals), 2),
                "max": round(max(vals), 2),
                "n": len(vals),
                "change_first_to_last": round(vals[-1] - vals[0], 2) if len(vals) > 1 else 0,
            }

        recent = []
        for day, row in reversed(ordered[-include_recent:]):
            recent.append({"date": day, **{k: round(v, 2) for k, v in row.items()}})

        return {
            "period": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
            "metrics": metrics,
            "recent": recent,
            "days_with_any_data": len(ordered),
            "errors": {k: v[:180] for k, v in errors.items()},
        }
