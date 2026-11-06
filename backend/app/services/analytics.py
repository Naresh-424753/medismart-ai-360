"""Lightweight predictive analytics (no heavy deps)."""
from __future__ import annotations

import math
import statistics


def forecast(series: list[float], horizon: int = 7, window: int = 7) -> list[float]:
    """Moving-average + linear-trend forecast. Returns [] if there's no history."""
    if not series:
        return []
    w = series[-window:]
    base = sum(w) / len(w)
    slope = 0.0
    if len(w) >= 3:
        xs = list(range(len(w)))
        mx, my = statistics.mean(xs), statistics.mean(w)
        den = sum((x - mx) ** 2 for x in xs)
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, w)) / den if den else 0.0
    return [round(max(0.0, base + slope * (i + 1)), 1) for i in range(horizon)]


def bed_demand(daily_admissions: list[float], avg_stay_days: float) -> int | None:
    """Little's law: occupied beds ~ arrival rate x length of stay."""
    if not daily_admissions:
        return None
    rate = sum(daily_admissions[-14:]) / len(daily_admissions[-14:])
    return math.ceil(rate * avg_stay_days)


def anomalies(values: list[float], z: float = 2.5, min_n: int = 8) -> list[int]:
    """Indexes of points whose z-score vs. the preceding history exceeds z."""
    out = []
    for i in range(min_n, len(values)):
        hist = values[:i]
        sd = statistics.pstdev(hist)
        if sd and abs(values[i] - statistics.mean(hist)) / sd > z:
            out.append(i)
    return out


def readmission_risk(age: int, admissions_last_year: int, chronic_conditions: int, length_of_stay: int, emergency_admission: bool) -> dict:
    """Transparent additive score (LACE-index inspired). Demo only - validate before clinical use."""
    los = 1 if length_of_stay < 1 else length_of_stay if length_of_stay <= 3 else 4 if length_of_stay <= 6 else 5 if length_of_stay <= 13 else 7
    score = los + (3 if emergency_admission else 0) + min(chronic_conditions, 4) + min(admissions_last_year, 4) + (1 if age >= 65 else 0)
    level = "low" if score <= 4 else "moderate" if score <= 9 else "high"
    return {"score": score, "level": level, "scale": "0-16 (higher = more likely to be readmitted within 30 days)"}


def trend(values: list[float]) -> str:
    if len(values) < 3:
        return "insufficient data"
    half = len(values) // 2
    a, b = statistics.mean(values[:half]), statistics.mean(values[half:])
    if a == 0:
        return "stable"
    ch = (b - a) / abs(a)
    return "rising" if ch > 0.05 else "falling" if ch < -0.05 else "stable"
