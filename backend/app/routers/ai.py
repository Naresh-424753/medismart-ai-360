import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from ..common import log_event, new_id, now
from ..db import get_db
from ..deps import current_user, require_roles
from ..services import image_ai, ml, profile_features, symptoms

router = APIRouter(prefix="/ai", tags=["ai"])
patient_only = require_roles("patient")


class PredictIn(BaseModel):
    values: dict = {}
    use_profile: bool = True


class SymptomIn(BaseModel):
    symptoms: list[str] = []
    text: str = ""


async def _autofill(db, user_id: str) -> dict:
    profile = await db.patients.find_one({"user_id": user_id}, {"_id": 0}) or {}
    vit = await db.vitals.find({"patient_id": user_id}, {"_id": 0}).sort("ts", -1).limit(1).to_list(1)
    rep = await db.reports.find({"user_id": user_id}, {"_id": 0}).sort("ts", -1).limit(10).to_list(10)
    labs: dict = {}
    for r in reversed(rep):  # newest wins
        labs.update(r.get("values", {}))
    return profile_features.build(profile, vit[0] if vit else None, labs)


@router.get("/diseases")
async def diseases(user: dict = Depends(current_user)):
    return [{"id": k, "title": v["title"], "features": ml.feature_schema(k)} for k, v in ml.SPECS.items()]


@router.get("/autofill")
async def autofill(user: dict = Depends(patient_only)):
    return await _autofill(get_db(), user["id"])


@router.post("/predict/{disease}")
async def predict(disease: str, body: PredictIn, user: dict = Depends(patient_only)):
    if disease not in ml.SPECS:
        raise HTTPException(404, f"Unknown disease. Choose from {list(ml.SPECS)}")
    db = get_db()
    values = {**(await _autofill(db, user["id"]) if body.use_profile else {}), **body.values}
    res = ml.predict(disease, values)
    await db.risk_assessments.insert_one({"id": new_id(), "user_id": user["id"], "disease": disease, "probability": res["probability"], "level": res["level"], "ts": now()})
    await log_event(db, user["id"], "risk", f"{res['title']}: {res['level']} ({res['score']}%)")
    from .board import maybe_auto_case  # opens a second-opinion case when the picture is complex
    await maybe_auto_case(db, user["id"])
    return res


@router.post("/risk-score")
async def risk_score(body: PredictIn, user: dict = Depends(patient_only)):
    """Multi-disease assessment + overall health score. Missing inputs use model defaults - results flag how many were provided."""
    db = get_db()
    values = {**(await _autofill(db, user["id"]) if body.use_profile else {}), **body.values}
    results = [ml.predict(d, values) for d in ml.SPECS]
    for r in results:
        provided = sum(1 for f in ml.SPECS[r["disease"]]["features"] if f in values)
        r["inputs_provided"], r["inputs_total"] = provided, len(ml.SPECS[r["disease"]]["features"])
        await db.risk_assessments.insert_one({"id": new_id(), "user_id": user["id"], "disease": r["disease"], "probability": r["probability"], "level": r["level"], "ts": now()})
    overall = ml.overall_health_score(results)
    await log_event(db, user["id"], "risk", f"Health risk score: {overall['score']} ({overall['label']})")
    from .board import maybe_auto_case
    await maybe_auto_case(db, user["id"])
    prevention = sorted({r["advice"] for r in results if r["level"] != "low"}) or ["Keep up your healthy habits and have a yearly check-up."]
    return {"overall": overall, "results": results, "preventive_recommendations": prevention, "disclaimer": ml.DISCLAIMER}


@router.get("/risk-history")
async def risk_history(user: dict = Depends(patient_only)):
    return await get_db().risk_assessments.find({"user_id": user["id"]}, {"_id": 0}).sort("ts", -1).limit(100).to_list(100)


@router.get("/symptoms")
async def symptom_list(user: dict = Depends(current_user)):
    return symptoms.all_symptoms()


@router.post("/symptom-check")
async def symptom_check(body: SymptomIn, user: dict = Depends(current_user)):
    res = symptoms.check(body.symptoms, body.text)
    if user["role"] == "patient":
        await log_event(get_db(), user["id"], "symptoms", f"Symptom check: {', '.join(res['symptoms'][:5])}", {"urgency": res["urgency"]})
    return res


TASK_LABELS = {"chest_xray": "Chest X-ray (pneumonia / TB screening)", "brain_mri": "Brain MRI (tumor screening)", "skin": "Skin lesion analysis",
               "retina": "Retinal image (diabetic retinopathy)", "cataract": "Eye / cataract screening", "segment": "Medical image segmentation",
               "fracture": "Bone fracture detection", "tumor_classification": "Brain tumor classification", "pneumonia_classification": "Pneumonia classification"}


def _task(kind: str) -> str:
    t = kind.replace("-", "_")
    return {"skin_lesion": "skin", "eye_cataract": "cataract", "bone_fracture": "fracture"}.get(t, t)


@router.get("/image-models")
async def image_models(user: dict = Depends(current_user)):
    out = []
    for t in image_ai.TASKS:
        trained = (image_ai.MODEL_DIR / f"{t}.onnx").exists()
        mode = "cnn" if trained else ("needs-trained-model" if t in image_ai.CNN_ONLY_TASKS else "heuristic-demo")
        out.append({"kind": t, "title": TASK_LABELS.get(t, t), "mode": mode})
    return out


