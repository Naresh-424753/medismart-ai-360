from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..common import new_id, now, today
from ..db import get_db
from ..deps import require_roles
from ..services import wellness as w
from ..services.analytics import trend

router = APIRouter(prefix="/wellness", tags=["nutrition, fitness & mental health"])
patient_only = require_roles("patient")
LOG_TYPES = {"weight", "water", "steps", "sleep", "mood", "journal"}


class CalcIn(BaseModel):
    weight_kg: float = Field(gt=10, lt=400)
    height_cm: float = Field(gt=60, lt=260)
    age: int = Field(ge=5, le=110)
    sex: str
    activity: str = "light"
    goal: str = "maintain"
    vegetarian: bool = True


class LogIn(BaseModel):
    type: str
    value: float | None = None
    note: str = ""
    date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class ScreenIn(BaseModel):
    kind: str  # depression | anxiety
    answers: list[int]


@router.post("/calculate")
async def calculate(body: CalcIn, user: dict = Depends(patient_only)):
    r = w.calculate(body.weight_kg, body.height_cm, body.age, body.sex, body.activity, body.goal)
    prof = await get_db().patients.find_one({"user_id": user["id"]}) or {}
    conds = [d["name"] for d in prof.get("diseases", [])]
    return {**r, "diet": w.diet_plan(r["calorie_target"], conds, body.vegetarian), "exercise": w.exercise_plan(r["bmi"], body.age, conds)}


@router.post("/log", status_code=201)
async def add_log(body: LogIn, user: dict = Depends(patient_only)):
    if body.type not in LOG_TYPES:
        raise HTTPException(400, f"type must be one of {sorted(LOG_TYPES)}")
    if body.type == "mood" and not (body.value is not None and 1 <= body.value <= 5):
        raise HTTPException(400, "mood value must be 1 (low) to 5 (great)")
    if body.type not in ("journal",) and body.value is None:
        raise HTTPException(400, "value is required")
    doc = {"id": new_id(), "user_id": user["id"], "type": body.type, "value": body.value, "note": body.note[:2000], "date": body.date or today(), "ts": now()}
    await get_db().wellness_logs.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.get("/logs")
async def logs(type: str, days: int = 30, user: dict = Depends(patient_only)):
    since = (datetime.now() - timedelta(days=min(days, 365))).strftime("%Y-%m-%d")
    return await get_db().wellness_logs.find({"user_id": user["id"], "type": type, "date": {"$gte": since}}, {"_id": 0}).sort("date", 1).to_list(1000)


@router.delete("/logs/{lid}")
async def del_log(lid: str, user: dict = Depends(patient_only)):
    await get_db().wellness_logs.delete_one({"id": lid, "user_id": user["id"]})
    return {"deleted": lid}


@router.get("/progress")
async def progress(user: dict = Depends(patient_only)):
    """Weekly progress summary across water, steps, sleep, mood and weight."""
    since = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    rows = await get_db().wellness_logs.find({"user_id": user["id"], "date": {"$gte": since}}, {"_id": 0}).to_list(2000)
    out: dict = {}
    for t in ("water", "steps", "sleep", "mood", "weight"):
        by_day: dict = {}
        for r in rows:
            if r["type"] == t and r["value"] is not None:
                by_day.setdefault(r["date"], []).append(r["value"])
        series = {d: (sum(v) if t in ("water", "steps") else sum(v) / len(v)) for d, v in sorted(by_day.items())}
        vals = list(series.values())
        out[t] = {"daily": series, "average": round(sum(vals) / len(vals), 1) if vals else None, "trend": trend(vals)}
    tips = []
    if out["sleep"]["average"] is not None and out["sleep"]["average"] < 6.5:
        tips.append("Your average sleep is under 6.5 h - try a fixed bedtime and no screens before bed.")
    if out["water"]["average"] is not None and out["water"]["average"] < 2:
        tips.append("Water intake looks low - aim for 2-3 litres a day.")
    if out["steps"]["average"] is not None and out["steps"]["average"] < 5000:
        tips.append("Try a 20-minute walk after meals to raise your step count.")
    if out["mood"]["average"] is not None and out["mood"]["average"] <= 2.5:
        tips.append("Your mood has been low this week. Consider talking to someone you trust or booking a counselor.")
    return {"weekly": out, "tips": tips}


@router.get("/screening-questions")
async def questions(user: dict = Depends(patient_only)):
    return {"scale": ["Not at all (0)", "Several days (1)", "More than half the days (2)", "Nearly every day (3)"],
            "depression": w.PHQ2, "anxiety": w.GAD2, "note": "Over the last 2 weeks, how often have you been bothered by:"}


@router.post("/screen")
async def screen(body: ScreenIn, user: dict = Depends(patient_only)):
    if body.kind not in ("depression", "anxiety"):
        raise HTTPException(400, "kind must be depression or anxiety")
    try:
        res = w.screen(body.kind, body.answers)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await get_db().wellness_logs.insert_one({"id": new_id(), "user_id": user["id"], "type": f"screen_{body.kind}", "value": res["score"], "note": "", "date": today(), "ts": now()})
    return res


@router.get("/breathing")
async def breathing(user: dict = Depends(patient_only)):
    return w.breathing_exercises()
