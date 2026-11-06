"""Early-warning score (NEWS2) + short-horizon trend projection + per-patient anomaly detection.

HONESTY NOTES (also in the README):
* NEWS2 (Royal College of Physicians, 2017) is a real, validated bedside score. The scoring table below is
  implemented as published (SpO2 scale 1, breathing air, patient assumed alert because consciousness is not measured).
* The "2-4 hours ahead" part is a *projection*: a damped, noise-tested linear trend of each vital sign is pushed
  forward and re-scored. It is NOT a model trained on ICU outcomes and has NOT been clinically validated.
  It is a screening aid that tells a clinician "this patient is drifting towards the urgent-review threshold".
* The anomaly detector is an IsolationForest trained on the patient's OWN earlier readings. It flags unusual
  combinations for that person; it does not know what disease is developing.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np

METRICS = ("heart_rate", "spo2", "temperature", "systolic", "respiratory_rate")
BOUNDS = {"heart_rate": (25, 220), "spo2": (50, 100), "temperature": (30, 43), "systolic": (40, 260), "respiratory_rate": (4, 60)}
URGENT, EMERGENCY = 5, 7
LEVEL_RANK = {"insufficient_data": 0, "stable": 1, "watch": 2, "high": 3, "critical": 4}


def _band(x, bands):
    for lo, hi, pts in bands:
        if lo <= x <= hi:
            return pts
    return 0


_NEWS = {
    "respiratory_rate": [(-1e9, 8, 3), (9, 11, 1), (12, 20, 0), (21, 24, 2), (25, 1e9, 3)],
    "spo2": [(-1e9, 91.5, 3), (91.5, 93.5, 2), (93.5, 95.5, 1), (95.5, 1e9, 0)],
    "systolic": [(-1e9, 90.5, 3), (90.5, 100.5, 2), (100.5, 110.5, 1), (110.5, 219.5, 0), (219.5, 1e9, 3)],
    "heart_rate": [(-1e9, 40.5, 3), (40.5, 50.5, 1), (50.5, 90.5, 0), (90.5, 110.5, 1), (110.5, 130.5, 2), (130.5, 1e9, 3)],
    "temperature": [(-1e9, 35.05, 3), (35.05, 36.05, 1), (36.05, 38.05, 0), (38.05, 39.05, 1), (39.05, 1e9, 2)],
}


def news2(values: dict) -> dict:
    parts = {}
    for k, bands in _NEWS.items():
        v = values.get(k)
        if v is not None:
            parts[k] = _band(float(v), bands)
    return {"total": sum(parts.values()), "parts": parts, "used": sorted(parts), "missing": [k for k in _NEWS if k not in parts],
            "single3": [k for k, p in parts.items() if p == 3]}


def _t(ts: str) -> float:
    d = datetime.fromisoformat(ts)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp() / 3600.0


def series_from_rows(rows: list[dict]) -> dict[str, list[tuple[float, float]]]:
    out: dict[str, list] = {m: [] for m in METRICS}
    for r in rows:
        t = _t(r["ts"])
        for m in METRICS:
            if r.get(m) is not None:
                out[m].append((t, float(r[m])))
    return {m: sorted(v) for m, v in out.items() if v}


def _trend(points: list[tuple[float, float]]):
    """Returns (level_now, slope_per_hour, significant). Needs >=4 points spanning >=30 min."""
    if len(points) < 4:
        return None
    t = np.array([p[0] for p in points]); y = np.array([p[1] for p in points])
    span = t[-1] - t[0]
    if span < 0.5:
        return None
    t0 = t[-1]; x = t - t0
    w = np.exp(x / 3.0)  # recent readings matter more
    A = np.vstack([np.ones_like(x), x]).T
    W = np.diag(w)
    beta = np.linalg.lstsq(W @ A, W @ y, rcond=None)[0]
    level, slope = float(beta[0]), float(beta[1])
    n = len(x)
    resid = y - A @ beta
    sd = float(np.sqrt(np.sum(resid ** 2) / max(n - 2, 1)))
    sxx = float(np.sum((x - x.mean()) ** 2)) or 1e-9
    se = sd / math.sqrt(sxx) if sd > 0 else 1e-9
    significant = abs(slope) / max(se, 1e-9) > 2.0  # noise-only drift is ignored
    return level, slope, significant


SHRINK = 0.6  # damping: linear extrapolation over hours is optimistic about persistence of a trend


def project(series: dict, hours: float) -> dict:
    """Projected value of each metric `hours` ahead (None if not enough clean data). Non-significant trends stay flat."""
    out = {}
    for m, pts in series.items():
        tr = _trend(pts)
        if tr is None:
            if pts:
                recent = [v for _, v in pts[-3:]]
                out[m] = float(np.median(recent))
            continue
        level, slope, sig = tr
        v = level + (slope * hours * SHRINK if sig else 0.0)
        lo, hi = BOUNDS[m]
        out[m] = min(max(v, lo), hi)
    return out


def current_values(series: dict) -> dict:
    return {m: float(np.median([v for _, v in pts[-3:]])) for m, pts in series.items() if pts}


def anomaly(baseline_rows: list[dict], recent_rows: list[dict]) -> dict:
    """IsolationForest on this patient's own history. Returns {available, flagged, score}."""
    from sklearn.ensemble import IsolationForest
    feats = [m for m in METRICS if sum(1 for r in baseline_rows if r.get(m) is not None) >= 40]
    if len(baseline_rows) < 60 or len(feats) < 2 or len(recent_rows) < 2:
        return {"available": False, "flagged": False, "score": None, "reason": "needs about 60 earlier readings from this patient"}
    X = np.array([[r.get(m) if r.get(m) is not None else np.nan for m in feats] for r in baseline_rows], dtype=float)
    med = np.nanmedian(X, axis=0)
    X = np.where(np.isnan(X), med, X)
    clf = IsolationForest(n_estimators=100, contamination=0.03, random_state=0).fit(X)
    R = np.array([[r.get(m) if r.get(m) is not None else np.nan for m in feats] for r in recent_rows[-3:]], dtype=float)
    R = np.where(np.isnan(R), med, R)
    pred = clf.predict(R)
    score = float(-np.mean(clf.score_samples(R)))
    flagged = int((pred == -1).sum()) >= min(2, len(R))
    return {"available": True, "flagged": flagged, "score": round(score, 3), "features": feats}


