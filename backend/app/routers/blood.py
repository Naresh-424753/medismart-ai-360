from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..common import new_id, notify, now, today
from ..db import get_db
from ..deps import current_user, require_roles

router = APIRouter(prefix="/blood", tags=["blood bank"])
BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
# recipient -> groups that can donate to them (red cells)
COMPATIBLE = {"A+": ["A+", "A-", "O+", "O-"], "A-": ["A-", "O-"], "B+": ["B+", "B-", "O+", "O-"], "B-": ["B-", "O-"],
              "AB+": BLOOD_GROUPS, "AB-": ["A-", "B-", "AB-", "O-"], "O+": ["O+", "O-"], "O-": ["O-"]}
MIN_GAP_DAYS = 90


class DonorIn(BaseModel):
    blood_group: str
    city: str
    last_donation: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    available: bool = True


class RequestIn(BaseModel):
    blood_group: str
    units: int = Field(default=1, ge=1, le=20)
    city: str
    hospital: str = ""
    urgency: str = "urgent"  # urgent | critical | planned
    contact_phone: str = ""


class StockIn(BaseModel):
    blood_group: str
    units: int = Field(ge=0, le=100000)
    expiry: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class CampIn(BaseModel):
    title: str
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    venue: str
    city: str


def eligible(d: dict) -> bool:
    if not d.get("available"):
        return False
    if d.get("last_donation"):
        gap = (datetime.now() - datetime.strptime(d["last_donation"], "%Y-%m-%d")).days
        return gap >= MIN_GAP_DAYS
    return True


@router.post("/donors", status_code=201)
async def register_donor(body: DonorIn, user: dict = Depends(current_user)):
    if body.blood_group not in BLOOD_GROUPS:
        raise HTTPException(400, f"blood_group must be one of {BLOOD_GROUPS}")
    db = get_db()
    doc = {"user_id": user["id"], "name": user["name"], **body.model_dump(), "updated_at": now()}
    await db.donors.update_one({"user_id": user["id"]}, {"$set": doc, "$setOnInsert": {"id": new_id(), "donations": []}}, upsert=True)
    d = await db.donors.find_one({"user_id": user["id"]}, {"_id": 0})
    return {**d, "eligible_now": eligible(d)}


@router.get("/donors/me")
async def my_donor(user: dict = Depends(current_user)):
    d = await get_db().donors.find_one({"user_id": user["id"]}, {"_id": 0})
    return {**d, "eligible_now": eligible(d)} if d else None


@router.post("/donors/me/donated")
async def record_donation(where: str = "", user: dict = Depends(current_user)):
    db = get_db()
    d = await db.donors.find_one({"user_id": user["id"]})
    if not d:
        raise HTTPException(404, "Register as a donor first")
    await db.donors.update_one({"user_id": user["id"]}, {"$set": {"last_donation": today()}, "$push": {"donations": {"date": today(), "where": where[:100]}}})
    return {"ok": True, "next_eligible": (datetime.now() + timedelta(days=MIN_GAP_DAYS)).strftime("%Y-%m-%d")}


@router.get("/donors/search")
async def search_donors(blood_group: str, city: str, user: dict = Depends(current_user)):
    """Contact details are NOT exposed - use a blood request so donors can opt in to share them."""
    ds = await get_db().donors.find({"blood_group": {"$in": COMPATIBLE.get(blood_group, [blood_group])}, "city": {"$regex": f"^{city}$", "$options": "i"}}, {"_id": 0}).to_list(500)
    return [{"blood_group": d["blood_group"], "city": d["city"], "eligible_now": eligible(d), "name": d["name"].split()[0]} for d in ds if eligible(d)]


@router.post("/requests", status_code=201)
async def blood_request(body: RequestIn, user: dict = Depends(current_user)):
    if body.blood_group not in BLOOD_GROUPS:
        raise HTTPException(400, "Invalid blood group")
    db = get_db()
    doc = {"id": new_id(), "requester_id": user["id"], "requester_name": user["name"], **body.model_dump(), "contact_phone": body.contact_phone or user.get("phone", ""), "status": "open", "responders": [], "created_at": now()}
    await db.blood_requests.insert_one(dict(doc))
    notified = 0
    async for d in db.donors.find({"blood_group": {"$in": COMPATIBLE[body.blood_group]}, "city": {"$regex": f"^{body.city}$", "$options": "i"}}):
        if d["user_id"] != user["id"] and eligible(d):
            u = await db.users.find_one({"id": d["user_id"]})
            await notify(db, u, f"{body.urgency.upper()}: {body.blood_group} blood needed", f"{body.units} unit(s) needed in {body.city} {('at ' + body.hospital) if body.hospital else ''}. Open Blood Bank to respond.", "blood_request", ("app", "sms", "whatsapp"))
            notified += 1
    for bank in await db.users.find({"role": "blood_bank", "approved": True}).to_list(50):
        await notify(db, bank, "Blood request", f"{body.blood_group} x{body.units} in {body.city}", "blood_request")
    doc.pop("_id", None)
    return {**doc, "donors_notified": notified}


