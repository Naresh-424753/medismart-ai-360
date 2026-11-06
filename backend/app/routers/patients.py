import os
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import crypto
from ..access import can_access
from ..services import blobstore, ledger
from ..common import audit, clean, log_event, new_id, now
from ..config import settings
from ..db import get_db
from ..deps import current_user, require_roles

router = APIRouter(prefix="/patients", tags=["patients"])
patient_only = require_roles("patient")

BLOOD_GROUPS = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
RECORD_KINDS = {"allergies", "diseases", "surgeries", "vaccinations", "emergency_contacts"}
RECORD_FIELDS = {
    "allergies": {"name", "severity", "reaction"},
    "diseases": {"name", "since", "status", "notes"},
    "surgeries": {"name", "date", "hospital", "notes"},
    "vaccinations": {"name", "date", "dose", "next_due"},
    "emergency_contacts": {"name", "relation", "phone", "email"},
}
ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".txt", ".dcm"}
SCOPES = {"summary", "vitals", "reports", "documents", "medicines"}


class ProfileIn(BaseModel):
    dob: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    sex: str | None = None
    blood_group: str | None = None
    height_cm: float | None = Field(default=None, gt=30, lt=260)
    weight_kg: float | None = Field(default=None, gt=1, lt=500)
    address: str | None = None
    city: str | None = None
    phone: str | None = None


class RecordIn(BaseModel):
    data: dict


class FamilyIn(BaseModel):
    name: str
    relation: str
    dob: str | None = None
    blood_group: str | None = None
    notes: str = ""


class ConsentIn(BaseModel):
    grantee_email: str
    scopes: list[str] = ["summary"]
    expires: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


