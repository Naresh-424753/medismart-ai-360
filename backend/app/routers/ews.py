"""Early Warning System endpoints and alert dispatch."""
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..access import can_access
from ..common import new_id, notify, now
from ..config import settings
from ..db import get_db
from ..deps import current_user, require_roles
from ..services import ews

router = APIRouter(prefix="/ews", tags=["early warning"])
patient_only = require_roles("patient")
staff_only = require_roles("doctor", "hospital")
_last_eval: dict[str, float] = {}
EVAL_MIN_INTERVAL_S = 60
REMIND_MIN = {"high": 60, "critical": 30}


def _iso(h: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=h)).isoformat(timespec="seconds")


async def assess(db, pid: str) -> dict:
    rows = await db.vitals.find({"patient_id": pid, "ts": {"$gte": _iso(8)}}, {"_id": 0, "ecg": 0}).sort("ts", 1).to_list(3000)
    base = await db.vitals.find({"patient_id": pid, "ts": {"$gte": _iso(24 * 14), "$lt": _iso(6)}}, {"_id": 0, "ecg": 0}).sort("ts", 1).to_list(5000)
    return ews.assess(rows, base)


async def care_team(db, pid: str) -> list[dict]:
    """Doctors with a live appointment relationship and the hospital the patient is currently admitted to."""
    team, seen = [], set()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
    async for a in db.appointments.find({"patient_user_id": pid, "status": {"$ne": "cancelled"}, "date": {"$gte": cutoff}}, {"_id": 0}):
        if a["doctor_user_id"] not in seen:
            seen.add(a["doctor_user_id"])
            u = await db.users.find_one({"id": a["doctor_user_id"]})
            if u:
                team.append(u)
    prof = await db.patients.find_one({"user_id": pid}) or {}
    if prof.get("health_id"):
        async for adm in db.admissions.find({"health_id": prof["health_id"], "status": "admitted"}, {"_id": 0}):
            h = await db.hospitals.find_one({"id": adm["hospital_id"]})
            u = await db.users.find_one({"id": h.get("user_id")}) if h and h.get("user_id") else None
            if u and u["id"] not in seen:
                seen.add(u["id"])
                team.append(u)
    return team


async def _settings(db, pid: str) -> dict:
    return await db.ews_settings.find_one({"user_id": pid}, {"_id": 0}) or {"user_id": pid, "share_with_care_team": False}


async def evaluate_and_alert(db, pid: str, force: bool = False) -> dict | None:
    """Called after every stored reading (throttled). Never raises."""
    try:
        if not force and time.time() - _last_eval.get(pid, 0) < EVAL_MIN_INTERVAL_S:
            return None
        _last_eval[pid] = time.time()
        a = await assess(db, pid)
        st = await db.ews_state.find_one({"user_id": pid}, {"_id": 0}) or {"level": "stable", "last_alert": 0}
        prev_rank, rank = ews.LEVEL_RANK.get(st["level"], 1), ews.LEVEL_RANK[a["level"]]
        due = a["level"] in ("high", "critical") and (rank > prev_rank or time.time() - st.get("last_alert", 0) > REMIND_MIN[a["level"]] * 60)
        watch_first = a["level"] == "watch" and rank > prev_rank
        if due or watch_first:
            user = await db.users.find_one({"id": pid})
            eta = a.get("eta_to_urgent_hours")
            proj = a["projected"].get("4h", {}).get("score")
            txt = f"Early-warning {a['level'].upper()}: NEWS2 {a['score_now']}" + (f" -> {proj} projected in 4h" if proj is not None else "") + (f", urgent threshold in ~{eta:g}h" if eta else "") + "."
            await notify(db, user, "Early warning", txt + " " + " ".join(a["reasons"][:1]), "vital_alert", ("app", "sms") if a["level"] == "critical" else ("app",))
            sent = []
            if due and (await _settings(db, pid)).get("share_with_care_team"):
                for u in await care_team(db, pid):
                    await notify(db, u, "Patient deterioration risk", f"{user['name']}: {txt} Open MediSmart > Early Warning.", "ews", ("app", "sms"))
                    sent.append(u["id"])
            await db.ews_events.insert_one({"id": new_id(), "user_id": pid, "level": a["level"], "score_now": a["score_now"], "projected_4h": proj, "eta": eta, "notified": sent, "ts": now()})
            st["last_alert"] = time.time()
        await db.ews_state.update_one({"user_id": pid}, {"$set": {"level": a["level"], "score": a["score_now"], "last_alert": st.get("last_alert", 0), "ts": now()}}, upsert=True)
        return a
    except Exception as e:  # monitoring must never break data ingestion
        try:
            await db.audit_logs.insert_one({"id": new_id(), "user_id": pid, "action": "ews_failed", "detail": str(e)[:200], "ip": "", "ts": now()})
        except Exception:
            pass
        return None


