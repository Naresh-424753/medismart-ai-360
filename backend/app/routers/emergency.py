from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..common import audit, haversine_km, log_event, new_id, notify, now
from ..db import get_db
from ..deps import current_user, require_roles

router = APIRouter(prefix="/emergency", tags=["emergency"])

DIRECTORY = [
    {"name": "National Emergency Number", "number": "112"}, {"name": "Ambulance (emergency)", "number": "108"},
    {"name": "Ambulance (patient transport)", "number": "102"}, {"name": "Police", "number": "100"}, {"name": "Fire", "number": "101"},
    {"name": "Women helpline", "number": "1091"}, {"name": "Tele-MANAS mental health helpline", "number": "14416"},
]
STATUSES = ["open", "accepted", "en_route", "arrived", "transporting", "completed", "cancelled"]
AVG_KMH = 35


class SOSIn(BaseModel):
    type: str = "sos"  # sos | ambulance | accident
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    message: str = ""


class LocIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


def _rank(hospitals: list[dict], lat: float, lon: float, need_emergency=True) -> list[dict]:
    out = []
    for h in hospitals:
        d = haversine_km(lat, lon, h["lat"], h["lon"])
        beds = h.get("beds", {})
        avail = beds.get("emergency", {}).get("available", 0)
        out.append({**{k: h[k] for k in ("id", "name", "phone", "address", "city", "lat", "lon")}, "distance_km": round(d, 1), "eta_min": round(d / AVG_KMH * 60 + 2),
                    "emergency_beds": avail, "icu_beds": beds.get("icu", {}).get("available", 0), "has_emergency": avail > 0})
    # prefer hospitals with emergency capacity, then nearest
    out.sort(key=lambda x: (0 if x["has_emergency"] or not need_emergency else 1, x["distance_km"]))
    return out


async def create_alert(db, user: dict, kind: str, lat, lon, message: str) -> dict:
    prof = await db.patients.find_one({"user_id": user["id"]}, {"_id": 0}) or {}
    hospital = None
    if lat is not None and lon is not None:
        ranked = _rank(await db.hospitals.find({}, {"_id": 0}).to_list(500), lat, lon)
        hospital = ranked[0] if ranked else None
    alert = {"id": new_id(), "user_id": user["id"], "patient_name": user["name"], "phone": user.get("phone", ""), "type": kind, "lat": lat, "lon": lon, "message": message[:500],
             "status": "open", "blood_group": prof.get("blood_group"), "allergies": [a["name"] for a in prof.get("allergies", [])],
             "conditions": [d["name"] for d in prof.get("diseases", [])], "hospital": hospital, "ambulance": None, "ambulance_loc": None, "created_at": now(), "history": [{"status": "open", "ts": now()}]}
    await db.emergency_alerts.insert_one(dict(alert))
    loc = f"https://www.google.com/maps?q={lat},{lon}" if lat is not None else "location unavailable"
    body = f"EMERGENCY: {user['name']} needs help ({kind}). Location: {loc}. Blood group: {prof.get('blood_group') or 'unknown'}."
    for c in prof.get("emergency_contacts", []):
        await notify(db, None, "Emergency alert", body, "emergency", ("sms", "whatsapp", "email"), email=c.get("email"), phone=c.get("phone"))
    for amb in await db.users.find({"role": "ambulance", "approved": True}).to_list(100):
        await notify(db, amb, "New emergency request", body, "emergency")
    await log_event(db, user["id"], "emergency", f"{kind.upper()} raised", {"alert_id": alert["id"]})
    await audit(db, user["id"], "sos", kind)
    alert.pop("_id", None)
    return alert


@router.get("/directory")
async def directory(user: dict = Depends(current_user)):
    return DIRECTORY


@router.post("/sos", status_code=201)
async def sos(body: SOSIn, user: dict = Depends(require_roles("patient", "family"))):
    if body.type not in ("sos", "ambulance", "accident"):
        raise HTTPException(400, "type must be sos, ambulance or accident")
    return await create_alert(get_db(), user, body.type, body.lat, body.lon, body.message)


@router.get("/hospitals/nearby")
async def nearby(lat: float, lon: float, emergency_only: bool = False, user: dict = Depends(current_user)):
    ranked = _rank(await get_db().hospitals.find({}, {"_id": 0}).to_list(500), lat, lon, need_emergency=False)
    return [h for h in ranked if h["has_emergency"]] if emergency_only else ranked


