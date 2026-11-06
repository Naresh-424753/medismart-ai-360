"""Doctor <-> patient secure messaging. Only people who share a non-cancelled appointment may chat."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..common import new_id, notify, now
from ..db import get_db
from ..deps import require_roles

router = APIRouter(prefix="/messages", tags=["messaging"])
party = require_roles("patient", "doctor")


class MsgIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


async def _check_link(db, me: dict, other_id: str) -> dict:
    q = ({"patient_user_id": me["id"], "doctor_user_id": other_id} if me["role"] == "patient"
         else {"doctor_user_id": me["id"], "patient_user_id": other_id})
    q["status"] = {"$ne": "cancelled"}
    a = await db.appointments.find_one(q, {"_id": 0})
    other = await db.users.find_one({"id": other_id}, {"_id": 0, "password_hash": 0})
    if not a or not other:
        raise HTTPException(403, "You can chat only with a doctor/patient you have an appointment with")
    return other


@router.get("/threads")
async def threads(user: dict = Depends(party)):
    db = get_db()
    field, other_field, name_field = (("patient_user_id", "doctor_user_id", "doctor_name") if user["role"] == "patient"
                                      else ("doctor_user_id", "patient_user_id", "patient_name"))
    people: dict = {}
    for a in await db.appointments.find({field: user["id"], "status": {"$ne": "cancelled"}}, {"_id": 0}).to_list(2000):
        people[a[other_field]] = a[name_field]
    out = []
    for oid, name in people.items():
        msgs = await db.messages.find({"pair": sorted([user["id"], oid])}, {"_id": 0}).sort("ts", -1).limit(1).to_list(1)
        unread = await db.messages.count_documents({"from": oid, "to": user["id"], "read": False})
        out.append({"user_id": oid, "name": name, "last": msgs[0] if msgs else None, "unread": unread})
    return sorted(out, key=lambda t: (t["last"] or {}).get("ts", ""), reverse=True)


@router.get("/{other_id}")
async def history(other_id: str, user: dict = Depends(party)):
    db = get_db()
    await _check_link(db, user, other_id)
    await db.messages.update_many({"from": other_id, "to": user["id"], "read": False}, {"$set": {"read": True}})
    return await db.messages.find({"pair": sorted([user["id"], other_id])}, {"_id": 0, "pair": 0}).sort("ts", 1).limit(500).to_list(500)


@router.post("/{other_id}", status_code=201)
async def send(other_id: str, body: MsgIn, user: dict = Depends(party)):
    db = get_db()
    other = await _check_link(db, user, other_id)
    m = {"id": new_id(), "pair": sorted([user["id"], other_id]), "from": user["id"], "to": other_id, "text": body.text.strip(), "ts": now(), "read": False}
    await db.messages.insert_one(dict(m))
    await notify(db, other, f"New message from {user['name']}", body.text.strip()[:120], "message")
    m.pop("_id", None)
    m.pop("pair")
    return m
