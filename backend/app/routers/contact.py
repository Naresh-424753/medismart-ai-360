"""Public contact / help form. Anyone (even logged out) can send a message; admins read and resolve them."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from ..common import audit, new_id, notify, now
from ..config import settings
from ..db import get_db
from ..deps import require_roles

router = APIRouter(prefix="/contact", tags=["contact"])
admin_only = require_roles("admin")  # super_admin passes automatically


class ContactIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    subject: str = Field(min_length=3, max_length=120)
    message: str = Field(min_length=10, max_length=2000)
    category: str = "problem"  # problem | account | payment | feedback | other


@router.get("/info")
async def info():
    """Public support details shown on the contact page (empty unless set in backend/.env)."""
    return {"support_email": settings.SUPPORT_EMAIL, "support_phone": settings.SUPPORT_PHONE, "support_whatsapp": settings.SUPPORT_WHATSAPP}


@router.post("", status_code=201)
async def send(body: ContactIn, request: Request):
    db = get_db()
    cat = body.category if body.category in {"problem", "account", "payment", "feedback", "other"} else "other"
    doc = {"id": new_id(), "name": body.name.strip(), "email": body.email.lower(), "subject": body.subject.strip(), "message": body.message.strip(),
           "category": cat, "status": "open", "ip": request.client.host if request.client else "", "ts": now()}
    await db.contact_messages.insert_one(dict(doc))
    async for a in db.users.find({"role": {"$in": ["admin", "super_admin"]}}, {"_id": 0}):
        await notify(db, a, "New contact message", f"{doc['name']}: {doc['subject']}", "contact")
    return {"message": "Thanks, your message was sent. The team will reply by email.", "id": doc["id"]}


@router.get("/admin")
async def list_messages(status: str | None = None, user: dict = Depends(admin_only)):
    f = {"status": status} if status in {"open", "resolved"} else {}
    return await get_db().contact_messages.find(f, {"_id": 0, "ip": 0}).sort("ts", -1).limit(300).to_list(300)


@router.patch("/admin/{mid}")
async def set_status(mid: str, status: str, user: dict = Depends(admin_only)):
    if status not in {"open", "resolved"}:
        raise HTTPException(400, "status must be open or resolved")
    db = get_db()
    if not await db.contact_messages.find_one({"id": mid}):
        raise HTTPException(404, "Message not found")
    await db.contact_messages.update_one({"id": mid}, {"$set": {"status": status, "handled_by": user["id"], "handled_at": now()}})
    await audit(db, user["id"], "contact_" + status, mid)
    return {"id": mid, "status": status}
