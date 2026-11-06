import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..common import log_event, new_id, notify, now
from ..db import get_db
from ..deps import current_user, require_roles
from ..services import report_analyzer as ra

router = APIRouter(prefix="/reports", tags=["reports"])
patient_only = require_roles("patient")


class AnalyzeIn(BaseModel):
    text: str = ""
    values: dict[str, float] = {}
    title: str = "Lab report"
    report_date: str | None = None


async def _store(db, user: dict, values: dict, title: str, report_date: str | None, source: str, text: str = "") -> dict:
    profile = await db.patients.find_one({"user_id": user["id"]}, {"_id": 0}) or {}
    result = ra.analyze(values, profile.get("sex"))
    prev_docs = await db.reports.find({"user_id": user["id"]}, {"_id": 0}).sort("ts", -1).limit(10).to_list(10)
    prev_vals: dict = {}
    for d in reversed(prev_docs):
        prev_vals.update(d.get("values", {}))
    comparison = ra.compare(values, prev_vals)
    doc = {"id": new_id(), "user_id": user["id"], "title": title, "report_date": report_date or now()[:10], "source": source,
           "categories": ra.detect_categories(values), "values": values, "findings": result["findings"], "summary": result["summary"],
           "abnormal_count": result["abnormal_count"], "comparison": comparison, "ts": now()}
    await db.reports.insert_one(dict(doc))
    await log_event(db, user["id"], "report", f"{title}: {result['abnormal_count']} abnormal value(s)", {"report_id": doc["id"]})
    if result["abnormal_count"]:
        await notify(db, user, "Abnormal report values", result["summary"], "report")
        from .board import maybe_auto_case
        await maybe_auto_case(db, user["id"])
    doc.pop("_id", None)
    doc["disclaimer"] = result["disclaimer"]
    return doc


@router.post("/analyze")
async def analyze_text(body: AnalyzeIn, user: dict = Depends(patient_only)):
    values = {k: v for k, v in body.values.items() if k in ra.REFS}
    if body.text.strip():
        values = {**ra.extract_values(body.text), **values}
    if not values:
        raise HTTPException(422, "No recognisable test values found. Paste lines like 'Hemoglobin 11.2 g/dL' or send 'values'.")
    return await _store(get_db(), user, values, body.title, body.report_date, "text", body.text)


@router.post("/upload")
async def analyze_file(file: UploadFile = File(...), title: str = Form("Uploaded report"), user: dict = Depends(patient_only)):
    """PDF (text layer) or image (OCR via Tesseract). If OCR is unavailable the error says so."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 10 MB)")
    try:
        if ext == ".pdf":
            text = ra.pdf_text(data)
            if len(text.strip()) < 20:
                raise RuntimeError("This PDF has no text layer (scanned). Upload it as an image so OCR can read it.")
        elif ext in {".png", ".jpg", ".jpeg", ".bmp", ".tiff"}:
            text = ra.ocr_image_bytes(data)
        elif ext == ".txt":
            text = data.decode("utf-8", "ignore")
        else:
            raise HTTPException(400, "Upload a PDF, image (png/jpg) or txt file")
    except RuntimeError as e:
        raise HTTPException(422, str(e))
    values = ra.extract_values(text)
    if not values:
        raise HTTPException(422, "Text was read but no known lab values were recognised. Try pasting the text manually.")
    out = await _store(get_db(), user, values, title, None, "upload:" + ext, text)
    out["extracted_text_preview"] = text[:500]
    return out


@router.get("")
async def list_reports(user: dict = Depends(patient_only)):
    return await get_db().reports.find({"user_id": user["id"]}, {"_id": 0}).sort("ts", -1).limit(100).to_list(100)


@router.get("/reference")
async def reference(user: dict = Depends(current_user)):
    return {k: {"name": v["name"], "unit": v["unit"], "low": v["low"], "high": v["high"]} for k, v in ra.REFS.items()}


@router.get("/trend/{test}")
async def trend(test: str, user: dict = Depends(patient_only)):
    if test not in ra.REFS:
        raise HTTPException(404, "Unknown test")
    docs = await get_db().reports.find({"user_id": user["id"], f"values.{test}": {"$exists": True}}, {"_id": 0}).sort("ts", 1).limit(200).to_list(200)
    r = ra.REFS[test]
    return {"test": r["name"], "unit": r["unit"], "low": r["low"], "high": r["high"],
            "points": [{"date": d["report_date"], "ts": d["ts"], "value": d["values"][test]} for d in docs]}


@router.get("/{rid}")
async def get_report(rid: str, user: dict = Depends(patient_only)):
    d = await get_db().reports.find_one({"id": rid, "user_id": user["id"]}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Report not found")
    return d
