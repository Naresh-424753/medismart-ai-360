import asyncio
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ..access import can_access
from ..common import log_event, new_id, notify, now
from ..db import get_db
from ..deps import current_user, require_roles, user_from_token
from ..security import hash_key
from ..services import vitals_rules

router = APIRouter(prefix="/vitals", tags=["iot vitals"])
patient_only = require_roles("patient")


class VitalsIn(BaseModel):
    heart_rate: float | None = Field(default=None, ge=20, le=250)
    spo2: float | None = Field(default=None, ge=50, le=100)
    temperature: float | None = Field(default=None, ge=30, le=45)  # Celsius
    systolic: float | None = Field(default=None, ge=50, le=300)
    diastolic: float | None = Field(default=None, ge=30, le=200)
    respiratory_rate: float | None = Field(default=None, ge=4, le=60)
    glucose: float | None = Field(default=None, ge=20, le=700)
    ecg: list[float] | None = Field(default=None, max_length=1000)  # raw samples, optional
    steps: int | None = Field(default=None, ge=0, le=200000)
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    fall_detected: bool = False


class DeviceIn(BaseModel):
    label: str = "ESP32 wearable"


class Hub:
    """Fan-out of live vitals to connected WebSocket viewers, keyed by patient user id."""

    def __init__(self):
        self.rooms: dict[str, set] = {}

    async def join(self, pid: str, ws: WebSocket):
        self.rooms.setdefault(pid, set()).add(ws)

    def leave(self, pid: str, ws: WebSocket):
        self.rooms.get(pid, set()).discard(ws)

    async def publish(self, pid: str, msg: dict):
        for ws in list(self.rooms.get(pid, ())):
            try:
                await ws.send_json(msg)
            except Exception:
                self.leave(pid, ws)


hub = Hub()
_last_alert: dict[tuple, float] = {}
ALERT_COOLDOWN_S = 300


async def process_reading(db, patient_id: str, data: dict, source: str) -> dict:
    ev = {k: v for k, v in data.items() if v is not None}
    alerts = vitals_rules.evaluate(ev)
    status = vitals_rules.overall(alerts)
    doc = {"id": new_id(), "patient_id": patient_id, **{k: v for k, v in ev.items() if k != "ecg"}, "ecg": ev.get("ecg"), "status": status, "source": source, "ts": now()}
    await db.vitals.insert_one(dict(doc))
    doc.pop("_id", None)
    fresh = []
    for a in alerts:
        key = (patient_id, a["metric"], a["severity"])
        if time.time() - _last_alert.get(key, 0) > ALERT_COOLDOWN_S:
            _last_alert[key] = time.time()
            fresh.append(a)
    if fresh:
        user = await db.users.find_one({"id": patient_id})
        crit = [a for a in fresh if a["severity"] == "critical"]
        await db.vital_alerts.insert_many([{"id": new_id(), "patient_id": patient_id, **a, "ts": doc["ts"]} for a in fresh])
        await notify(db, user, "Health alert", "; ".join(a["message"] for a in fresh), "vital_alert", ("app", "sms") if crit else ("app",))
        await log_event(db, patient_id, "vital_alert", "; ".join(a["message"] for a in fresh))
        if crit:
            prof = await db.patients.find_one({"user_id": patient_id}) or {}
            for c in prof.get("emergency_contacts", []):
                await notify(db, None, "Patient health alert", f"{user['name']}: " + "; ".join(a["message"] for a in crit), "vital_alert", ("sms", "whatsapp"), email=c.get("email"), phone=c.get("phone"))
        if any(a["metric"] == "fall" for a in fresh):
            from .emergency import create_alert
            await create_alert(db, user, "fall", None, None, "Automatic fall detection from wearable")
    msg = {"type": "vitals", "reading": {k: v for k, v in doc.items() if k != "ecg"}, "alerts": alerts, "ecg": ev.get("ecg")}
    await hub.publish(patient_id, msg)
    from .ews import evaluate_and_alert  # deterioration forecast; throttled and never raises
    await evaluate_and_alert(db, patient_id)
    return {"status": status, "alerts": alerts}


