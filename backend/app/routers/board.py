"""Second opinion & medical board review. AI ensemble runs automatically; specialists see the case only after the patient consents."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..access import can_access
from ..common import audit, new_id, notify, now
from ..db import get_db
from ..deps import require_roles
from ..services import board as B
from ..services import ledger, ml

router = APIRouter(prefix="/board", tags=["second opinion"])
patient_only = require_roles("patient")
doctor_only = require_roles("doctor")
PANEL_SIZE = 3


async def _gather(db, uid: str, symptom_list: list[str] | None = None, note: str = "") -> dict:
    from .ai import _autofill
    prof = await db.patients.find_one({"user_id": uid}, {"_id": 0}) or {}
    values = await _autofill(db, uid)
    reps = await db.reports.find({"user_id": uid}, {"_id": 0}).sort("ts", -1).limit(5).to_list(5)
    findings = [f for r in reps for f in r.get("findings", [])]
    abnormal = [f for f in findings if f.get("status") != "normal"]
    vit = (await db.vitals.find({"patient_id": uid}, {"_id": 0, "ecg": 0}).sort("ts", -1).limit(1).to_list(1) or [None])[0]
    risks_all = await db.risk_assessments.find({"user_id": uid}, {"_id": 0}).sort("ts", -1).to_list(200)
    latest = list({r["disease"]: r for r in reversed(risks_all)}.values())
    meds = await db.medicines.find({"user_id": uid, "active": True}, {"_id": 0, "name": 1}).to_list(30)
    dob = prof.get("dob")
    age = None
    if dob:
        y, m, d = map(int, dob.split("-")); t = datetime.now().date(); age = t.year - y - ((t.month, t.day) < (m, d))
    conditions = [d["name"] for d in prof.get("diseases", [])]
    return {"values": values, "findings": findings, "abnormal": abnormal, "vitals": vit, "risks": latest, "conditions": conditions, "note": note[:600], "symptoms": symptom_list or [],
            "packet": {"age": age, "sex": prof.get("sex"), "known_conditions": conditions, "allergies": [a["name"] for a in prof.get("allergies", [])],
                       "active_medicines": [m["name"] for m in meds], "abnormal_findings": [{"test": f["test"], "value": f["value"], "unit": f.get("unit"), "status": f["status"], "severity": f.get("severity")} for f in abnormal[:15]],
                       "risk_levels": {r["disease"]: r["level"] for r in latest},
                       "latest_vitals": {k: vit.get(k) for k in ("heart_rate", "spo2", "temperature", "systolic", "diastolic", "status")} if vit else None,
                       "symptoms": symptom_list or [], "patient_note": note[:600]}}


async def create_case(db, uid: str, origin: str, reasons: list[str], symptom_list=None, note="", requested_by: str | None = None) -> dict:
    g = await _gather(db, uid, symptom_list, note)
    provs = [B.provider_risk_models(g["values"], {r["disease"]: r["probability"] for r in g["risks"]}), B.provider_rules(g["findings"], g["symptoms"], g["note"], (g["vitals"] or {}).get("status")), await B.provider_llm(g["packet"])]
    case = {"id": new_id(), "patient_id": uid, "origin": origin, "requested_by": requested_by or uid, "triggers": reasons, "status": "awaiting_consent", "packet": g["packet"],
            "providers": provs, "ensemble": B.ensemble(provs), "consent": None, "panel": [], "report": None, "created_at": now()}
    if case["ensemble"]["methods_disagree_on_top"]:
        case["triggers"].append("ai_methods_disagree")
    await db.board_cases.insert_one(dict(case))
    case.pop("_id", None)
    return case


async def maybe_auto_case(db, uid: str) -> None:
    """Called after risk checks and report analysis. Opens at most one case per patient per 7 days. Never raises."""
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        if await db.board_cases.find_one({"patient_id": uid, "created_at": {"$gte": since}, "status": {"$ne": "cancelled"}}):
            return
        g = await _gather(db, uid)
        why = B.triggers(g["risks"], g["findings"], g["conditions"], vitals_status=(g["vitals"] or {}).get("status"))
        if not why:
            return
        case = await create_case(db, uid, "auto", why)
        user = await db.users.find_one({"id": uid})
        await notify(db, user, "Second-opinion review ready", "Your case looks complex, so an AI review was prepared. Open Second Opinion to read it and, if you agree, share an anonymised summary with a panel of specialists.", "second_opinion")
        await audit(db, uid, "board_case_auto", case["id"])
    except Exception:
        return


class CaseIn(BaseModel):
    symptoms: list[str] = []
    note: str = Field(default="", max_length=600)


async def _own(db, cid, user):
    c = await db.board_cases.find_one({"id": cid, "patient_id": user["id"]}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Case not found")
    return c


@router.post("/cases", status_code=201)
async def request_case(body: CaseIn, user: dict = Depends(patient_only)):
    db = get_db()
    return await create_case(db, user["id"], "patient", ["patient_requested"], body.symptoms[:20], body.note)


@router.post("/cases/for/{patient_user_id}", status_code=201)
async def doctor_request(patient_user_id: str, body: CaseIn, user: dict = Depends(doctor_only)):
    db = get_db()
    if not await can_access(db, user, patient_user_id, "summary"):
        raise HTTPException(403, "No access to this patient")
    c = await create_case(db, patient_user_id, "doctor", ["doctor_requested"], body.symptoms[:20], body.note, requested_by=user["id"])
    await notify(db, await db.users.find_one({"id": patient_user_id}), "Second-opinion review prepared", f"Dr. {user['name']} asked for a second-opinion review. Open Second Opinion to see it and decide whether to share it with a specialist panel.", "second_opinion")
    return c


@router.get("/cases")
async def my_cases(user: dict = Depends(patient_only)):
    rows = await get_db().board_cases.find({"patient_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
    for r in rows:
        for p in r["panel"]:
            p.pop("doctor_user_id", None)
    return rows


class ConsentIn(BaseModel):
    allow: bool = True


@router.post("/cases/{cid}/consent")
async def consent(cid: str, body: ConsentIn, user: dict = Depends(patient_only)):
    """Patient agrees to share the ANONYMISED packet (no name, contact or address) with up to 3 specialists."""
    db = get_db()
    c = await _own(db, cid, user)
    if c["status"] != "awaiting_consent":
        raise HTTPException(409, "Case is already past the consent step")
    if not body.allow:
        await db.board_cases.update_one({"id": cid}, {"$set": {"status": "cancelled", "consent": {"given": False, "ts": now()}}})
        return {"status": "cancelled"}
    wanted = [r["specialist"] for r in c["ensemble"]["top"][:3]] + [B.SPEC_FALLBACK]
    panel, used = [], set()
    docs = await db.doctors.find({}, {"_id": 0}).to_list(500)
    for spec in wanted:
        for d in docs:
            if d["user_id"] in used or d["user_id"] == user["id"] or spec.lower() not in (d.get("specialization") or "").lower():
                continue
            du = await db.users.find_one({"id": d["user_id"]})
            if not du or not du.get("approved"):
                continue
            used.add(d["user_id"]); panel.append({"doctor_user_id": d["user_id"], "name": d["name"], "specialization": d["specialization"], "status": "invited", "opinion": None, "invited_at": now()})
            break
        if len(panel) >= PANEL_SIZE:
            break
    for d in docs:  # fill remaining seats with any other approved doctor
        if len(panel) >= PANEL_SIZE:
            break
        if d["user_id"] not in used and d["user_id"] != user["id"] and (du := await db.users.find_one({"id": d["user_id"]})) and du.get("approved"):
            used.add(d["user_id"]); panel.append({"doctor_user_id": d["user_id"], "name": d["name"], "specialization": d["specialization"], "status": "invited", "opinion": None, "invited_at": now()})
    if len(panel) < 2:
        raise HTTPException(409, "Not enough verified doctors are available to form a panel")
    await db.board_cases.update_one({"id": cid}, {"$set": {"status": "panel_review", "consent": {"given": True, "ts": now()}, "panel": panel}})
    await ledger.append(db, user["id"], "access_grant", {"grantee": "second_opinion_panel", "scope": "anonymised_case", "case": cid}, actor=user["id"])
    for p in panel:
        await notify(db, await db.users.find_one({"id": p["doctor_user_id"]}), "Second-opinion panel request", "You were invited to a medical board review (anonymised case). Open Board Review to respond.", "second_opinion")
    return {"status": "panel_review", "panel": [{k: p[k] for k in ("name", "specialization", "status")} for p in panel]}


@router.get("/panel")
async def my_panel(user: dict = Depends(doctor_only)):
    rows = await get_db().board_cases.find({"panel.doctor_user_id": user["id"], "status": {"$in": ["panel_review", "completed"]}}, {"_id": 0}).sort("created_at", -1).to_list(100)
    out = []
    for r in rows:
        mine = next(p for p in r["panel"] if p["doctor_user_id"] == user["id"])
        out.append({"id": r["id"], "status": r["status"], "created_at": r["created_at"], "triggers": r["triggers"], "packet": r["packet"], "ensemble": r["ensemble"],
                    "my_status": mine["status"], "my_opinion": mine["opinion"], "report": r["report"] if r["status"] == "completed" else None})
    return out


class OpinionIn(BaseModel):
    verdict: str = Field(pattern=r"^(agree|modify|disagree|need_more_info)$")
    suggested_diagnosis: str = Field(default="", max_length=200)
    recommended_tests: list[str] = []
    recommended_specialist: str = Field(default="", max_length=80)
    comments: str = Field(default="", max_length=2000)


@router.post("/panel/{cid}/opinion")
async def submit_opinion(cid: str, body: OpinionIn, user: dict = Depends(doctor_only)):
    db = get_db()
    c = await db.board_cases.find_one({"id": cid, "status": "panel_review", "panel.doctor_user_id": user["id"]})
    if not c:
        raise HTTPException(404, "No open case for you")
    op = {**body.model_dump(), "recommended_tests": [t[:80] for t in body.recommended_tests[:10]], "submitted_at": now()}
    panel = [{**p, "status": "submitted", "opinion": op} if p["doctor_user_id"] == user["id"] else p for p in c["panel"]]
    await db.board_cases.update_one({"id": cid}, {"$set": {"panel": panel}})
    c["panel"] = panel
    if all(p["status"] == "submitted" for p in panel):
        await _complete(db, c)
        return {"status": "completed"}
    return {"status": "submitted", "waiting_for": sum(1 for p in panel if p["status"] != "submitted")}


async def _complete(db, c: dict) -> dict:
    rep = B.build_report(c)
    rep["generated_at"] = now()
    rep["sha256"] = B.report_hash({k: v for k, v in rep.items() if k != "sha256"})
    await db.board_cases.update_one({"id": c["id"]}, {"$set": {"status": "completed", "report": rep}})
    await ledger.append(db, c["patient_id"], "second_opinion_report", {"case": c["id"], "sha256": rep["sha256"]})
    await notify(db, await db.users.find_one({"id": c["patient_id"]}), "Second Opinion Report ready", "The panel has responded. Open Second Opinion to read the report and take it to your doctor.", "second_opinion")
    return rep


@router.post("/cases/{cid}/finalize")
async def finalize(cid: str, user: dict = Depends(patient_only)):
    """Close the case early once at least two doctors have answered."""
    db = get_db()
    c = await _own(db, cid, user)
    if c["status"] != "panel_review":
        raise HTTPException(409, "Case is not under panel review")
    if sum(1 for p in c["panel"] if p["status"] == "submitted") < 2:
        raise HTTPException(409, "At least two doctors must respond first")
    return await _complete(db, c)