@router.get("/requests")
async def list_requests(mine: bool = False, user: dict = Depends(current_user)):
    db = get_db()
    q = {"requester_id": user["id"]} if mine else {"status": "open"}
    docs = await db.blood_requests.find(q, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)
    for d in docs:
        if d["requester_id"] != user["id"]:
            d.pop("contact_phone", None)
            d["responders"] = []
    return docs


@router.post("/requests/{rid}/respond")
async def respond(rid: str, user: dict = Depends(current_user)):
    """A donor opts in. The requester gets the donor's phone; the donor gets the requester's contact."""
    db = get_db()
    r = await db.blood_requests.find_one({"id": rid})
    d = await db.donors.find_one({"user_id": user["id"]})
    if not r or r["status"] != "open":
        raise HTTPException(404, "Request not open")
    if not d or not eligible(d) or d["blood_group"] not in COMPATIBLE[r["blood_group"]]:
        raise HTTPException(403, "You are not an eligible compatible donor for this request")
    if any(x["user_id"] == user["id"] for x in r["responders"]):
        return {"already": True, "contact_phone": r["contact_phone"]}
    await db.blood_requests.update_one({"id": rid}, {"$push": {"responders": {"user_id": user["id"], "name": user["name"], "phone": user.get("phone", ""), "ts": now()}}})
    await notify(db, await db.users.find_one({"id": r["requester_id"]}), "A donor can help", f"{user['name']} ({d['blood_group']}) offered to donate. Phone: {user.get('phone') or 'not provided'}", "blood_request", ("app", "sms"))
    return {"contact_phone": r["contact_phone"], "requester": r["requester_name"], "hospital": r["hospital"]}


@router.patch("/requests/{rid}/close")
async def close(rid: str, user: dict = Depends(current_user)):
    await get_db().blood_requests.update_one({"id": rid, "requester_id": user["id"]}, {"$set": {"status": "closed"}})
    return {"closed": rid}


# ---- blood bank portal ----
bank_only = require_roles("blood_bank")


@router.get("/stock")
async def stock(blood_group: str | None = None, city: str | None = None, user: dict = Depends(current_user)):
    q: dict = {}
    if blood_group:
        q["blood_group"] = blood_group
    if city:
        q["city"] = {"$regex": f"^{city}$", "$options": "i"}
    rows = await get_db().blood_stock.find(q, {"_id": 0}).to_list(1000)
    t = today()
    return [{**r, "expired": bool(r.get("expiry") and r["expiry"] < t)} for r in rows]


@router.put("/stock")
async def set_stock(body: StockIn, user: dict = Depends(bank_only)):
    if body.blood_group not in BLOOD_GROUPS:
        raise HTTPException(400, "Invalid blood group")
    u = user
    await get_db().blood_stock.update_one({"bank_id": u["id"], "blood_group": body.blood_group},
                                          {"$set": {"bank_id": u["id"], "bank_name": u.get("organization") or u["name"], "city": u.get("city", ""), "phone": u.get("phone", ""), "units": body.units, "expiry": body.expiry, "updated_at": now()}}, upsert=True)
    return {"ok": True}


@router.get("/stock/mine")
async def my_stock(user: dict = Depends(bank_only)):
    rows = await get_db().blood_stock.find({"bank_id": user["id"]}, {"_id": 0}).to_list(20)
    soon = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    return {"stock": rows, "expiring_soon": [r for r in rows if r.get("expiry") and r["expiry"] <= soon], "low": [r for r in rows if r["units"] <= 5]}


@router.post("/camps", status_code=201)
async def create_camp(body: CampIn, user: dict = Depends(bank_only)):
    doc = {"id": new_id(), "bank_id": user["id"], "bank_name": user.get("organization") or user["name"], **body.model_dump(), "registrations": 0, "created_at": now()}
    await get_db().blood_camps.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.get("/camps")
async def camps(city: str | None = None, user: dict = Depends(current_user)):
    q = {"date": {"$gte": today()}}
    if city:
        q["city"] = {"$regex": f"^{city}$", "$options": "i"}
    return await get_db().blood_camps.find(q, {"_id": 0}).sort("date", 1).to_list(100)


@router.post("/camps/{cid}/register")
async def register_camp(cid: str, user: dict = Depends(current_user)):
    db = get_db()
    if await db.camp_regs.find_one({"camp_id": cid, "user_id": user["id"]}):
        return {"already": True}
    await db.camp_regs.insert_one({"camp_id": cid, "user_id": user["id"], "ts": now()})
    await db.blood_camps.update_one({"id": cid}, {"$inc": {"registrations": 1}})
    return {"registered": True}
