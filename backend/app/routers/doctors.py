from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..common import new_id, now
from ..db import get_db
from ..deps import current_user, require_roles

router = APIRouter(tags=["doctors & appointments"])
doctor_only = require_roles("doctor")
patient_only = require_roles("patient")


class DoctorIn(BaseModel):
    specialization: str | None = None
    experience_years: int | None = Field(default=None, ge=0, le=70)
    fee: int | None = Field(default=None, ge=0, le=100000)
    bio: str | None = None
    hospital: str | None = None
    city: str | None = None
    availability: dict | None = None  # {"days":[0..6], "slots":["10:00",...]}


class ApptIn(BaseModel):
    doctor_id: str
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    reason: str = ""
    mode: str = "in_person"  # in_person | video


class ApptAction(BaseModel):
    action: str  # cancel | reschedule | confirm | complete
    date: str | None = None
    time: str | None = None
    notes: str | None = None
    follow_up_date: str | None = None


class FeedbackIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = ""


def _public_doctor(d: dict) -> dict:
    return {k: d.get(k) for k in ("id", "user_id", "name", "specialization", "experience_years", "fee", "bio", "hospital", "city", "availability", "rating", "rating_count")}


async def _visible_doctor_ids(db) -> set:
    return {u["id"] async for u in db.users.find({"role": "doctor", "approved": True, "status": {"$ne": "suspended"}}, {"id": 1})}


@router.get("/doctors")
async def search_doctors(specialization: str | None = None, city: str | None = None, q: str | None = None, user: dict = Depends(current_user)):
    db = get_db()
    ok = await _visible_doctor_ids(db)
    out = []
    for d in await db.doctors.find({}, {"_id": 0}).to_list(500):
        if d["user_id"] not in ok:
            continue
        if specialization and specialization.lower() not in d["specialization"].lower():
            continue
        if city and city.lower() not in (d.get("city") or "").lower():
            continue
        if q and q.lower() not in (d["name"] + d["specialization"] + (d.get("hospital") or "")).lower():
            continue
        out.append(_public_doctor(d))
    return sorted(out, key=lambda d: -d["rating"])


@router.get("/doctors/me")
async def my_doctor_profile(user: dict = Depends(doctor_only)):
    d = await get_db().doctors.find_one({"user_id": user["id"]}, {"_id": 0})
    return {**_public_doctor(d), "license_no": d.get("license_no"), "approved": user.get("approved", False)}


@router.put("/doctors/me")
async def update_doctor(body: DoctorIn, user: dict = Depends(doctor_only)):
    data = body.model_dump(exclude_none=True)
    av = data.get("availability")
    if av:
        if not all(isinstance(x, int) and 0 <= x <= 6 for x in av.get("days", [])) or not all(isinstance(s, str) and len(s) == 5 for s in av.get("slots", [])):
            raise HTTPException(400, "availability must be {days:[0-6], slots:['HH:MM']}")
    if data:
        await get_db().doctors.update_one({"user_id": user["id"]}, {"$set": data})
    return await my_doctor_profile(user)