@router.post("/image/{kind}")
async def analyze_image(kind: str, file: UploadFile = File(...), user: dict = Depends(patient_only)):
    task = _task(kind)
    if task not in image_ai.TASKS:
        raise HTTPException(404, f"Unknown analysis type. Choose from {image_ai.TASKS}")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "Image too large (max 10 MB)")
    try:
        res = image_ai.analyze(data, task)
    except image_ai.ImageError as e:
        raise HTTPException(400, str(e))
    db = get_db()
    rid = new_id()
    stored = {k: v for k, v in res.items() if k != "overlay_png"}
    await db.imaging_results.insert_one({"id": rid, "user_id": user["id"], "kind": task, "result": stored, "ts": now()})
    if res.get("available", True):
        await log_event(db, user["id"], "imaging", f"{TASK_LABELS.get(task, task)}: {res.get('finding') or res.get('label') or ''}"[:200])
    return {**res, "result_id": rid}


@router.get("/image-history")
async def image_history(user: dict = Depends(patient_only)):
    return await get_db().imaging_results.find({"user_id": user["id"]}, {"_id": 0}).sort("ts", -1).limit(50).to_list(50)


@router.get("/image-report/{rid}")
async def image_report(rid: str, user: dict = Depends(current_user)):
    """Image-based medical report generation: re-creates the text report of a stored analysis (owner only)."""
    r = await get_db().imaging_results.find_one({"id": rid, "user_id": user["id"]}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Result not found")
    res = r["result"]
    return {"result_id": rid, "task": r["kind"], "created": r["ts"], "report": res.get("report") or image_ai.generate_report(r["kind"], res)}


# ---- digital twin + second opinion ----
class TwinSim(BaseModel):
    changes: dict


@router.get("/digital-twin")
async def digital_twin(user: dict = Depends(patient_only)):
    db = get_db()
    features = await _autofill(db, user["id"])
    profile = await db.patients.find_one({"user_id": user["id"]}, {"_id": 0})
    vit = await db.vitals.find({"patient_id": user["id"]}, {"_id": 0}).sort("ts", -1).limit(50).to_list(50)
    avg = {}
    for k in ("heart_rate", "spo2", "temperature", "systolic", "diastolic"):
        xs = [v[k] for v in vit if v.get(k) is not None]
        if xs:
            avg[k] = round(sum(xs) / len(xs), 1)
    risks = [ml.predict(d, features) for d in ml.SPECS]
    meds = await db.medicines.find({"user_id": user["id"], "active": True}, {"_id": 0, "name": 1}).to_list(50)
    return {"profile": {k: profile.get(k) for k in ("sex", "blood_group", "height_cm", "weight_kg")}, "features": features,
            "vitals_average": avg, "risks": [{k: r[k] for k in ("disease", "title", "score", "level")} for r in risks],
            "overall": ml.overall_health_score(risks), "active_medicines": [m["name"] for m in meds],
            "conditions": [d["name"] for d in profile.get("diseases", [])]}


@router.post("/digital-twin/simulate")
async def simulate(body: TwinSim, user: dict = Depends(patient_only)):
    """What-if: change lifestyle/clinical inputs and see how every risk moves."""
    db = get_db()
    base = await _autofill(db, user["id"])
    changed = {**base, **body.changes}
    out = []
    for d in ml.SPECS:
        a, b = ml.predict(d, base), ml.predict(d, changed)
        out.append({"disease": d, "title": a["title"], "before": a["score"], "after": b["score"], "delta": b["score"] - a["score"]})
    return {"changes": body.changes, "results": out}


@router.get("/second-opinion")
async def second_opinion(user: dict = Depends(patient_only)):
    """Structured summary the patient can bring to a doctor. Rule-based; uses an LLM when configured (see chatbot)."""
    db = get_db()
    reps = await db.reports.find({"user_id": user["id"]}, {"_id": 0}).sort("ts", -1).limit(5).to_list(5)
    abnormal = [f for r in reps for f in r.get("findings", []) if f["status"] != "normal"]
    twin = await digital_twin(user)
    high = [r for r in twin["risks"] if r["level"] != "low"]
    questions = []
    for f in abnormal[:6]:
        questions.append(f"My {f['test']} is {f['status']} ({f['value']} {f['unit']}). What could be causing this and do I need follow-up tests?")
    for r in high:
        questions.append(f"My {r['title']} screening is {r['level']}. What should I do to lower it?")
    if not questions:
        questions.append("Are my check-ups and vaccinations up to date for my age?")
    specialists = sorted({s for r in high for s in {"diabetes": ["Endocrinologist"], "heart": ["Cardiologist"], "kidney": ["Nephrologist"], "liver": ["Gastroenterologist / Hepatologist"], "stroke": ["Neurologist"]}.get(r["disease"], [])})
    return {"abnormal_findings": abnormal[:10], "elevated_risks": high, "suggested_specialists": specialists, "questions_for_doctor": questions,
            "disclaimer": "A preparation aid, not a substitute for a clinician's second opinion."}
