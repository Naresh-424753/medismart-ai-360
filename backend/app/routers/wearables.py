"""Wearable integration: phone-bridge ingest (Health Connect / HealthKit / Google Health), Apple Health export import, dashboard summary."""
import asyncio
import hashlib
import io
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..common import log_event, new_id, now
from ..config import settings
from ..db import get_db
from ..deps import require_roles, user_from_token
from ..services import wearables as W
from ..security import hash_key
from .vitals import process_reading

router = APIRouter(prefix="/wearables", tags=["wearables"])
patient_only = require_roles("patient")
SOURCES = {"health_connect", "apple_health", "google_health", "samsung_health", "fitbit_export", "garmin_export", "other"}


class SampleIn(BaseModel):
    type: str
    value: float
    ts: str
    end_ts: str | None = None


class IngestIn(BaseModel):
    source: str = "other"
    samples: list[SampleIn] = Field(max_length=5000)


async def _patient(authorization: str | None, x_device_key: str | None) -> str:
    """Patient JWT, or a device API key created in Vitals -> Register device (for the phone bridge)."""
    db = get_db()
    if x_device_key:
        dev = await db.devices.find_one({"key_hash": hash_key(x_device_key)})
        if not dev:
            raise HTTPException(401, "Invalid device key")
        return dev["user_id"]
    if authorization and authorization.lower().startswith("bearer "):
        u = await user_from_token(authorization[7:])
        if u["role"] == "patient":
            return u["id"]
    raise HTTPException(401, "Send a patient token or an X-Device-Key")


def _key(uid: str, s: dict, source: str) -> str:
    return hashlib.sha1(f"{uid}|{s['type']}|{s['ts']}|{s['end_ts']}|{source}".encode()).hexdigest()


async def store(db, uid: str, samples: list[dict], source: str) -> dict:
    """Idempotent: the same sample sent twice is stored once. Recent vital signs also feed the live vitals dashboard and alerts."""
    new, seen = [], set()
    for s in samples:
        k = _key(uid, s, source)
        if k in seen or await db.wearable_samples.find_one({"k": k}, {"_id": 1}):
            continue
        seen.add(k)
        new.append({"k": k, "user_id": uid, "source": source, **s})
    if new:
        try:
            await db.wearable_samples.insert_many([dict(n) for n in new], ordered=False)
        except Exception as e:  # a concurrent request stored some of them first (unique index): keep going
            if "duplicate" not in str(e).lower() and "E11000" not in str(e):
                raise
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    groups: dict = {}
    for s in new:
        if s["ts"] >= cutoff and s["type"] in ("heart_rate", "spo2", "temperature", "respiratory_rate"):
            g = groups.setdefault(s["ts"][:16], {})
            g[{"heart_rate": "heart_rate", "spo2": "spo2", "temperature": "temperature", "respiratory_rate": "respiratory_rate"}[s["type"]]] = s["value"]
    forwarded = 0
    for _, g in sorted(groups.items())[-50:]:
        await process_reading(db, uid, g, source)
        forwarded += 1
    if forwarded:
        from .ews import evaluate_and_alert
        await evaluate_and_alert(db, uid, force=True)
    return {"received": len(samples), "new": len(new), "duplicates": len(samples) - len(new), "forwarded_to_vitals": forwarded}


@router.get("/providers")
async def providers():
    return [
        {"id": "health_connect", "name": "Android Health Connect (Samsung, Pixel, Fitbit-on-Google, Garmin and others)", "how": "Phone-side bridge posts to /wearables/ingest with a device key", "status": "supported"},
        {"id": "apple_health", "name": "Apple Health (Apple Watch / iPhone)", "how": "Upload the Health export (export.zip) here, or let an iOS bridge post to /wearables/ingest", "status": "supported"},
        {"id": "google_health", "name": "Google Health API (successor of Fitbit Web API and Google Fit)", "how": "Needs your own Google Cloud OAuth client and Google's verification before real users; not connected in this build", "status": "needs_setup"},
        {"id": "fitbit_web_api", "name": "Fitbit Web API (legacy)", "how": "Shut down on 30 Oct 2026", "status": "retired"},
        {"id": "google_fit", "name": "Google Fit REST API (legacy)", "how": "Retired by Google; use Health Connect", "status": "retired"},
    ]


@router.post("/ingest", status_code=201)
async def ingest(body: IngestIn, authorization: str | None = Header(default=None), x_device_key: str | None = Header(default=None)):
    uid = await _patient(authorization, x_device_key)
    if body.source not in SOURCES:
        raise HTTPException(400, f"source must be one of {sorted(SOURCES)}")
    clean = [c for s in body.samples if (c := W.clean_sample(s.model_dump()))]
    res = await store(get_db(), uid, clean, body.source)
    return {**res, "rejected_invalid": len(body.samples) - len(clean)}


@router.post("/import/apple-health", status_code=201)
async def import_apple(file: UploadFile = File(...), days: int = 30, user: dict = Depends(patient_only)):
    data = await file.read()
    if len(data) > 100 * 1024 * 1024:
        raise HTTPException(413, "File larger than 100 MB. On iPhone, export again after clearing old data, or send only export.xml.")
    days = max(1, min(days, 90))
    try:
        parsed = await asyncio.get_running_loop().run_in_executor(None, lambda: W.parse_apple_health(io.BytesIO(data), days))
    except (ValueError, Exception) as e:  # zip / xml errors
        raise HTTPException(400, f"Could not read the Health export: {str(e)[:150]}")
    db = get_db()
    res = await store(db, user["id"], parsed["samples"], "apple_health")
    await log_event(db, user["id"], "wearable", f"Imported Apple Health data ({res['new']} new readings, last {days} days)")
    return {**res, "records_seen": parsed["records_seen"], "skipped_invalid": parsed["skipped_invalid"], "truncated": parsed["truncated"]}


@router.get("/summary")
async def summary(days: int = 7, user: dict = Depends(patient_only)):
    days = max(1, min(days, 90))
    db = get_db()
    since = (datetime.now(timezone.utc) - timedelta(days=days + 1)).isoformat()
    rows = await db.wearable_samples.find({"user_id": user["id"], "ts": {"$gte": since}}, {"_id": 0, "k": 0}).to_list(200000)
    daily = W.daily_summary(rows, ZoneInfo(settings.APP_TZ))[-days:]
    latest_hr = max((r for r in rows if r["type"] == "heart_rate"), key=lambda r: r["ts"], default=None)
    sources = sorted({r["source"] for r in rows})
    done = [d for d in daily if d["steps"] or d["sleep_hours"]]
    return {"daily": daily, "latest_heart_rate": {"bpm": latest_hr["value"], "ts": latest_hr["ts"]} if latest_hr else None, "sources": sources,
            "averages": {"steps": round(sum(d["steps"] for d in done) / len(done)) if done else None,
                         "sleep_hours": round(sum(d["sleep_hours"] for d in done if d["sleep_hours"]) / max(len([d for d in done if d["sleep_hours"]]), 1), 1) if done else None},
            "has_data": bool(rows)}


@router.delete("/data")
async def delete_data(user: dict = Depends(patient_only)):
    r = await get_db().wearable_samples.delete_many({"user_id": user["id"]})
    return {"deleted": r.deleted_count}