@router.get("/doctors/{doctor_id}/slots")
async def free_slots(doctor_id: str, date: str = Query(pattern=r"^\d{4}-\d{2}-\d{2}$"), user: dict = Depends(current_user)):
    db = get_db()
    d = await db.doctors.find_one({"id": doctor_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Doctor not found")
    try:
        wd = datetime.strptime(date, "%Y-%m-%d").weekday()
    except ValueError:
        raise HTTPException(400, "Invalid date")
    av = d.get("availability", {})
    if wd not in av.get("days", []):
        return {"date": date, "slots": [], "note": "Doctor is not available on this day"}
    taken = {a["time"] async for a in db.appointments.find({"doctor_id": doctor_id, "date": date, "status": {"$in": ["booked", "confirmed"]}})}
    return {"date": date, "slots": [s for s in av.get("slots", []) if s not in taken]}


@router.post("/appointments", status_code=201)
async def book(body: ApptIn, user: dict = Depends(patient_only)):
    db = get_db()
    d = await db.doctors.find_one({"id": body.doctor_id}, {"_id": 0})
    if not d or d["user_id"] not in await _visible_doctor_ids(db):
        raise HTTPException(404, "Doctor not found")
    if body.date < now()[:10]:
        raise HTTPException(400, "Cannot book in the past")
    if body.mode not in ("in_person", "video"):
        raise HTTPException(400, "mode must be in_person or video")
    slots = await free_slots(body.doctor_id, body.date, user)
    if body.time not in slots["slots"]:
        raise HTTPException(409, "That slot is not available")
    aid = new_id()
    doc = {"id": aid, "patient_user_id": user["id"], "patient_name": user["name"], "doctor_id": d["id"], "doctor_user_id": d["user_id"], "doctor_name": d["name"],
           "specialization": d["specialization"], "date": body.date, "time": body.time, "reason": body.reason[:500], "mode": body.mode,
           "video_url": f"https://meet.jit.si/medismart-{aid[:12]}" if body.mode == "video" else None,
           "status": "booked", "notes": "", "fee": d["fee"], "created_at": now(), "reminded_24h": False, "reminded_1h": False}
    await db.appointments.insert_one(dict(doc))
    from ..common import log_event, notify
    await log_event(db, user["id"], "appointment", f"Appointment booked with {d['name']} on {body.date} {body.time}")
    doctor_user = await db.users.find_one({"id": d["user_id"]})
    await notify(db, doctor_user, "New appointment", f"{user['name']} booked {body.date} {body.time}", "appointment")
    await notify(db, user, "Appointment confirmed", f"{d['name']} - {body.date} {body.time}", "appointment", ("app", "email"))
    doc.pop("_id", None)
    return doc


@router.get("/appointments")
async def my_appointments(status: str | None = None, user: dict = Depends(current_user)):
    db = get_db()
    if user["role"] == "patient":
        q = {"patient_user_id": user["id"]}
    elif user["role"] == "doctor":
        q = {"doctor_user_id": user["id"]}
    else:
        raise HTTPException(403, "Only patients and doctors have appointments")
    if status:
        q["status"] = status
    return await db.appointments.find(q, {"_id": 0}).sort([("date", -1), ("time", -1)]).limit(200).to_list(200)


@router.patch("/appointments/{aid}")
async def update_appt(aid: str, body: ApptAction, user: dict = Depends(current_user)):
    db = get_db()
    a = await db.appointments.find_one({"id": aid}, {"_id": 0})
    if not a or user["id"] not in (a["patient_user_id"], a["doctor_user_id"]):
        raise HTTPException(404, "Appointment not found")
    is_doc = user["id"] == a["doctor_user_id"]
    upd: dict = {}
    if body.action == "cancel":
        if a["status"] in ("completed", "cancelled"):
            raise HTTPException(400, f"Appointment already {a['status']}")
        upd = {"status": "cancelled", "cancelled_by": user["role"]}
    elif body.action == "reschedule":
        if not (body.date and body.time):
            raise HTTPException(400, "date and time required")
        if a["status"] not in ("booked", "confirmed"):
            raise HTTPException(400, "Only active appointments can be rescheduled")
        slots = await free_slots(a["doctor_id"], body.date, user)
        if body.time not in slots["slots"]:
            raise HTTPException(409, "That slot is not available")
        upd = {"date": body.date, "time": body.time, "status": "booked", "reminded_24h": False, "reminded_1h": False}
    elif body.action in ("confirm", "complete"):
        if not is_doc:
            raise HTTPException(403, "Only the doctor can do this")
        upd = {"status": "confirmed" if body.action == "confirm" else "completed"}
        if body.action == "complete":
            upd["notes"] = (body.notes or "")[:3000]
            upd["follow_up_date"] = body.follow_up_date
    else:
        raise HTTPException(400, "action must be cancel, reschedule, confirm or complete")
    await db.appointments.update_one({"id": aid}, {"$set": upd})
    other_id = a["patient_user_id"] if is_doc else a["doctor_user_id"]
    from ..common import notify
    other = await db.users.find_one({"id": other_id})
    await notify(db, other, f"Appointment {body.action}", f"{a['date']} {a['time']} - {user['name']}", "appointment")
    if body.action == "complete" and body.follow_up_date:
        pu = await db.users.find_one({"id": a["patient_user_id"]})
        await notify(db, pu, "Follow-up scheduled", f"Follow-up with {a['doctor_name']} on {body.follow_up_date}", "follow_up", ("app", "email", "sms"))
    return {**a, **upd}


@router.post("/appointments/{aid}/feedback")
async def feedback(aid: str, body: FeedbackIn, user: dict = Depends(patient_only)):
    db = get_db()
    a = await db.appointments.find_one({"id": aid, "patient_user_id": user["id"]})
    if not a or a["status"] != "completed":
        raise HTTPException(400, "Feedback is possible after a completed appointment")
    if a.get("feedback"):
        raise HTTPException(409, "Feedback already submitted")
    await db.appointments.update_one({"id": aid}, {"$set": {"feedback": body.model_dump()}})
    d = await db.doctors.find_one({"id": a["doctor_id"]})
    n = d.get("rating_count", 0)
    await db.doctors.update_one({"id": d["id"]}, {"$set": {"rating": round((d.get("rating", 0) * n + body.rating) / (n + 1), 2), "rating_count": n + 1}})
    return {"ok": True}


# ---- doctor dashboard ----
@router.get("/doctor/dashboard")
async def doctor_dashboard(user: dict = Depends(doctor_only)):
    db = get_db()
    appts = await db.appointments.find({"doctor_user_id": user["id"]}, {"_id": 0}).to_list(2000)
    t = now()[:10]
    patients = {a["patient_user_id"] for a in appts if a["status"] != "cancelled"}
    done = [a for a in appts if a["status"] == "completed"]
    rated = [a["feedback"]["rating"] for a in done if a.get("feedback")]
    by_month: dict = {}
    for a in done:
        by_month[a["date"][:7]] = by_month.get(a["date"][:7], 0) + 1
    return {"today": [a for a in appts if a["date"] == t and a["status"] != "cancelled"],
            "upcoming": sorted([a for a in appts if a["date"] > t and a["status"] in ("booked", "confirmed")], key=lambda a: (a["date"], a["time"]))[:20],
            "stats": {"total_patients": len(patients), "completed": len(done), "cancelled": sum(1 for a in appts if a["status"] == "cancelled"),
                      "avg_rating": round(sum(rated) / len(rated), 2) if rated else None, "consultations_per_month": dict(sorted(by_month.items()))},
            "approved": user.get("approved", False)}


@router.get("/doctor/patients")
async def doctor_patients(user: dict = Depends(doctor_only)):
    db = get_db()
    seen: dict = {}
    for a in await db.appointments.find({"doctor_user_id": user["id"], "status": {"$ne": "cancelled"}}, {"_id": 0}).sort("date", -1).to_list(2000):
        p = seen.setdefault(a["patient_user_id"], {"user_id": a["patient_user_id"], "name": a["patient_name"], "visits": 0, "last_visit": a["date"]})
        p["visits"] += 1
    return list(seen.values())