def assess(rows: list[dict], baseline_rows: list[dict] | None = None, now_ts: float | None = None) -> dict:
    """rows: this patient's readings from roughly the last 8 hours (any order)."""
    now_h = (now_ts / 3600.0) if now_ts else datetime.now(timezone.utc).timestamp() / 3600.0
    rows = sorted(rows, key=lambda r: r["ts"])
    fresh = [r for r in rows if now_h - _t(r["ts"]) <= 6.0]
    if len(fresh) < 2:
        return {"level": "insufficient_data", "reasons": ["Fewer than 2 readings in the last 6 hours."], "score_now": None, "projected": {}, "eta_to_urgent_hours": None,
                "anomaly": {"available": False, "flagged": False, "score": None}, "readings_used": len(fresh), "confidence": "none"}
    series = series_from_rows(fresh)
    cur = current_values(series)
    now_s = news2(cur)
    projected = {}
    for h in (2, 4):
        pv = project(series, h)
        sc = news2({**cur, **pv})
        projected[f"{h}h"] = {"score": sc["total"], "values": {k: round(v, 1) for k, v in pv.items()}, "single3": sc["single3"]}
    eta = None
    for step in range(1, 9):  # 0.5h .. 4h
        h = step * 0.5
        if news2({**cur, **project(series, h)})["total"] >= URGENT:
            eta = h
            break
    an = anomaly(baseline_rows or [], fresh)
    p2, p4 = projected["2h"]["score"], projected["4h"]["score"]
    reasons = []
    if now_s["total"] >= EMERGENCY:
        level = "critical"
    elif now_s["total"] >= URGENT or now_s["single3"] and now_s["total"] >= 3 or p2 >= EMERGENCY:
        level = "high"
    elif p4 >= URGENT or (an["flagged"] and p4 > now_s["total"]):
        level = "watch"
    else:
        level = "stable"
    if now_s["total"] >= URGENT:
        reasons.append(f"NEWS2 is {now_s['total']} now (5+ means urgent clinical review).")
    for k in now_s["single3"]:
        reasons.append(f"{k.replace('_', ' ')} alone scores 3 (extreme).")
    if eta is not None and now_s["total"] < URGENT:
        reasons.append(f"Trend projects NEWS2 reaching {URGENT}+ in about {eta:g} h.")
    trends = []
    for m, pts in series.items():
        tr = _trend(pts)
        if tr and tr[2] and abs(tr[1]) > 0:
            trends.append(f"{m.replace('_', ' ')} {'rising' if tr[1] > 0 else 'falling'} ~{abs(tr[1]):.1f}/h")
    if trends:
        reasons.append("Significant trends: " + "; ".join(trends) + ".")
    if an["flagged"]:
        reasons.append("Readings are unusual compared with this patient's own earlier pattern.")
    if now_s["missing"]:
        reasons.append("Not measured, so not scored: " + ", ".join(k.replace("_", " ") for k in now_s["missing"]) + ".")
    span = (_t(fresh[-1]["ts"]) - _t(fresh[0]["ts"]))
    conf = "low" if len(fresh) < 8 or span < 1 or len(now_s["used"]) < 3 else "moderate"
    return {"level": level, "score_now": now_s["total"], "parts": now_s["parts"], "current": {k: round(v, 1) for k, v in cur.items()}, "projected": projected,
            "eta_to_urgent_hours": eta, "anomaly": an, "reasons": reasons, "readings_used": len(fresh), "confidence": conf,
            "disclaimer": "Screening aid. NEWS2 is validated; the 2-4 hour projection and anomaly flag are not clinically validated predictions. Always use clinical judgement."}
