"""Threshold rules for vital signs. Adult defaults."""
from __future__ import annotations

# metric: (label, unit, crit_low, warn_low, warn_high, crit_high)
RULES = {
    "heart_rate": ("Heart rate", "bpm", 40, 50, 110, 130),
    "spo2": ("SpO2", "%", 90, 94, 101, 101),
    "temperature": ("Body temperature", "C", 35.0, 36.0, 37.8, 39.5),
    "systolic": ("Systolic BP", "mmHg", 80, 90, 140, 180),
    "diastolic": ("Diastolic BP", "mmHg", 50, 60, 90, 120),
    "respiratory_rate": ("Respiratory rate", "/min", 8, 11, 22, 30),
    "glucose": ("Blood glucose", "mg/dL", 54, 70, 180, 300),
}


def evaluate(v: dict) -> list[dict]:
    alerts = []
    for k, (label, unit, cl, wl, wh, ch) in RULES.items():
        x = v.get(k)
        if x is None:
            continue
        sev = None
        if x <= cl:
            sev, kind = "critical", "low"
        elif x < wl:
            sev, kind = "warning", "low"
        elif x >= ch:
            sev, kind = "critical", "high"
        elif x > wh:
            sev, kind = "warning", "high"
        if sev:
            alerts.append({"metric": k, "label": label, "value": x, "unit": unit, "severity": sev, "message": f"{label} is {kind} ({x} {unit})"})
    if v.get("fall_detected"):
        alerts.append({"metric": "fall", "label": "Fall", "value": 1, "unit": "", "severity": "critical", "message": "Possible fall detected"})
    return alerts


def overall(alerts: list[dict]) -> str:
    if any(a["severity"] == "critical" for a in alerts):
        return "critical"
    return "warning" if alerts else "normal"
