from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

from ..common import log_event, new_id, notify, now, today
from ..db import get_db
from ..deps import current_user, require_roles

router = APIRouter(prefix="/hospitals", tags=["hospitals"])
hospital_only = require_roles("hospital")
patient_only = require_roles("patient")

BED_TYPES = ["general", "icu", "emergency", "ventilator"]


class BedsIn(BaseModel):
    general: tuple[int, int] | None = None  # (total, available)
    icu: tuple[int, int] | None = None
    emergency: tuple[int, int] | None = None
    ventilator: tuple[int, int] | None = None


class AdmitIn(BaseModel):
    patient_name: str
    health_id: str | None = None
    ward: str = "general"
    doctor: str = ""
    reason: str = ""


class BillIn(BaseModel):
    patient_name: str
    items: list[dict]
    admission_id: str | None = None


class TokenIn(BaseModel):
    department: str = "OPD"


def _view(h: dict) -> dict:
    return {k: h.get(k) for k in ("id", "name", "address", "city", "phone", "lat", "lon", "departments", "beds", "specialities", "rating", "verified")}


async def _my_hospital(db, user) -> dict:
    h = await db.hospitals.find_one({"user_id": user["id"]}, {"_id": 0})
    if not h:  # first login of a hospital account creates its profile
        h = {"id": new_id(), "user_id": user["id"], "name": user.get("organization") or user["name"], "address": "", "city": "", "phone": user.get("phone", ""), "lat": 0.0, "lon": 0.0,
             "departments": ["OPD", "Emergency"], "specialities": [], "rating": 0, "verified": bool(user.get("approved")),
             "beds": {t: {"total": 0, "available": 0} for t in BED_TYPES}}
        await db.hospitals.insert_one(dict(h))
    return h


@router.get("")
async def search(city: str | None = None, q: str | None = None, speciality: str | None = None, min_icu: int = 0, user: dict = Depends(current_user)):
    out = []
    for h in await get_db().hospitals.find({"verified": True}, {"_id": 0}).to_list(500):
        if city and city.lower() not in h.get("city", "").lower():
            continue
        if q and q.lower() not in h["name"].lower():
            continue
        if speciality and not any(speciality.lower() in s.lower() for s in h.get("specialities", [])):
            continue
        if h["beds"]["icu"]["available"] < min_icu:
            continue
        out.append(_view(h))
    return out


@router.get("/compare")
async def compare(ids: str = Query(description="comma separated hospital ids"), user: dict = Depends(current_user)):
    idl = [i for i in ids.split(",") if i][:4]
    hs = await get_db().hospitals.find({"id": {"$in": idl}}, {"_id": 0}).to_list(4)
    return [{**_view(h), "queue_today": await get_db().hospital_tokens.count_documents({"hospital_id": h["id"], "date": today(), "status": "waiting"})} for h in hs]


@router.get("/me")
async def my_hospital(user: dict = Depends(hospital_only)):
    return await _my_hospital(get_db(), user)


@router.put("/me/beds")
async def set_beds(body: BedsIn, user: dict = Depends(hospital_only)):
    db = get_db()
    h = await _my_hospital(db, user)
    upd = {}
    for t, v in body.model_dump(exclude_none=True).items():
        total, avail = v
        if total < 0 or avail < 0 or avail > total:
            raise HTTPException(400, f"{t}: available must be between 0 and total")
        upd[f"beds.{t}"] = {"total": total, "available": avail}
    if upd:
        await db.hospitals.update_one({"id": h["id"]}, {"$set": upd})
    return await _my_hospital(db, user)


class ProfileIn(BaseModel):
    address: str | None = None
    city: str | None = None
    phone: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    departments: list[str] | None = None
    specialities: list[str] | None = None


@router.put("/me")
async def update_profile(body: ProfileIn, user: dict = Depends(hospital_only)):
    db = get_db()
    h = await _my_hospital(db, user)
    d = body.model_dump(exclude_none=True)
    if d:
        await db.hospitals.update_one({"id": h["id"]}, {"$set": d})
    return await _my_hospital(db, user)


@router.post("/me/admissions", status_code=201)
async def admit(body: AdmitIn, user: dict = Depends(hospital_only)):
    db = get_db()
    h = await _my_hospital(db, user)
    ward = body.ward if body.ward in BED_TYPES else "general"
    if h["beds"][ward]["available"] <= 0:
        raise HTTPException(409, f"No {ward} beds available")
    await db.hospitals.update_one({"id": h["id"]}, {"$inc": {f"beds.{ward}.available": -1}})
    doc = {"id": new_id(), "hospital_id": h["id"], **body.model_dump(), "ward": ward, "status": "admitted", "admitted_at": now(), "discharged_at": None}
    await db.admissions.insert_one(dict(doc))
    if body.health_id:
        p = await db.patients.find_one({"health_id": body.health_id})
        if p:
            await log_event(db, p["user_id"], "admission", f"Admitted to {h['name']} ({ward})")
    doc.pop("_id", None)
    return doc


@router.post("/me/admissions/{aid}/discharge")
async def discharge(aid: str, user: dict = Depends(hospital_only)):
    db = get_db()
    h = await _my_hospital(db, user)
    a = await db.admissions.find_one({"id": aid, "hospital_id": h["id"]})
    if not a or a["status"] != "admitted":
        raise HTTPException(404, "Active admission not found")
    await db.admissions.update_one({"id": aid}, {"$set": {"status": "discharged", "discharged_at": now()}})
    await db.hospitals.update_one({"id": h["id"]}, {"$inc": {f"beds.{a['ward']}.available": 1}})
    if a.get("health_id"):
        p = await db.patients.find_one({"health_id": a["health_id"]})
        if p:
            await log_event(db, p["user_id"], "discharge", f"Discharged from {h['name']}")
    return {"discharged": aid}