@router.get("/me")
async def my_assessment(user: dict = Depends(patient_only)):
    db = get_db()
    a = await assess(db, user["id"])
    ev = await db.ews_events.find({"user_id": user["id"]}, {"_id": 0}).sort("ts", -1).limit(10).to_list(10)
    return {"assessment": a, "settings": await _settings(db, user["id"]), "events": ev}


class SettingsIn(BaseModel):
    share_with_care_team: bool


@router.put("/me/settings")
async def set_settings(body: SettingsIn, user: dict = Depends(patient_only)):
    await get_db().ews_settings.update_one({"user_id": user["id"]}, {"$set": {"share_with_care_team": body.share_with_care_team, "ts": now()}}, upsert=True)
    return {"share_with_care_team": body.share_with_care_team}


async def _watch_ids(db, user: dict) -> list[str]:
    ids: set[str] = set()
    if user["role"] == "doctor":
        async for a in db.appointments.find({"doctor_user_id": user["id"], "status": {"$ne": "cancelled"}}, {"_id": 0, "patient_user_id": 1}):
            ids.add(a["patient_user_id"])
    else:
        h = await db.hospitals.find_one({"user_id": user["id"]})
        if h:
            async for adm in db.admissions.find({"hospital_id": h["id"], "status": "admitted"}, {"_id": 0}):
                p = await db.patients.find_one({"health_id": adm.get("health_id")}) if adm.get("health_id") else None
                if p:
                    ids.add(p["user_id"])
    shared = []
    for pid in ids:
        if (await _settings(db, pid)).get("share_with_care_team"):
            shared.append(pid)
    return shared


@router.get("/watchlist")
async def watchlist(user: dict = Depends(staff_only)):
    """Patients (who opted in) sorted by risk. Every row is a third-party read and goes on the patient's ledger."""
    db = get_db()
    out = []
    for pid in (await _watch_ids(db, user))[:60]:
        if not await can_access(db, user, pid, "vitals") and user["role"] == "doctor":
            continue
        u = await db.users.find_one({"id": pid}, {"_id": 0, "name": 1})
        a = await assess(db, pid)
        out.append({"patient_id": pid, "name": u["name"], "level": a["level"], "score_now": a["score_now"], "projected_4h": a["projected"].get("4h", {}).get("score"),
                    "eta_to_urgent_hours": a["eta_to_urgent_hours"], "reasons": a["reasons"][:3], "confidence": a["confidence"], "current": a.get("current", {})})
    out.sort(key=lambda r: -ews.LEVEL_RANK[r["level"]])
    return out


@router.get("/patient/{pid}")
async def patient_assessment(pid: str, user: dict = Depends(current_user)):
    db = get_db()
    if user["role"] not in ("doctor", "hospital", "patient"):
        raise HTTPException(403, "Not allowed")
    if user["id"] != pid:
        if pid not in await _watch_ids(db, user):
            raise HTTPException(403, "Patient has not enabled care-team early-warning sharing, or is not under your care")
        if user["role"] == "doctor" and not await can_access(db, user, pid, "vitals"):
            raise HTTPException(403, "No access")
    return await assess(db, pid)


@router.post("/demo/deteriorating")
async def demo_series(user: dict = Depends(patient_only)):
    """DEV_MODE only: writes 6 hours of synthetic, slowly worsening readings so the feature can be demonstrated."""
    if not settings.DEV_MODE:
        raise HTTPException(403, "Demo data is disabled when DEV_MODE=0")
    db = get_db()
    base = datetime.now(timezone.utc)
    docs = []
    for i in range(0, 73):  # every 5 minutes for 6 hours
        f = i / 72
        ts = (base - timedelta(minutes=5 * (72 - i))).isoformat(timespec="seconds")
        docs.append({"id": new_id(), "patient_id": user["id"], "heart_rate": round(78 + 30 * f + (i % 3), 1), "spo2": round(98 - 4.5 * f + (i % 2) * 0.3, 1), "temperature": round(36.8 + 1.4 * f, 1),
                     "respiratory_rate": round(16 + 7 * f, 1), "systolic": round(122 - 16 * f, 1), "status": "normal", "source": "ews_demo", "ts": ts})
    await db.vitals.insert_many(docs)
    a = await evaluate_and_alert(db, user["id"], force=True)
    return {"inserted": len(docs), "assessment": a}


@router.delete("/demo")
async def clear_demo(user: dict = Depends(patient_only)):
    r = await get_db().vitals.delete_many({"patient_id": user["id"], "source": "ews_demo"})
    return {"deleted": r.deleted_count}
