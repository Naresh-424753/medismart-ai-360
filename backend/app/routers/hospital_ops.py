"""Hospital operations: departments, staff, operation-theatre schedule, inventory, equipment, bed forecast."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..common import new_id, now, today
from ..db import get_db
from ..deps import require_roles
from .hospitals import BED_TYPES, _my_hospital

router = APIRouter(prefix="/hospital-ops", tags=["hospital operations"])
hospital_only = require_roles("hospital")
TIME = r"^\d{2}:\d{2}$"
DATE = r"^\d{4}-\d{2}-\d{2}$"


class StaffIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    role: str = Field(max_length=40)  # nurse, technician, ward boy, admin ...
    department: str = "General"
    phone: str = ""
    shift: str = "day"  # day | evening | night


class TheatreIn(BaseModel):
    theatre: str = Field(max_length=30)
    patient_name: str = Field(max_length=80)
    procedure: str = Field(max_length=120)
    surgeon: str = Field(max_length=80)
    date: str = Field(pattern=DATE)
    start: str = Field(pattern=TIME)
    end: str = Field(pattern=TIME)


class InventoryIn(BaseModel):
    item: str = Field(max_length=80)
    category: str = "medicine"
    quantity: int = Field(ge=0, le=10_000_000)
    unit: str = "units"
    reorder_level: int = Field(default=10, ge=0)
    expiry: str | None = Field(default=None, pattern=DATE)


class EquipmentIn(BaseModel):
    name: str = Field(max_length=80)
    serial_no: str = ""
    department: str = "General"
    status: str = "working"  # working | maintenance | out_of_service
    next_service: str | None = Field(default=None, pattern=DATE)


class DeptIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)


KINDS = {"staff": ("hosp_staff", StaffIn), "inventory": ("hosp_inventory", InventoryIn), "equipment": ("hosp_equipment", EquipmentIn)}


def _kind(kind: str):
    if kind not in KINDS:
        raise HTTPException(404, f"Unknown resource. Use one of {list(KINDS)}")
    return KINDS[kind]


# ---- departments ----
@router.get("/departments")
async def departments(user: dict = Depends(hospital_only)):
    return (await _my_hospital(get_db(), user))["departments"]


@router.post("/departments", status_code=201)
async def add_department(body: DeptIn, user: dict = Depends(hospital_only)):
    db = get_db()
    h = await _my_hospital(db, user)
    if body.name.strip().lower() in [d.lower() for d in h["departments"]]:
        raise HTTPException(409, "Department already exists")
    await db.hospitals.update_one({"id": h["id"]}, {"$push": {"departments": body.name.strip()}})
    return {"departments": h["departments"] + [body.name.strip()]}


@router.delete("/departments/{name}")
async def remove_department(name: str, user: dict = Depends(hospital_only)):
    db = get_db()
    h = await _my_hospital(db, user)
    await db.hospitals.update_one({"id": h["id"]}, {"$pull": {"departments": name}})
    return {"ok": True}


# ---- operation theatre schedule (before the generic /{kind} routes so "theatre" is not captured) ----
@router.get("/theatre")
async def list_theatre(date: str | None = None, user: dict = Depends(hospital_only)):
    h = await _my_hospital(get_db(), user)
    q = {"hospital_id": h["id"], **({"date": date} if date else {})}
    return await get_db().hosp_theatre.find(q, {"_id": 0}).sort([("date", 1), ("start", 1)]).limit(500).to_list(500)


@router.post("/theatre", status_code=201)
async def book_theatre(body: TheatreIn, user: dict = Depends(hospital_only)):
    if body.end <= body.start:
        raise HTTPException(400, "End time must be after start time")
    db = get_db()
    h = await _my_hospital(db, user)
    clash = await db.hosp_theatre.find_one({"hospital_id": h["id"], "theatre": body.theatre, "date": body.date, "status": "scheduled",
                                            "start": {"$lt": body.end}, "end": {"$gt": body.start}})
    if clash:
        raise HTTPException(409, f"{body.theatre} is already booked {clash['start']}-{clash['end']} on {body.date}")
    doc = {"id": new_id(), "hospital_id": h["id"], **body.model_dump(), "status": "scheduled", "created_at": now()}
    await db.hosp_theatre.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.patch("/theatre/{tid}/{action}")
async def theatre_action(tid: str, action: str, user: dict = Depends(hospital_only)):
    if action not in ("complete", "cancel"):
        raise HTTPException(400, "action must be complete or cancel")
    h = await _my_hospital(get_db(), user)
    r = await get_db().hosp_theatre.update_one({"id": tid, "hospital_id": h["id"]}, {"$set": {"status": "completed" if action == "complete" else "cancelled"}})
    if not r.matched_count:
        raise HTTPException(404, "Booking not found")
    return {"ok": True}


# ---- alerts + forecast ----
@router.get("/alerts")
async def ops_alerts(user: dict = Depends(hospital_only)):
    db = get_db()
    h = await _my_hospital(db, user)
    soon = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
    inv = await db.hosp_inventory.find({"hospital_id": h["id"]}, {"_id": 0}).to_list(2000)
    eq = await db.hosp_equipment.find({"hospital_id": h["id"]}, {"_id": 0}).to_list(2000)
    return {"low_stock": [i for i in inv if i["quantity"] <= i["reorder_level"]],
            "expiring_soon": [i for i in inv if i.get("expiry") and i["expiry"] <= soon],
            "equipment_down": [e for e in eq if e["status"] != "working"],
            "service_due": [e for e in eq if e.get("next_service") and e["next_service"] <= soon]}


@router.get("/forecast")
async def forecast(days: int = 7, user: dict = Depends(hospital_only)):
    """Admission trend + bed-demand prediction: 14-day average with weekday pattern, vs. current free beds."""
    days = max(1, min(days, 30))
    db = get_db()
    h = await _my_hospital(db, user)
    since = (datetime.now(timezone.utc) - timedelta(days=28)).isoformat()
    rows = await db.admissions.find({"hospital_id": h["id"], "admitted_at": {"$gte": since}}, {"_id": 0}).to_list(20000)
    per_day: dict = defaultdict(int)
    by_ward: dict = defaultdict(int)
    for r in rows:
        per_day[r["admitted_at"][:10]] += 1
        by_ward[r["ward"]] += 1
    hist = [{"date": (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")} for i in range(27, -1, -1)]
    for x in hist:
        x["admissions"] = per_day.get(x["date"], 0)
    avg = sum(x["admissions"] for x in hist[-14:]) / 14
    wd: dict = defaultdict(list)
    for x in hist:
        wd[datetime.strptime(x["date"], "%Y-%m-%d").weekday()].append(x["admissions"])
    overall = (sum(x["admissions"] for x in hist) / len(hist)) or 1
    fc = []
    for i in range(1, days + 1):
        d = datetime.now(timezone.utc) + timedelta(days=i)
        factor = (sum(wd[d.weekday()]) / max(len(wd[d.weekday()]), 1)) / overall if overall else 1
        fc.append({"date": d.strftime("%Y-%m-%d"), "expected_admissions": round(avg * (0.5 + 0.5 * factor), 1)})
    total_expected = sum(f["expected_admissions"] for f in fc)
    ward_share = {w: n / max(len(rows), 1) for w, n in by_ward.items()}
    beds = {}
    for t in BED_TYPES:
        free = h["beds"][t]["available"]
        need = total_expected * ward_share.get(t, 0)  # ignores discharges: conservative estimate
        beds[t] = {"available_now": free, "expected_new_patients": round(need, 1), "risk": "shortage" if need > free else "ok"}
    return {"history": hist, "forecast": fc, "bed_demand": beds,
            "note": "Simple moving-average + weekday pattern forecast from your last 28 days; it ignores discharges and seasonality."}


# ---- generic resources: staff, inventory, equipment ----
@router.get("/{kind}")
async def list_items(kind: str, user: dict = Depends(hospital_only)):
    coll, _ = _kind(kind)
    h = await _my_hospital(get_db(), user)
    return await get_db()[coll].find({"hospital_id": h["id"]}, {"_id": 0}).sort("created_at", -1).limit(1000).to_list(1000)


@router.post("/{kind}", status_code=201)
async def add_item(kind: str, body: dict, user: dict = Depends(hospital_only)):
    coll, schema = _kind(kind)
    try:
        data = schema(**body).model_dump()
    except Exception as e:  # pydantic ValidationError
        raise HTTPException(422, str(e)[:300])
    h = await _my_hospital(get_db(), user)
    doc = {"id": new_id(), "hospital_id": h["id"], **data, "created_at": now()}
    await get_db()[coll].insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.put("/{kind}/{iid}")
async def update_item(kind: str, iid: str, body: dict, user: dict = Depends(hospital_only)):
    coll, schema = _kind(kind)
    h = await _my_hospital(get_db(), user)
    cur = await get_db()[coll].find_one({"id": iid, "hospital_id": h["id"]}, {"_id": 0})
    if not cur:
        raise HTTPException(404, "Not found")
    try:
        data = schema(**{**{k: v for k, v in cur.items() if k not in ("id", "hospital_id", "created_at")}, **body}).model_dump()
    except Exception as e:
        raise HTTPException(422, str(e)[:300])
    await get_db()[coll].update_one({"id": iid}, {"$set": data})
    return {**cur, **data}


@router.delete("/{kind}/{iid}")
async def delete_item(kind: str, iid: str, user: dict = Depends(hospital_only)):
    coll, _ = _kind(kind)
    h = await _my_hospital(get_db(), user)
    await get_db()[coll].delete_one({"id": iid, "hospital_id": h["id"]})
    return {"ok": True}