@router.get("/me/admissions")
async def admissions(status: str | None = None, user: dict = Depends(hospital_only)):
    h = await _my_hospital(get_db(), user)
    q = {"hospital_id": h["id"], **({"status": status} if status else {})}
    return await get_db().admissions.find(q, {"_id": 0}).sort("admitted_at", -1).limit(300).to_list(300)


@router.post("/me/bills", status_code=201)
async def create_bill(body: BillIn, user: dict = Depends(hospital_only)):
    db = get_db()
    h = await _my_hospital(db, user)
    items = [{"name": str(i.get("name", ""))[:80], "amount": float(i.get("amount", 0))} for i in body.items]
    if not items or any(i["amount"] < 0 for i in items):
        raise HTTPException(400, "Provide items with non-negative amounts")
    doc = {"id": new_id(), "hospital_id": h["id"], "patient_name": body.patient_name, "admission_id": body.admission_id, "items": items,
           "total": round(sum(i["amount"] for i in items), 2), "status": "unpaid", "created_at": now()}
    await db.bills.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.get("/me/bills")
async def bills(user: dict = Depends(hospital_only)):
    h = await _my_hospital(get_db(), user)
    return await get_db().bills.find({"hospital_id": h["id"]}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)


@router.patch("/me/bills/{bid}")
async def pay_bill(bid: str, user: dict = Depends(hospital_only)):
    h = await _my_hospital(get_db(), user)
    await get_db().bills.update_one({"id": bid, "hospital_id": h["id"]}, {"$set": {"status": "paid", "paid_at": now()}})
    return {"paid": bid}


@router.get("/me/analytics")
async def analytics(user: dict = Depends(hospital_only)):
    from ..services import analytics as an
    db = get_db()
    h = await _my_hospital(db, user)
    adm = await db.admissions.find({"hospital_id": h["id"]}, {"_id": 0}).to_list(5000)
    daily: dict = {}
    for a in adm:
        daily[a["admitted_at"][:10]] = daily.get(a["admitted_at"][:10], 0) + 1
    series = [daily[k] for k in sorted(daily)]
    total_beds = sum(h["beds"][t]["total"] for t in BED_TYPES)
    free = sum(h["beds"][t]["available"] for t in BED_TYPES)
    return {"admissions_by_day": dict(sorted(daily.items())), "forecast_next_7_days": an.forecast(series, 7), "occupancy_pct": round(100 * (total_beds - free) / total_beds) if total_beds else None,
            "active_admissions": sum(1 for a in adm if a["status"] == "admitted"), "bed_demand_estimate": an.bed_demand(series, 4.0),
            "revenue_total": sum(b["total"] for b in await db.bills.find({"hospital_id": h["id"], "status": "paid"}).to_list(5000))}


# ---- digital OPD token queue ----
@router.post("/{hid}/tokens", status_code=201)
async def take_token(hid: str, body: TokenIn, user: dict = Depends(patient_only)):
    db = get_db()
    h = await db.hospitals.find_one({"id": hid})
    if not h:
        raise HTTPException(404, "Hospital not found")
    if await db.hospital_tokens.find_one({"hospital_id": hid, "user_id": user["id"], "date": today(), "department": body.department, "status": "waiting"}):
        raise HTTPException(409, "You already have a waiting token for this department")
    ctr = await db.counters.find_one_and_update({"key": f"{hid}:{today()}:{body.department}"}, {"$inc": {"n": 1}}, upsert=True, return_document=ReturnDocument.AFTER)
    doc = {"id": new_id(), "hospital_id": hid, "hospital_name": h["name"], "user_id": user["id"], "patient_name": user["name"], "department": body.department, "number": ctr["n"], "date": today(), "status": "waiting", "created_at": now()}
    await db.hospital_tokens.insert_one(dict(doc))
    ahead = await db.hospital_tokens.count_documents({"hospital_id": hid, "date": today(), "department": body.department, "status": "waiting", "number": {"$lt": ctr["n"]}})
    doc.pop("_id", None)
    return {**doc, "people_ahead": ahead, "est_wait_min": ahead * 8}


@router.get("/{hid}/queue")
async def queue(hid: str, department: str = "OPD", user: dict = Depends(current_user)):
    toks = await get_db().hospital_tokens.find({"hospital_id": hid, "date": today(), "department": department}, {"_id": 0}).sort("number", 1).to_list(500)
    waiting = [t for t in toks if t["status"] == "waiting"]
    serving = [t for t in toks if t["status"] == "serving"]
    return {"department": department, "now_serving": serving[-1]["number"] if serving else None, "waiting": len(waiting),
            "tokens": [{"number": t["number"], "status": t["status"], **({"mine": True} if t["user_id"] == user["id"] else {})} for t in toks]}


@router.post("/me/queue/next")
async def call_next(department: str = "OPD", user: dict = Depends(hospital_only)):
    db = get_db()
    h = await _my_hospital(db, user)
    await db.hospital_tokens.update_many({"hospital_id": h["id"], "date": today(), "department": department, "status": "serving"}, {"$set": {"status": "done"}})
    nxt = await db.hospital_tokens.find({"hospital_id": h["id"], "date": today(), "department": department, "status": "waiting"}, {"_id": 0}).sort("number", 1).limit(1).to_list(1)
    if not nxt:
        return {"now_serving": None}
    await db.hospital_tokens.update_one({"id": nxt[0]["id"]}, {"$set": {"status": "serving"}})
    await notify(db, await db.users.find_one({"id": nxt[0]["user_id"]}), "Your turn", f"Token {nxt[0]['number']} - please proceed to {department}.", "queue", ("app", "sms"))
    return {"now_serving": nxt[0]["number"]}
