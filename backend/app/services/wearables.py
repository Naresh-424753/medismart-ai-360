"""Wearable data: normalisation of samples from any source and an Apple Health export (export.xml / export.zip) parser.

Why not direct Fitbit / Google Fit cloud connectors? The Fitbit Web API was shut down on 30 Oct 2026 and the Google Fit
APIs are being retired. Data now reaches an app through (a) Health Connect on Android and HealthKit on iOS, which a small
phone-side bridge posts to /wearables/ingest, or (b) the user's own Apple Health export.
"""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta, timezone

TYPES = {"heart_rate", "resting_heart_rate", "spo2", "temperature", "respiratory_rate", "steps", "sleep_minutes", "active_minutes", "calories", "distance_m"}
RANGES = {"heart_rate": (20, 250), "resting_heart_rate": (20, 200), "spo2": (50, 100), "temperature": (30, 45), "respiratory_rate": (4, 60),
          "steps": (0, 100000), "sleep_minutes": (0, 1440), "active_minutes": (0, 1440), "calories": (0, 20000), "distance_m": (0, 200000)}
APPLE_TYPES = {
    "HKQuantityTypeIdentifierHeartRate": "heart_rate", "HKQuantityTypeIdentifierRestingHeartRate": "resting_heart_rate",
    "HKQuantityTypeIdentifierOxygenSaturation": "spo2", "HKQuantityTypeIdentifierBodyTemperature": "temperature",
    "HKQuantityTypeIdentifierRespiratoryRate": "respiratory_rate", "HKQuantityTypeIdentifierStepCount": "steps",
    "HKQuantityTypeIdentifierAppleExerciseTime": "active_minutes", "HKQuantityTypeIdentifierActiveEnergyBurned": "calories",
    "HKQuantityTypeIdentifierDistanceWalkingRunning": "distance_m", "HKCategoryTypeIdentifierSleepAnalysis": "sleep_minutes",
}
ASLEEP = ("Asleep", "AsleepUnspecified", "AsleepCore", "AsleepDeep", "AsleepREM")


def parse_ts(s: str) -> datetime:
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            return datetime.strptime(s.replace("Z", "+0000"), fmt).astimezone(timezone.utc)
        except ValueError:
            pass
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def clean_sample(s: dict) -> dict | None:
    """Validates one sample; returns {type, value, ts, end_ts} or None when invalid/out of range."""
    t = s.get("type")
    if t not in TYPES:
        return None
    try:
        v = float(s["value"])
        ts = parse_ts(str(s["ts"]))
        end = parse_ts(str(s["end_ts"])) if s.get("end_ts") else ts
    except (KeyError, ValueError, TypeError):
        return None
    if t == "spo2" and v <= 1:
        v *= 100
    lo, hi = RANGES[t]
    if not lo <= v <= hi or ts > datetime.now(timezone.utc) + timedelta(minutes=5):
        return None
    return {"type": t, "value": round(v, 2), "ts": ts.isoformat(), "end_ts": end.isoformat()}


def _open_export(fileobj, size_cap=2_000_000_000):
    head = fileobj.read(4)
    fileobj.seek(0)
    if head[:2] == b"PK":
        zf = zipfile.ZipFile(fileobj)
        member = next((i for i in zf.infolist() if i.filename.lower().endswith("export.xml")), None)
        if not member:
            raise ValueError("export.xml not found inside the zip")
        if member.file_size > size_cap:
            raise ValueError("export.xml is too large")
        return zf.open(member)
    return fileobj


def parse_apple_health(fileobj, days: int = 30, max_samples: int = 20000) -> dict:
    """Streams export.xml. Heart-rate samples are averaged into 15-minute buckets to keep the volume manageable."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    out: list[dict] = []
    hr_buckets: dict = {}
    seen = skipped = 0
    for _, el in ET.iterparse(_open_export(fileobj), events=("end",)):
        if el.tag != "Record":
            el.clear()
            continue
        a = el.attrib
        el.clear()
        t = APPLE_TYPES.get(a.get("type", ""))
        if not t:
            continue
        seen += 1
        try:
            start, end = parse_ts(a["startDate"]), parse_ts(a["endDate"])
            if end < since:
                continue
            if t == "sleep_minutes":
                if not a.get("value", "").endswith(ASLEEP):
                    continue
                val = (end - start).total_seconds() / 60
            else:
                val = float(a["value"])
                if t == "temperature" and a.get("unit") == "degF":
                    val = (val - 32) * 5 / 9
                if t == "distance_m" and a.get("unit") == "km":
                    val *= 1000
        except (KeyError, ValueError):
            skipped += 1
            continue
        if t == "heart_rate":
            if not RANGES["heart_rate"][0] <= val <= RANGES["heart_rate"][1]:
                skipped += 1
                continue
            k = int(start.timestamp() // 900)
            b = hr_buckets.setdefault(k, [0.0, 0, start])
            b[0] += val
            b[1] += 1
            continue
        c = clean_sample({"type": t, "value": val, "ts": start.isoformat(), "end_ts": end.isoformat()})
        if c:
            out.append(c)
        else:
            skipped += 1
    for s, n, t0 in hr_buckets.values():
        c = clean_sample({"type": "heart_rate", "value": s / n, "ts": t0.isoformat()})
        if c:
            out.append(c)
    out.sort(key=lambda x: x["ts"], reverse=True)
    return {"samples": out[:max_samples], "records_seen": seen, "skipped_invalid": skipped, "truncated": len(out) > max_samples}


def daily_summary(samples: list[dict], tz) -> list[dict]:
    days: dict = {}
    for s in samples:
        end = parse_ts(s["end_ts"] if s["type"] == "sleep_minutes" else s["ts"]).astimezone(tz)
        d = days.setdefault(end.strftime("%Y-%m-%d"), {"date": end.strftime("%Y-%m-%d"), "steps": 0, "sleep_hours": 0.0, "active_minutes": 0, "calories": 0, "distance_km": 0.0,
                                                       "_hr": [], "_rhr": [], "_spo2": []})
        v, t = s["value"], s["type"]
        if t == "steps":
            d["steps"] += int(v)
        elif t == "sleep_minutes":
            d["sleep_hours"] += v / 60
        elif t == "active_minutes":
            d["active_minutes"] += v
        elif t == "calories":
            d["calories"] += v
        elif t == "distance_m":
            d["distance_km"] += v / 1000
        elif t == "heart_rate":
            d["_hr"].append(v)
        elif t == "resting_heart_rate":
            d["_rhr"].append(v)
        elif t == "spo2":
            d["_spo2"].append(v)
    out = []
    for k in sorted(days):
        d = days[k]
        hr, rhr, sp = d.pop("_hr"), d.pop("_rhr"), d.pop("_spo2")
        d.update(sleep_hours=round(d["sleep_hours"], 1), active_minutes=round(d["active_minutes"]), calories=round(d["calories"]), distance_km=round(d["distance_km"], 2),
                 hr_avg=round(sum(hr) / len(hr)) if hr else None, hr_min=round(min(hr)) if hr else None, hr_max=round(max(hr)) if hr else None,
                 resting_hr=round(sum(rhr) / len(rhr)) if rhr else None, spo2_avg=round(sum(sp) / len(sp), 1) if sp else None)
        out.append(d)
    return out
