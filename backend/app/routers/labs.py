from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..common import log_event, new_id, notify, now
from ..db import get_db
from ..deps import current_user, require_roles
from ..services import report_analyzer as ra

router = APIRouter(prefix="/labs", tags=["laboratory"])
patient_only = require_roles("patient")
lab_only = require_roles("lab")

CATALOG = [
    {"id": "cbc", "name": "Complete Blood Count (CBC)", "price": 350, "type": "blood"},
    {"id": "lft", "name": "Liver Function Test (LFT)", "price": 600, "type": "blood"},
    {"id": "kft", "name": "Kidney Function Test (KFT)", "price": 650, "type": "blood"},
    {"id": "lipid", "name": "Lipid Profile", "price": 500, "type": "blood"},
    {"id": "thyroid", "name": "Thyroid Profile (T3, T4, TSH)", "price": 550, "type": "blood"},
    {"id": "sugar", "name": "Fasting Sugar + HbA1c", "price": 450, "type": "blood"},
    {"id": "vitd", "name": "Vitamin D", "price": 900, "type": "blood"},
    {"id": "b12", "name": "Vitamin B12", "price": 800, "type": "blood"},
    {"id": "urine", "name": "Urine Routine", "price": 150, "type": "urine"},
    {"id": "pkg_basic", "name": "Basic Health Package (CBC, Sugar, Lipid, LFT, KFT)", "price": 1799, "type": "package"},
    {"id": "pkg_senior", "name": "Senior Citizen Package", "price": 2999, "type": "package"},
]
STATUS_FLOW = ["booked", "sample_collected", "processing", "completed"]


class BookIn(BaseModel):
    test_ids: list[str] = Field(min_length=1)
    home_collection: bool = False
    address: str = ""
    slot: str = ""  # free text e.g. "2026-11-02 08:00-10:00"


class ResultIn(BaseModel):
    text: str = ""
    values: dict[str, float] = {}


@router.get("/catalog")
async def catalog(user: dict = Depends(current_user)):
    return CATALOG


@router.post("/bookings", status_code=201)
async def book(body: BookIn, user: dict = Depends(patient_only)):
    tests = [t for t in CATALOG if t["id"] in body.test_ids]
    if len(tests) != len(set(body.test_ids)):
        raise HTTPException(400, "Unknown test id")
    if body.home_collection and not body.address.strip():
        raise HTTPException(400, "Address is required for home collection")
    total = sum(t["price"] for t in tests) + (100 if body.home_collection else 0)
    doc = {"id": new_id(), "user_id": user["id"], "patient_name": user["name"], "tests": [{"id": t["id"], "name": t["name"]} for t in tests], "home_collection": body.home_collection,
           "address": body.address[:300], "slot": body.slot[:60], "total": total, "status": "booked", "verified": False, "report_id": None, "created_at": now()}
    db = get_db()
    await db.lab_bookings.insert_one(dict(doc))
    await log_event(db, user["id"], "lab", f"Booked lab tests: {', '.join(t['name'] for t in tests)}")
    doc.pop("_id", None)
    return doc


@router.get("/bookings")
async def list_bookings(status: str | None = None, user: dict = Depends(current_user)):
    q = {"user_id": user["id"]} if user["role"] == "patient" else {} if user["role"] in ("lab", "admin", "super_admin") else None
    if q is None:
        raise HTTPException(403, "Not available for your role")
    if status:
        q["status"] = status
    return await get_db().lab_bookings.find(q, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)


@router.patch("/bookings/{bid}/status")
async def set_status(bid: str, status: str, user: dict = Depends(lab_only)):
    if status not in STATUS_FLOW:
        raise HTTPException(400, f"status must be one of {STATUS_FLOW}")
    db = get_db()
    b = await db.lab_bookings.find_one({"id": bid})
    if not b:
        raise HTTPException(404, "Booking not found")
    if STATUS_FLOW.index(status) < STATUS_FLOW.index(b["status"]):
        raise HTTPException(400, "Cannot move a booking backwards")
    await db.lab_bookings.update_one({"id": bid}, {"$set": {"status": status}})
    await notify(db, await db.users.find_one({"id": b["user_id"]}), "Lab update", f"Your lab booking is now: {status.replace('_', ' ')}", "lab")
    return {"id": bid, "status": status}


@router.post("/bookings/{bid}/result")
async def upload_result(bid: str, body: ResultIn, user: dict = Depends(lab_only)):
    """Technician enters results; they're interpreted and stored in the patient's reports (marked unverified until a lab verifier signs off)."""
    db = get_db()
    b = await db.lab_bookings.find_one({"id": bid})
    if not b:
        raise HTTPException(404, "Booking not found")
    values = {k: v for k, v in body.values.items() if k in ra.REFS}
    if body.text.strip():
        values = {**ra.extract_values(body.text), **values}
    if not values:
        raise HTTPException(422, "No recognisable values")
    prof = await db.patients.find_one({"user_id": b["user_id"]}) or {}
    res = ra.analyze(values, prof.get("sex"))
    rid = new_id()
    await db.reports.insert_one({"id": rid, "user_id": b["user_id"], "title": "Lab: " + ", ".join(t["name"] for t in b["tests"]), "report_date": now()[:10], "source": "lab", "lab_verified": False,
                                 "categories": ra.detect_categories(values), "values": values, "findings": res["findings"], "summary": res["summary"], "abnormal_count": res["abnormal_count"], "comparison": [], "ts": now()})
    await db.lab_bookings.update_one({"id": bid}, {"$set": {"status": "completed", "report_id": rid}})
    return {"report_id": rid, "summary": res["summary"]}


@router.post("/bookings/{bid}/verify")
async def verify(bid: str, user: dict = Depends(lab_only)):
    db = get_db()
    b = await db.lab_bookings.find_one({"id": bid})
    if not b or not b.get("report_id"):
        raise HTTPException(400, "Upload results first")
    if b.get("verified"):
        return {"already": True}
    await db.lab_bookings.update_one({"id": bid}, {"$set": {"verified": True, "verified_by": user["name"], "verified_at": now()}})
    await db.reports.update_one({"id": b["report_id"]}, {"$set": {"lab_verified": True, "verified_by": user["name"]}})
    pu = await db.users.find_one({"id": b["user_id"]})
    rep = await db.reports.find_one({"id": b["report_id"]})
    await notify(db, pu, "Lab report ready", f"Your report is ready. {rep['summary']}", "lab", ("app", "email", "sms"))
    return {"verified": True}


@router.get("/analytics")
async def lab_analytics(user: dict = Depends(lab_only)):
    db = get_db()
    bs = await db.lab_bookings.find({}, {"_id": 0}).to_list(5000)
    by_test: dict = {}
    for b in bs:
        for t in b["tests"]:
            by_test[t["name"]] = by_test.get(t["name"], 0) + 1
    reps = await db.reports.find({"source": "lab"}, {"_id": 0}).to_list(5000)
    abn: dict = {}
    for r in reps:
        for f in r["findings"]:
            if f["status"] != "normal":
                abn[f["test"]] = abn.get(f["test"], 0) + 1
    return {"bookings": len(bs), "by_status": {s: sum(1 for b in bs if b["status"] == s) for s in STATUS_FLOW}, "most_booked": sorted(by_test.items(), key=lambda x: -x[1])[:5],
            "most_abnormal": sorted(abn.items(), key=lambda x: -x[1])[:5], "revenue": sum(b["total"] for b in bs)}
