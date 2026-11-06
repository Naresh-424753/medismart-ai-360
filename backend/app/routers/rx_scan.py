"""Automated prescription OCR with mandatory verification: scan -> parse -> patient edits -> doctor/pharmacist verifies -> reminders."""
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import crypto
from ..common import log_event, new_id, notify, now
from ..db import get_db
from ..deps import current_user, require_roles
from ..services import drugs, ledger, report_analyzer, rx_parser
from .medicines import MedIn, add_med

router = APIRouter(prefix="/rx-scan", tags=["prescription OCR"])
patient_only = require_roles("patient")
reviewer = require_roles("doctor", "pharmacist")
TIME_RE = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


class ItemIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    dose: str = Field(default="", max_length=40)
    times: list[str] = Field(default=["08:00"], min_length=1, max_length=6)
    duration_days: int = Field(default=5, ge=1, le=730)
    instructions: str = Field(default="", max_length=200)


class ItemsIn(BaseModel):
    items: list[ItemIn] = Field(min_length=1, max_length=30)


class ReviewIn(BaseModel):
    approve: bool
    note: str = Field(default="", max_length=500)
    items: list[ItemIn] | None = None  # reviewer may correct items


def _check(items: list[ItemIn]):
    for it in items:
        if not all(TIME_RE.fullmatch(t) for t in it.times):
            raise HTTPException(400, f"Invalid time in '{it.name}'. Use HH:MM (24 hour).")


async def _warn(db, user_id: str, names: list[str]) -> list[str]:
    prof = await db.patients.find_one({"user_id": user_id}, {"_id": 0}) or {}
    allergies = [a["name"] for a in prof.get("allergies", [])]
    out = [a["message"] for n in names for a in drugs.check_allergies(n, allergies)]
    return out + [f"{x['drugs'][0]} + {x['drugs'][1]}: {x['message']}" for x in drugs.check_interactions(names)]


async def _get(db, sid: str, user: dict, reviewer_ok=False) -> dict:
    d = await db.rx_scans.find_one({"id": sid}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Scan not found")
    if d["user_id"] == user["id"]:
        return d
    if reviewer_ok and user["role"] in ("doctor", "pharmacist") and d["status"] in ("pending_verification", "verified", "rejected"):
        return d
    raise HTTPException(404, "Scan not found")


@router.post("/upload", status_code=201)
async def upload(file: UploadFile = File(...), user: dict = Depends(patient_only)):
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 10 MB)")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(400, "Upload a photo (JPEG/PNG) of the prescription")
    try:
        text = rx_parser.preprocess_ocr(data)
    except Exception as e:
        raise HTTPException(422, f"OCR is not available on the server ({str(e)[:120]}). Install tesseract-ocr or enter medicines manually.")
    items = rx_parser.parse(text)
    db = get_db()
    sid = new_id()
    folder_key = f"rx_{sid}"
    await db.rx_images.insert_one({"id": sid, "user_id": user["id"], "blob": crypto.encrypt(data), "content_type": file.content_type, "key": folder_key})
    doc = {"id": sid, "user_id": user["id"], "patient_name": user["name"], "status": "draft", "text": text[:4000], "items": items,
           "warnings": await _warn(db, user["id"], [i["name"] for i in items]), "created_at": now(), "reviewed_by": None, "review_note": ""}
    await db.rx_scans.insert_one(dict(doc))
    doc.pop("_id", None)
    return {**doc, "note": "Draft only. Check every item against the paper prescription, then send it for doctor/pharmacist verification. Handwriting is often misread."}


@router.get("")
async def mine(user: dict = Depends(patient_only)):
    return await get_db().rx_scans.find({"user_id": user["id"]}, {"_id": 0, "text": 0}).sort("created_at", -1).to_list(100)


@router.get("/queue")
async def queue(user: dict = Depends(reviewer)):
    if not user.get("approved", False):
        raise HTTPException(403, "Your account is pending verification")
    return await get_db().rx_scans.find({"status": "pending_verification"}, {"_id": 0}).sort("created_at", 1).to_list(200)


@router.get("/{sid}")
async def one(sid: str, user: dict = Depends(current_user)):
    return await _get(get_db(), sid, user, reviewer_ok=True)