async def get_profile(db, user_id: str) -> dict:
    p = await db.patients.find_one({"user_id": user_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Patient profile not found")
    return p


def age_from_dob(dob: str | None) -> int | None:
    if not dob:
        return None
    from datetime import date
    y, m, d = map(int, dob.split("-"))
    t = date.today()
    return t.year - y - ((t.month, t.day) < (m, d))


@router.get("/me")
async def my_profile(user: dict = Depends(patient_only)):
    p = await get_profile(get_db(), user["id"])
    p["name"], p["email"], p["phone"] = user["name"], user["email"], user.get("phone", "")
    p["age"] = age_from_dob(p.get("dob"))
    return p


@router.put("/me")
async def update_profile(body: ProfileIn, user: dict = Depends(patient_only)):
    db = get_db()
    data = body.model_dump(exclude_none=True)
    if "blood_group" in data and data["blood_group"] not in BLOOD_GROUPS:
        raise HTTPException(400, f"Blood group must be one of {sorted(BLOOD_GROUPS)}")
    if "sex" in data and data["sex"].lower() not in {"male", "female", "other"}:
        raise HTTPException(400, "Sex must be male, female or other")
    if "phone" in data:
        await db.users.update_one({"id": user["id"]}, {"$set": {"phone": data.pop("phone")}})
    if data:
        await db.patients.update_one({"user_id": user["id"]}, {"$set": data})
    await log_event(db, user["id"], "profile", "Profile updated")
    return await my_profile(user)


@router.post("/me/records/{kind}", status_code=201)
async def add_record(kind: str, body: RecordIn, user: dict = Depends(patient_only)):
    if kind not in RECORD_KINDS:
        raise HTTPException(404, "Unknown record type")
    data = {k: str(v)[:300] for k, v in body.data.items() if k in RECORD_FIELDS[kind]}
    if not data.get("name"):
        raise HTTPException(400, "'name' is required")
    item = {"id": new_id(), **data}
    db = get_db()
    await db.patients.update_one({"user_id": user["id"]}, {"$push": {kind: item}})
    await log_event(db, user["id"], kind, f"Added {kind.rstrip('s').replace('_', ' ')}: {data['name']}")
    return item


@router.delete("/me/records/{kind}/{item_id}")
async def delete_record(kind: str, item_id: str, user: dict = Depends(patient_only)):
    if kind not in RECORD_KINDS:
        raise HTTPException(404, "Unknown record type")
    await get_db().patients.update_one({"user_id": user["id"]}, {"$pull": {kind: {"id": item_id}}})
    return {"deleted": item_id}


@router.get("/me/timeline")
async def timeline(limit: int = 100, user: dict = Depends(patient_only)):
    cur = get_db().events.find({"user_id": user["id"]}, {"_id": 0}).sort("ts", -1).limit(min(limit, 300))
    return await cur.to_list(300)


@router.get("/me/notifications")
async def notifications(user: dict = Depends(current_user)):
    cur = get_db().notifications.find({"user_id": user["id"]}, {"_id": 0}).sort("ts", -1).limit(50)
    return await cur.to_list(50)


@router.post("/me/notifications/read")
async def mark_read(user: dict = Depends(current_user)):
    await get_db().notifications.update_many({"user_id": user["id"]}, {"$set": {"read": True}})
    return {"ok": True}


# ---- family members (dependants managed by the patient) ----
@router.get("/me/family")
async def list_family(user: dict = Depends(patient_only)):
    return await get_db().family_members.find({"owner_id": user["id"]}, {"_id": 0}).to_list(100)


@router.post("/me/family", status_code=201)
async def add_family(body: FamilyIn, user: dict = Depends(patient_only)):
    doc = {"id": new_id(), "owner_id": user["id"], **body.model_dump(), "created_at": now()}
    await get_db().family_members.insert_one(dict(doc))
    return clean(doc)


@router.delete("/me/family/{fid}")
async def delete_family(fid: str, user: dict = Depends(patient_only)):
    await get_db().family_members.delete_one({"id": fid, "owner_id": user["id"]})
    return {"deleted": fid}


# ---- consent management ----
@router.get("/me/consents")
async def list_consents(user: dict = Depends(patient_only)):
    return await get_db().consents.find({"patient_user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)


@router.post("/me/consents", status_code=201)
async def grant_consent(body: ConsentIn, user: dict = Depends(patient_only)):
    scopes = [s for s in body.scopes if s in SCOPES]
    if not scopes:
        raise HTTPException(400, f"scopes must be from {sorted(SCOPES)}")
    db = get_db()
    doc = {"id": new_id(), "patient_user_id": user["id"], "grantee_email": body.grantee_email.lower(), "scopes": scopes,
           "expires": body.expires, "active": True, "created_at": now()}
    await db.consents.insert_one(dict(doc))
    await audit(db, user["id"], "consent_grant", f"{doc['grantee_email']} {scopes}")
    await log_event(db, user["id"], "consent", f"Granted access to {doc['grantee_email']}", {"scopes": scopes})
    await ledger.append(db, user["id"], "access_grant", {"grantee": doc["grantee_email"], "scopes": scopes, "expires": body.expires}, actor=user["id"])
    return clean(doc)


@router.delete("/me/consents/{cid}")
async def revoke_consent(cid: str, user: dict = Depends(patient_only)):
    db = get_db()
    await db.consents.update_one({"id": cid, "patient_user_id": user["id"]}, {"$set": {"active": False, "revoked_at": now()}})
    await audit(db, user["id"], "consent_revoke", cid)
    c = await db.consents.find_one({"id": cid, "patient_user_id": user["id"]})
    if c:
        await ledger.append(db, user["id"], "access_revoke", {"grantee": c["grantee_email"], "consent_id": cid}, actor=user["id"])
    return {"revoked": cid}


# ---- documents (encrypted at rest) ----
@router.post("/me/documents", status_code=201)
async def upload_document(file: UploadFile = File(...), title: str = Form(""), category: str = Form("report"), user: dict = Depends(patient_only)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Allowed file types: {sorted(ALLOWED_EXT)}")
    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File too large (max {settings.MAX_UPLOAD_MB} MB)")
    did = new_id()
    blobstore.put(user["id"], did, crypto.encrypt(data))
    db = get_db()
    doc = {"id": did, "user_id": user["id"], "title": title or file.filename, "category": category[:40], "filename": re.sub(r"[^\w.\- ]", "_", file.filename or "file"),
           "ext": ext, "size": len(data), "content_type": file.content_type or "application/octet-stream", "created_at": now()}
    await db.documents.insert_one(dict(doc))
    await log_event(db, user["id"], "document", f"Uploaded document: {doc['title']}")
    await ledger.append(db, user["id"], "document", {"document_id": did, "sha256": ledger.sha256_hex(data), "title": doc["title"][:80]}, actor=user["id"])
    return clean(doc)


@router.get("/me/documents")
async def list_documents(user: dict = Depends(patient_only)):
    return await get_db().documents.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.get("/documents/{did}/download")
async def download_document(did: str, user: dict = Depends(current_user)):
    db = get_db()
    doc = await db.documents.find_one({"id": did}, {"_id": 0})
    if not doc or not await can_access(db, user, doc["user_id"], "documents"):
        raise HTTPException(404, "Document not found")
    raw = blobstore.get(doc["user_id"], did)
    if raw is None:
        raise HTTPException(404, "File missing")
    data = crypto.decrypt(raw)
    await audit(db, user["id"], "document_download", did)
    return Response(data, media_type=doc["content_type"], headers={"Content-Disposition": f'attachment; filename="{doc["filename"]}"'})


@router.delete("/me/documents/{did}")
async def delete_document(did: str, user: dict = Depends(patient_only)):
    db = get_db()
    doc = await db.documents.find_one({"id": did, "user_id": user["id"]})
    if doc:
        blobstore.delete(user["id"], did)
        await db.documents.delete_one({"id": did})
    return {"deleted": did}


# ---- shared views (doctor / family with access) ----
@router.get("/{patient_user_id}/summary")
async def patient_summary(patient_user_id: str, user: dict = Depends(current_user)):
    db = get_db()
    if not await can_access(db, user, patient_user_id, "summary"):
        raise HTTPException(403, "You don't have access to this patient")
    p = await get_profile(db, patient_user_id)
    u = await db.users.find_one({"id": patient_user_id}, {"_id": 0, "name": 1, "email": 1, "phone": 1})
    meds = await db.medicines.find({"user_id": patient_user_id, "active": True}, {"_id": 0}).to_list(100) if await can_access(db, user, patient_user_id, "medicines") else []
    risks = await db.risk_assessments.find({"user_id": patient_user_id}, {"_id": 0}).sort("ts", -1).limit(10).to_list(10)
    p.pop("qr_token", None)
    await audit(db, user["id"], "patient_summary_view", patient_user_id)
    return {"patient": {**p, **u, "age": age_from_dob(p.get("dob"))}, "medicines": meds, "recent_risks": risks}


@router.get("/{patient_user_id}/reports")
async def patient_reports(patient_user_id: str, user: dict = Depends(current_user)):
    db = get_db()
    if not await can_access(db, user, patient_user_id, "reports"):
        raise HTTPException(403, "You don't have access to this patient's reports")
    return await db.reports.find({"user_id": patient_user_id}, {"_id": 0}).sort("ts", -1).limit(50).to_list(50)


@router.get("/{patient_user_id}/documents")
async def patient_documents(patient_user_id: str, user: dict = Depends(current_user)):
    db = get_db()
    if not await can_access(db, user, patient_user_id, "documents"):
        raise HTTPException(403, "You don't have access to this patient's documents")
    return await db.documents.find({"user_id": patient_user_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