@router.post("/devices", status_code=201)
async def register_device(body: DeviceIn, user: dict = Depends(patient_only)):
    """Returns the API key ONCE - flash it into the ESP32 firmware. Only its hash is stored."""
    key = "msk_" + secrets.token_urlsafe(24)
    did = new_id()
    await get_db().devices.insert_one({"id": did, "user_id": user["id"], "label": body.label[:60], "key_hash": hash_key(key), "created_at": now(), "last_seen": None})
    return {"device_id": did, "api_key": key, "note": "Store this key now; it cannot be shown again."}


@router.get("/devices")
async def list_devices(user: dict = Depends(patient_only)):
    return await get_db().devices.find({"user_id": user["id"]}, {"_id": 0, "key_hash": 0}).to_list(20)


@router.delete("/devices/{did}")
async def delete_device(did: str, user: dict = Depends(patient_only)):
    await get_db().devices.delete_one({"id": did, "user_id": user["id"]})
    return {"deleted": did}


@router.post("/ingest")
async def ingest(body: VitalsIn, x_device_key: str = Header(default="")):
    """Endpoint for ESP32 devices. Auth via X-Device-Key header."""
    db = get_db()
    dev = await db.devices.find_one({"key_hash": hash_key(x_device_key)}) if x_device_key else None
    if not dev:
        raise HTTPException(401, "Invalid device key")
    await db.devices.update_one({"id": dev["id"]}, {"$set": {"last_seen": now()}})
    return await process_reading(db, dev["user_id"], body.model_dump(), "device")


@router.post("/manual")
async def manual(body: VitalsIn, user: dict = Depends(patient_only)):
    return await process_reading(get_db(), user["id"], body.model_dump(), "manual")


@router.get("/latest")
async def latest(patient_id: str | None = None, user: dict = Depends(current_user)):
    db = get_db()
    pid = patient_id or user["id"]
    if not await can_access(db, user, pid, "vitals"):
        raise HTTPException(403, "No access to this patient's vitals")
    docs = await db.vitals.find({"patient_id": pid}, {"_id": 0, "ecg": 0}).sort("ts", -1).limit(1).to_list(1)
    return docs[0] if docs else None


@router.get("/history")
async def history(hours: int = Query(24, ge=1, le=24 * 90), limit: int = Query(500, ge=1, le=5000), patient_id: str | None = None, user: dict = Depends(current_user)):
    db = get_db()
    pid = patient_id or user["id"]
    if not await can_access(db, user, pid, "vitals"):
        raise HTTPException(403, "No access to this patient's vitals")
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
    docs = await db.vitals.find({"patient_id": pid, "ts": {"$gte": since}}, {"_id": 0, "ecg": 0}).sort("ts", -1).limit(limit).to_list(limit)
    return list(reversed(docs))


@router.get("/alerts")
async def alerts(patient_id: str | None = None, user: dict = Depends(current_user)):
    db = get_db()
    pid = patient_id or user["id"]
    if not await can_access(db, user, pid, "vitals"):
        raise HTTPException(403, "No access")
    return await db.vital_alerts.find({"patient_id": pid}, {"_id": 0}).sort("ts", -1).limit(100).to_list(100)


@router.websocket("/ws")
async def ws_vitals(ws: WebSocket, token: str, patient_id: str | None = None):
    """Live stream. Browsers can't set headers on WebSockets, so the JWT is passed as ?token=."""
    db = get_db()
    try:
        user = await user_from_token(token)
        pid = patient_id or user["id"]
        if not await can_access(db, user, pid, "vitals"):
            raise HTTPException(403)
    except HTTPException:
        await ws.close(code=4401)
        return
    await ws.accept()
    await hub.join(pid, ws)
    try:
        while True:
            await ws.receive_text()  # keep-alive pings from the client
    except WebSocketDisconnect:
        pass
    finally:
        hub.leave(pid, ws)
