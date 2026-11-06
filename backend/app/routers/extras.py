"""Smaller features: radiology/ECG report explainer, meditation, sleep schedule, counselors, public kiosk endpoints."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..common import haversine_km, now
from ..db import get_db
from ..deps import current_user, require_roles
from ..services import radiology, symptoms
from .doctors import _public_doctor, _visible_doctor_ids

router = APIRouter(tags=["extras"])
patient_only = require_roles("patient")

MEDITATIONS = [
    {"id": "breath-awareness", "title": "Breath awareness", "title_hi": "सांसों पर ध्यान", "minutes": 5, "good_for": ["stress", "focus"],
     "steps": ["Sit comfortably with a straight back.", "Close your eyes and breathe naturally.", "Follow the air in and out at the nostrils.", "When the mind wanders, gently return to the breath."]},
    {"id": "body-scan", "title": "Body scan", "title_hi": "बॉडी स्कैन", "minutes": 10, "good_for": ["sleep", "anxiety", "pain"],
     "steps": ["Lie down and close your eyes.", "Bring attention to your toes, then slowly move up the body.", "Notice sensations without judging them.", "Soften any tight area as you breathe out."]},
    {"id": "box-breathing", "title": "Box breathing", "title_hi": "बॉक्स ब्रीदिंग", "minutes": 4, "good_for": ["anxiety", "stress"],
     "steps": ["Breathe in for 4 counts.", "Hold for 4 counts.", "Breathe out for 4 counts.", "Hold for 4 counts. Repeat 6-8 rounds."]},
    {"id": "loving-kindness", "title": "Loving-kindness", "title_hi": "मैत्री ध्यान", "minutes": 8, "good_for": ["low mood", "loneliness"],
     "steps": ["Silently say: 'May I be safe, healthy and at peace.'", "Repeat for someone you love.", "Then for a neutral person, and finally for everyone."]},
    {"id": "yoga-nidra", "title": "Yoga nidra (guided rest)", "title_hi": "योग निद्रा", "minutes": 15, "good_for": ["sleep", "fatigue"],
     "steps": ["Lie on your back, arms relaxed.", "Set a gentle intention for the day or night.", "Rotate attention through each body part.", "End by noticing the whole body resting."]},
    {"id": "5-4-3-2-1", "title": "5-4-3-2-1 grounding", "title_hi": "ग्राउंडिंग तकनीक", "minutes": 3, "good_for": ["panic", "anxiety"],
     "steps": ["Name 5 things you can see.", "4 you can touch.", "3 you can hear.", "2 you can smell.", "1 you can taste."]},
]


@router.get("/wellness/meditations")
async def meditations(need: str | None = None, user: dict = Depends(current_user)):
    items = [m for m in MEDITATIONS if not need or any(need.lower() in g for g in m["good_for"])]
    return items or MEDITATIONS


@router.get("/wellness/sleep-schedule")
async def sleep_schedule(wake_time: str = "06:30", age: int = 30, user: dict = Depends(patient_only)):
    try:
        wake = datetime.strptime(wake_time, "%H:%M")
    except ValueError:
        raise HTTPException(400, "wake_time must be HH:MM")
    need = 9.5 if age < 14 else 8.5 if age < 18 else 8 if age < 65 else 7.5
    # whole 90-minute sleep cycles + ~15 minutes to fall asleep
    options = [{"cycles": c, "hours": round(c * 1.5, 1), "bedtime": (wake - timedelta(minutes=c * 90 + 15)).strftime("%H:%M")} for c in (6, 5, 4)]
    since = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    logs = await get_db().wellness_logs.find({"user_id": user["id"], "type": "sleep", "date": {"$gte": since}}, {"_id": 0}).to_list(50)
    vals = [l["value"] for l in logs if l.get("value") is not None]
    avg = round(sum(vals) / len(vals), 1) if vals else None
    tips = ["Keep the same wake-up time every day, even on weekends.", "No caffeine 8 hours before bed and no screens for the last 30 minutes.", "Keep the room dark, quiet and cool."]
    if avg is not None and avg < need - 1:
        tips.insert(0, f"You averaged {avg} h this week, about {round(need - avg, 1)} h below the {need} h suggested for your age. Move bedtime earlier in 15-minute steps.")
    return {"recommended_hours": need, "options": options, "avg_last_7_days": avg, "tips": tips}


@router.get("/wellness/counselors")
async def counselors(city: str | None = None, user: dict = Depends(patient_only)):
    """Mental-health professionals from the verified doctor list; book them from Appointments."""
    db = get_db()
    ok = await _visible_doctor_ids(db)
    out = []
    for d in await db.doctors.find({}, {"_id": 0}).to_list(500):
        sp = d["specialization"].lower()
        if d["user_id"] in ok and any(k in sp for k in ("psych", "counsel", "mental")) and (not city or city.lower() in (d.get("city") or "").lower()):
            out.append(_public_doctor(d))
    return sorted(out, key=lambda d: -d["rating"])


class ExplainIn(BaseModel):
    text: str = Field(min_length=10, max_length=20000)
    modality: str | None = None  # ecg | xray | ct | mri (auto-detected if omitted)


@router.post("/extras/explain-report")
async def explain_report(body: ExplainIn, user: dict = Depends(current_user)):
    try:
        return radiology.explain(body.text, body.modality)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---- public kiosk endpoints (no login; read-only and non-identifying; rate limited in main.py) ----
kiosk = APIRouter(prefix="/kiosk", tags=["kiosk"])


class KioskSymptoms(BaseModel):
    symptoms: list[str] = Field(default=[], max_length=20)
    text: str = Field(default="", max_length=500)


class KioskBmi(BaseModel):
    weight_kg: float = Field(gt=10, lt=400)
    height_cm: float = Field(gt=60, lt=260)


@kiosk.post("/symptom-check")
async def kiosk_symptoms(body: KioskSymptoms):
    return symptoms.check(body.symptoms, body.text)


@kiosk.post("/bmi")
async def kiosk_bmi(body: KioskBmi):
    from ..services.wellness import bmi_category
    b = round(body.weight_kg / (body.height_cm / 100) ** 2, 1)
    return {"bmi": b, "category": bmi_category(b)}


@kiosk.get("/hospitals")
async def kiosk_hospitals(lat: float | None = None, lon: float | None = None, city: str | None = None):
    rows = await get_db().hospitals.find({"verified": True}, {"_id": 0}).to_list(500)
    out = []
    for h in rows:
        if city and city.lower() not in h.get("city", "").lower():
            continue
        dist = round(haversine_km(lat, lon, h["lat"], h["lon"]), 1) if lat is not None and lon is not None else None
        out.append({"name": h["name"], "city": h.get("city"), "phone": h.get("phone"), "address": h.get("address"), "distance_km": dist,
                    "icu_available": h["beds"]["icu"]["available"], "emergency_beds": h["beds"]["emergency"]["available"]})
    return sorted(out, key=lambda x: (x["distance_km"] is None, x["distance_km"] or 0))[:10]


@kiosk.get("/emergency-numbers")
async def numbers():
    return {"national_emergency": "112", "ambulance": "108", "women_helpline": "1091", "poison_control": "1066", "tele_mental_health": "14416"}