@router.get("/{sid}/image")
async def image(sid: str, user: dict = Depends(current_user)):
    from fastapi.responses import Response
    db = get_db()
    d = await _get(db, sid, user, reviewer_ok=True)
    img = await db.rx_images.find_one({"id": sid})
    if not img:
        raise HTTPException(404, "Image not found")
    if d["user_id"] != user["id"]:
        await ledger.append(db, d["user_id"], "access_event", {"viewer_role": user["role"], "scope": "prescription_scan"}, actor=user["id"])
    return Response(crypto.decrypt(img["blob"]), media_type=img.get("content_type") or "image/jpeg", headers={"Cache-Control": "no-store"})


@router.put("/{sid}")
async def edit(sid: str, body: ItemsIn, user: dict = Depends(patient_only)):
    db = get_db()
    d = await _get(db, sid, user)
    if d["status"] == "activated":
        raise HTTPException(400, "Already activated")
    _check(body.items)
    items = [{**i.model_dump(), "canonical": drugs.canon(i.name), "in_database": bool(drugs.canon(i.name)), "confidence": 1.0, "review_flags": []} for i in body.items]
    upd = {"items": items, "status": "draft", "warnings": await _warn(db, user["id"], [i["name"] for i in items]), "reviewed_by": None}
    await db.rx_scans.update_one({"id": sid}, {"$set": upd})
    return {**d, **upd}  # editing resets verification


@router.post("/{sid}/request-verification")
async def request_verification(sid: str, user: dict = Depends(patient_only)):
    db = get_db()
    d = await _get(db, sid, user)
    if d["status"] not in ("draft", "rejected"):
        raise HTTPException(400, f"Cannot request verification when status is {d['status']}")
    if not d["items"]:
        raise HTTPException(400, "No medicines found. Add them manually first.")
    await db.rx_scans.update_one({"id": sid}, {"$set": {"status": "pending_verification", "requested_at": now()}})
    return {"status": "pending_verification"}


@router.post("/{sid}/review")
async def review(sid: str, body: ReviewIn, user: dict = Depends(reviewer)):
    if not user.get("approved", False):
        raise HTTPException(403, "Your account is pending verification")
    db = get_db()
    d = await _get(db, sid, user, reviewer_ok=True)
    if d["status"] != "pending_verification":
        raise HTTPException(400, f"Scan is {d['status']}, not pending")
    upd: dict = {"reviewed_by": {"id": user["id"], "name": user["name"], "role": user["role"]}, "review_note": body.note, "reviewed_at": now()}
    if body.approve:
        items = d["items"]
        if body.items:
            _check(body.items)
            items = [{**i.model_dump(), "canonical": drugs.canon(i.name), "in_database": bool(drugs.canon(i.name)), "confidence": 1.0, "review_flags": []} for i in body.items]
        upd.update(status="verified", items=items, warnings=await _warn(db, d["user_id"], [i["name"] for i in items]))
        await ledger.append(db, d["user_id"], "prescription_scan_verified", {"scan_id": sid, "items_sha256": ledger.sha256_hex(str([(i["name"], i["dose"], i["times"], i["duration_days"]) for i in items]).encode()),
                                                                            "reviewer_role": user["role"]}, actor=user["id"])
    else:
        upd["status"] = "rejected"
    await db.rx_scans.update_one({"id": sid}, {"$set": upd})
    pu = await db.users.find_one({"id": d["user_id"]})
    await notify(db, pu, "Prescription scan " + ("verified" if body.approve else "needs changes"), body.note or "Open Prescription Scanner to continue.", "prescription")
    return {"status": upd["status"]}


@router.post("/{sid}/activate")
async def activate(sid: str, user: dict = Depends(patient_only)):
    """Creates medicine reminders. Allowed ONLY after a doctor/pharmacist verified the items."""
    db = get_db()
    d = await _get(db, sid, user)
    if d["status"] != "verified":
        raise HTTPException(403, "A doctor or pharmacist must verify this prescription before reminders are created")
    created = [await add_med(MedIn(name=i["name"], dose=i["dose"], times=i["times"], duration_days=i["duration_days"], instructions=i["instructions"]), user) for i in d["items"]]
    await db.rx_scans.update_one({"id": sid}, {"$set": {"status": "activated", "activated_at": now()}})
    await log_event(db, user["id"], "prescription", f"{len(created)} medicine reminder(s) created from a verified prescription scan")
    return {"created": len(created), "medicines": created}
