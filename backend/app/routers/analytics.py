from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import get_db
from ..deps import require_roles
from ..services import analytics as an

router = APIRouter(prefix="/analytics", tags=["predictive analytics"])
patient_only = require_roles("patient")
staff = require_roles("admin", "hospital")


class ReadmitIn(BaseModel):
    age: int = Field(ge=0, le=120)
    admissions_last_year: int = Field(ge=0, le=50)
    chronic_conditions: int = Field(ge=0, le=20)
    length_of_stay: int = Field(ge=0, le=365)
    emergency_admission: bool = False


@router.get("/my-health")
async def my_health(days: int = 14, user: dict = Depends(patient_only)):
    """Daily vitals averages, trend direction, abnormal-pattern detection, and risk history."""
    db = get_db()
    since = (datetime.now(timezone.utc) - timedelta(days=min(days, 90))).isoformat(timespec="seconds")
    rows = await db.vitals.find({"patient_id": user["id"], "ts": {"$gte": since}}, {"_id": 0, "ecg": 0}).sort("ts", 1).to_list(20000)
    metrics = {}
    for m in ("heart_rate", "spo2", "temperature", "systolic", "diastolic", "glucose"):
        by_day: dict = {}
        for r in rows:
            if r.get(m) is not None:
                by_day.setdefault(r["ts"][:10], []).append(r[m])
        daily = {d: round(sum(v) / len(v), 1) for d, v in sorted(by_day.items())}
        raw = [r[m] for r in rows if r.get(m) is not None]
        metrics[m] = {"daily_avg": daily, "trend": an.trend(list(daily.values())), "anomaly_count": len(an.anomalies(raw)), "n": len(raw)}
    risks = await db.risk_assessments.find({"user_id": user["id"]}, {"_id": 0}).sort("ts", 1).to_list(500)
    risk_series: dict = {}
    for r in risks:
        risk_series.setdefault(r["disease"], []).append({"ts": r["ts"], "p": r["probability"]})
    alerts = await db.vital_alerts.count_documents({"patient_id": user["id"], "ts": {"$gte": since}})
    rising = [d for d, s in risk_series.items() if len(s) >= 3 and an.trend([x["p"] for x in s]) == "rising"]
    return {"vitals": metrics, "risk_history": risk_series, "alerts_in_period": alerts,
            "preventive_alerts": [f"Your {d} risk score has been rising across recent assessments - consider a check-up." for d in rising]
            + [f"Unusual {k.replace('_', ' ')} readings detected ({v['anomaly_count']})." for k, v in metrics.items() if v["anomaly_count"]]}


@router.get("/monthly-report")
async def monthly_report(user: dict = Depends(patient_only)):
    db = get_db()
    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec="seconds")
    uid = user["id"]
    ev = await db.events.find({"user_id": uid, "ts": {"$gte": since}}, {"_id": 0}).to_list(2000)
    counts: dict = {}
    for e in ev:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    reps = await db.reports.find({"user_id": uid, "ts": {"$gte": since}}, {"_id": 0}).to_list(200)
    meds = await db.med_logs.count_documents({"user_id": uid, "date": {"$gte": since[:10]}})
    return {"period": f"{since[:10]} to {datetime.now().strftime('%Y-%m-%d')}", "activity": counts, "reports_analyzed": len(reps),
            "abnormal_values": sum(r["abnormal_count"] for r in reps), "doses_logged": meds,
            "vital_alerts": await db.vital_alerts.count_documents({"patient_id": uid, "ts": {"$gte": since}}),
            "appointments": await db.appointments.count_documents({"patient_user_id": uid, "date": {"$gte": since[:10]}})}


@router.post("/readmission-risk")
async def readmission(body: ReadmitIn, user: dict = Depends(require_roles("doctor", "hospital", "admin"))):
    return an.readmission_risk(**body.model_dump())


@router.get("/population")
async def population(user: dict = Depends(staff)):
    """Aggregate, de-identified population view."""
    db = get_db()
    risks = await db.risk_assessments.find({}, {"_id": 0, "disease": 1, "level": 1}).to_list(100000)
    by: dict = {}
    for r in risks:
        by.setdefault(r["disease"], {"low": 0, "moderate": 0, "high": 0})[r["level"]] += 1
    appts = await db.appointments.find({}, {"_id": 0, "date": 1, "specialization": 1}).to_list(100000)
    daily: dict = {}
    spec: dict = {}
    for a in appts:
        daily[a["date"]] = daily.get(a["date"], 0) + 1
        spec[a["specialization"]] = spec.get(a["specialization"], 0) + 1
    series = [daily[k] for k in sorted(daily)]
    return {"risk_distribution": by, "appointments_by_specialization": spec, "appointment_trend": an.trend(series), "appointments_forecast_7d": an.forecast(series, 7)}