@router.get("/route-suggestion")
async def route_suggestion(lat: float, lon: float, user: dict = Depends(current_user)):
    """Smart ambulance routing: nearest hospital that actually has emergency capacity. Straight-line distance/ETA estimate - plug in a routing API for road ETAs."""
    ranked = _rank(await get_db().hospitals.find({}, {"_id": 0}).to_list(500), lat, lon)
    return {"recommended": ranked[0] if ranked else None, "alternatives": ranked[1:4], "note": "ETA is estimated from straight-line distance."}


@router.get("/alerts")
async def alerts(status: str | None = None, user: dict = Depends(current_user)):
    db = get_db()
    q: dict = {}
    if user["role"] in ("patient", "family"):
        q["user_id"] = user["id"]
    elif user["role"] == "ambulance":
        q["$or"] = [{"status": "open"}, {"ambulance.user_id": user["id"]}]
    elif user["role"] not in ("super_admin", "admin", "hospital"):
        raise HTTPException(403, "Not available for your role")
    if status:
        q["status"] = status
    return await db.emergency_alerts.find(q, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)


@router.get("/alerts/{aid}")
async def alert_detail(aid: str, user: dict = Depends(current_user)):
    a = await get_db().emergency_alerts.find_one({"id": aid}, {"_id": 0})
    if not a or (user["role"] in ("patient", "family") and a["user_id"] != user["id"]):
        raise HTTPException(404, "Alert not found")
    return a


@router.patch("/alerts/{aid}")
async def update_alert(aid: str, status: str, user: dict = Depends(current_user)):
    db = get_db()
    a = await db.emergency_alerts.find_one({"id": aid})
    if not a:
        raise HTTPException(404, "Alert not found")
    if status not in STATUSES:
        raise HTTPException(400, f"status must be one of {STATUSES}")
    is_owner = a["user_id"] == user["id"]
    is_amb = user["role"] == "ambulance" and user.get("approved")
    if status == "cancelled" and is_owner:
        pass
    elif is_amb or user["role"] in ("super_admin", "admin"):
        if status == "accepted":
            if a["status"] != "open":
                raise HTTPException(409, "Already accepted by another ambulance")
            await db.emergency_alerts.update_one({"id": aid}, {"$set": {"ambulance": {"user_id": user["id"], "name": user["name"], "phone": user.get("phone", "")}}})
        elif a.get("ambulance", {}) and a["ambulance"]["user_id"] != user["id"] and user["role"] == "ambulance":
            raise HTTPException(403, "This request is assigned to another ambulance")
    else:
        raise HTTPException(403, "Not allowed")
    await db.emergency_alerts.update_one({"id": aid}, {"$set": {"status": status}, "$push": {"history": {"status": status, "ts": now()}}})
    await notify(db, await db.users.find_one({"id": a["user_id"]}), "Emergency update", f"Status: {status.replace('_', ' ')}", "emergency")
    return {"id": aid, "status": status}


@router.post("/alerts/{aid}/location")
async def ambulance_location(aid: str, body: LocIn, user: dict = Depends(require_roles("ambulance"))):
    db = get_db()
    a = await db.emergency_alerts.find_one({"id": aid})
    if not a or not a.get("ambulance") or a["ambulance"]["user_id"] != user["id"]:
        raise HTTPException(403, "Not your request")
    eta = None
    if a.get("lat") is not None:
        eta = round(haversine_km(body.lat, body.lon, a["lat"], a["lon"]) / AVG_KMH * 60 + 1)
    await db.emergency_alerts.update_one({"id": aid}, {"$set": {"ambulance_loc": {"lat": body.lat, "lon": body.lon, "ts": now(), "eta_min": eta}}})
    return {"ok": True, "eta_min": eta}


# ---- public offline-friendly emergency card (via QR token) ----
public = APIRouter(prefix="/public", tags=["public"])


@public.get("/emergency-card/{qr_token}")
async def emergency_card(qr_token: str):
    """Minimal data a first responder needs. The unguessable token is only in the patient's QR code."""
    db = get_db()
    p = await db.patients.find_one({"qr_token": qr_token}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Card not found")
    u = await db.users.find_one({"id": p["user_id"]})
    await audit(db, None, "emergency_card_view", p["health_id"])
    return {"name": u["name"], "health_id": p["health_id"], "blood_group": p.get("blood_group"), "sex": p.get("sex"), "dob": p.get("dob"),
            "allergies": [a["name"] for a in p.get("allergies", [])], "conditions": [d["name"] for d in p.get("diseases", [])],
            "emergency_contacts": [{"name": c["name"], "relation": c.get("relation"), "phone": c.get("phone")} for c in p.get("emergency_contacts", [])]}
