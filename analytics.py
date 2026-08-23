"""Local-first health analytics for Oura-derived daily data.

The functions are intentionally deterministic and return compact JSON-friendly
objects so a local LLM can consume them without loading large raw datasets.
"""
from __future__ import annotations

from datetime import date, timedelta
from math import sqrt
from statistics import mean, median, stdev
from typing import Any, Iterable


def _nums(values: Iterable[Any]) -> list[float]:
    out = []
    for v in values:
        try:
            if v is not None:
                out.append(float(v))
        except (TypeError, ValueError):
            pass
    return out


def summary(values: Iterable[Any]) -> dict[str, Any]:
    x = _nums(values)
    if not x:
        return {"count": 0}
    return {
        "count": len(x), "mean": mean(x), "median": median(x),
        "min": min(x), "max": max(x),
        "stddev": stdev(x) if len(x) > 1 else 0.0,
    }


def rolling(values: list[float], window: int) -> dict[str, Any]:
    x = _nums(values)
    tail = x[-window:]
    return {"window_days": window, "count": len(tail), "mean": mean(tail) if tail else None}


def trend(values: Iterable[Any]) -> dict[str, Any]:
    y = _nums(values)
    n = len(y)
    if n < 3:
        return {"count": n, "direction": "insufficient_data", "slope": 0.0, "r_squared": 0.0}
    xm = (n - 1) / 2
    ym = mean(y)
    den = sum((i - xm) ** 2 for i in range(n))
    slope = sum((i - xm) * (v - ym) for i, v in enumerate(y)) / den if den else 0.0
    pred = [ym + slope * (i - xm) for i in range(n)]
    ss_tot = sum((v - ym) ** 2 for v in y)
    ss_res = sum((v - p) ** 2 for v, p in zip(y, pred))
    r2 = max(0.0, 1 - ss_res / ss_tot) if ss_tot else 0.0
    pct = (slope / ym * 100) if ym else 0.0
    direction = "stable" if abs(pct) < 0.5 else ("increasing" if slope > 0 else "decreasing")
    return {"count": n, "slope_per_day": slope, "percent_per_day": pct, "r_squared": r2, "direction": direction}


def correlation(a: Iterable[Any], b: Iterable[Any]) -> dict[str, Any]:
    x, y = _nums(a), _nums(b)
    n = min(len(x), len(y))
    x, y = x[-n:], y[-n:]
    if n < 3:
        return {"n": n, "r": None, "strength": "insufficient_data"}
    mx, my = mean(x), mean(y)
    dx, dy = [v - mx for v in x], [v - my for v in y]
    den = sqrt(sum(v*v for v in dx) * sum(v*v for v in dy))
    r = sum(a*b for a, b in zip(dx, dy)) / den if den else 0.0
    ar = abs(r)
    strength = "very_strong" if ar >= .8 else "strong" if ar >= .6 else "moderate" if ar >= .4 else "weak" if ar >= .2 else "negligible"
    return {"n": n, "r": r, "strength": strength, "direction": "positive" if r > 0 else "negative" if r < 0 else "none"}


def iqr_outliers(values: Iterable[Any], multiplier: float = 1.5) -> dict[str, Any]:
    x = sorted(_nums(values))
    if len(x) < 4:
        return {"count": len(x), "outliers": []}
    def q(p: float) -> float:
        pos = (len(x)-1)*p
        lo = int(pos); hi = min(lo+1, len(x)-1); frac = pos-lo
        return x[lo] + frac*(x[hi]-x[lo])
    q1, q3 = q(.25), q(.75)
    iqr = q3-q1
    lo, hi = q1-multiplier*iqr, q3+multiplier*iqr
    return {"count": len(x), "q1": q1, "q3": q3, "lower": lo, "upper": hi, "outliers": [v for v in x if v < lo or v > hi]}


def personal_baseline(rows: list[dict[str, Any]], field: str, days: int = 30) -> dict[str, Any]:
    vals = [r.get(field) for r in rows[-days:]]
    s = summary(vals)
    s.update({"field": field, "window_days": days})
    return s


def compare_periods(rows: list[dict[str, Any]], field: str, first_days: int, second_days: int) -> dict[str, Any]:
    if not rows:
        return {"field": field, "error": "no_data"}
    first = _nums([r.get(field) for r in rows[-(first_days+second_days):-second_days or None]])
    second = _nums([r.get(field) for r in rows[-second_days:]])
    a, b = mean(first) if first else None, mean(second) if second else None
    return {"field": field, "first_mean": a, "second_mean": b, "absolute_change": (b-a) if a is not None and b is not None else None,
            "percent_change": ((b-a)/a*100) if a not in (None, 0) and b is not None else None,
            "first_n": len(first), "second_n": len(second)}


def sleep_debt(rows: list[dict[str, Any]], target_hours: float = 8.0, days: int = 7) -> dict[str, Any]:
    vals = _nums([r.get("sleep_duration_hours") for r in rows[-days:]])
    debt = sum(max(0.0, target_hours-v) for v in vals)
    return {"days": days, "target_hours": target_hours, "observed_days": len(vals), "sleep_debt_hours": debt, "average_sleep_hours": mean(vals) if vals else None}


def regularity(rows: list[dict[str, Any]], bedtime_field: str = "bedtime_hour", waketime_field: str = "waketime_hour", days: int = 30) -> dict[str, Any]:
    b = _nums([r.get(bedtime_field) for r in rows[-days:]])
    w = _nums([r.get(waketime_field) for r in rows[-days:]])
    def sd(v: list[float]) -> float: return stdev(v) if len(v) > 1 else 0.0
    return {"days": days, "observed_days": min(len(b), len(w)), "bedtime_std_hours": sd(b), "waketime_std_hours": sd(w),
            "bedtime_consistent": sd(b) < 1.0 if b else None, "waketime_consistent": sd(w) < 1.0 if w else None}
