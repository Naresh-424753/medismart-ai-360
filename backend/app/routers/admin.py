import json
import os

from fastapi import APIRouter, Depends, HTTPException

from ..common import audit, notify, now, public_user
from ..db import get_db
from ..deps import current_user, require_roles
from ..services import blobstore

router = APIRouter(prefix="/admin", tags=["admin"])
admin_only = require_roles("admin")  # super_admin passes automatically
super_only = require_roles("super_admin")


@router.get("/stats")
async def stats(user: dict = Depends(admin_only)):
    db = get_db()
    users = await db.users.find({}, {"_id": 0, "role": 1, "approved": 1, "status": 1}).to_list(100000)
    by_role: dict = {}
    for u in users:
        by_role[u["role"]] = by_role.get(u["role"], 0) + 1
    return {"users": len(users), "by_role": by_role, "pending_approvals": sum(1 for u in users if not u.get("approved")),
            "appointments": await db.appointments.count_documents({}), "open_emergencies": await db.emergency_alerts.count_documents({"status": "open"}),
            "reports": await db.reports.count_documents({}), "vitals_readings": await db.vitals.count_documents({}),
            "suspicious_logins": await db.audit_logs.count_documents({"action": "suspicious_login"})}


@router.get("/users")
async def users(role: str | None = None, pending: bool = False, q: str | None = None, user: dict = Depends(admin_only)):
    f: dict = {}
    if role:
        f["role"] = role
    if pending:
        f["approved"] = False
    rows = await get_db().users.find(f).sort("created_at", -1).limit(500).to_list(500)
    out = [public_user(u) for u in rows if not q or q.lower() in (u["name"] + u["email"]).lower()]
    return out


@router.patch("/users/{uid}")
async def update_user(uid: str, approved: bool | None = None, suspended: bool | None = None, user: dict = Depends(admin_only)):
    db = get_db()
    target = await db.users.find_one({"id": uid})
    if not target:
        raise HTTPException(404, "User not found")
    if target["role"] == "super_admin" or (target["role"] == "admin" and user["role"] != "super_admin"):
        raise HTTPException(403, "Only a super admin can change admin accounts")
    upd = {}
    if approved is not None:
        upd["approved"] = approved
    if suspended is not None:
        upd["status"] = "suspended" if suspended else "active"
    if upd:
        await db.users.update_one({"id": uid}, {"$set": upd})
        if upd.get("approved"):
            await db.hospitals.update_one({"user_id": uid}, {"$set": {"verified": True}})
            await notify(db, target, "Account approved", "Your account has been verified by the admin team.", "account")
        if "approved" in upd and not upd["approved"]:
            await db.hospitals.update_one({"user_id": uid}, {"$set": {"verified": False}})
        await audit(db, user["id"], "admin_update_user", f"{uid} {upd}")
    return {"id": uid, **upd}


# Personal data removed together with an account: (collection, field holding the user id)
_OWNED = [("medicines", "user_id"), ("med_logs", "user_id"), ("med_reminders", "user_id"), ("med_orders", "user_id"), ("notifications", "user_id"),
          ("events", "user_id"), ("reports", "user_id"), ("risk_assessments", "user_id"), ("rx_images", "user_id"), ("rx_scans", "user_id"),
          ("imaging_results", "user_id"), ("chat_history", "user_id"), ("login_history", "user_id"), ("wearable_samples", "user_id"),
          ("ews_state", "user_id"), ("ews_settings", "user_id"), ("ews_events", "user_id"), ("consents", "patient_user_id"),
          ("appointments", "patient_user_id"), ("pharmacy_stock", "user_id"), ("pharmacies", "user_id"), ("hospitals", "user_id"),
          ("doctors", "user_id"), ("patients", "user_id")]


@router.delete("/users/{uid}")
async def delete_user(uid: str, user: dict = Depends(admin_only)):
    """Permanently deletes an account and its personal data. The tamper-evident ledger and the audit log are kept on purpose."""
    db = get_db()
    target = await db.users.find_one({"id": uid})
    if not target:
        raise HTTPException(404, "User not found")
    if uid == user["id"]:
        raise HTTPException(400, "You cannot delete your own account")
    if target["role"] == "super_admin":
        raise HTTPException(403, "The super admin account cannot be deleted")
    if target["role"] == "admin" and user["role"] != "super_admin":
        raise HTTPException(403, "Only a super admin can delete admin accounts")
    pat = await db.patients.find_one({"user_id": uid}, {"_id": 0, "id": 1})
    if pat:
        for col in ("vitals", "vital_alerts", "board_cases"):
            await db[col].delete_many({"patient_id": pat["id"]})
    async for d in db.documents.find({"user_id": uid}, {"_id": 0, "id": 1}):
        blobstore.delete(uid, d["id"])
    await db.documents.delete_many({"user_id": uid})
    # a doctor's future appointments are cancelled, not erased from the patients' history
    await db.appointments.update_many({"doctor_user_id": uid, "status": {"$in": ["booked", "confirmed"]}}, {"$set": {"status": "cancelled"}})
    counts = {}
    for col, field in _OWNED:
        r = await db[col].delete_many({field: uid})
        n = getattr(r, "deleted_count", 0)
        if n:
            counts[col] = n
    await db.otps.delete_many({"email": target["email"]})
    await db.users.delete_one({"id": uid})
    await audit(db, user["id"], "admin_delete_user", f"{target['email']} ({target['role']})")
    return {"deleted": uid, "email": target["email"], "removed": counts}


@router.post("/admins")
async def create_admin(email: str, user: dict = Depends(super_only)):
    db = get_db()
    t = await db.users.find_one({"email": email.lower()})
    if not t:
        raise HTTPException(404, "User not found")
    await db.users.update_one({"id": t["id"]}, {"$set": {"role": "admin", "approved": True}})
    await audit(db, user["id"], "make_admin", email)
    return {"ok": True}


@router.get("/audit-logs")
async def audit_logs(action: str | None = None, limit: int = 200, user: dict = Depends(admin_only)):
    q = {"action": action} if action else {}
    return await get_db().audit_logs.find(q, {"_id": 0}).sort("ts", -1).limit(min(limit, 1000)).to_list(1000)


@router.get("/login-history")
async def login_history(user_id: str | None = None, user: dict = Depends(admin_only)):
    q = {"user_id": user_id} if user_id else {}
    return await get_db().login_history.find(q, {"_id": 0}).sort("ts", -1).limit(300).to_list(300)


@router.post("/backup")
async def backup(user: dict = Depends(super_only)):
    """Dumps non-sensitive collections to JSON files on the server (use mongodump for full production backups)."""
    db = get_db()
    folder = os.path.join("data", "backups", now().replace(":", "-"))
    os.makedirs(folder, exist_ok=True)
    counts = {}
    for c in ["users", "patients", "doctors", "appointments", "reports", "medicines", "hospitals", "audit_logs"]:
        rows = await db[c].find({}, {"_id": 0, "password_hash": 0}).to_list(1000000)
        with open(os.path.join(folder, c + ".json"), "w") as f:
            json.dump(rows, f, default=str)
        counts[c] = len(rows)
    await audit(db, user["id"], "backup", folder)
    return {"folder": folder, "counts": counts}


# ---- family dashboard ----
family = APIRouter(prefix="/family", tags=["family"])


@family.get("/patients")
async def family_patients(user: dict = Depends(require_roles("family"))):
    """Patients who granted this account access (via consent)."""
    db = get_db()
    out = []
    async for c in db.consents.find({"grantee_email": user["email"], "active": True}, {"_id": 0}):
        if c.get("expires") and c["expires"] < now()[:10]:
            continue
        u = await db.users.find_one({"id": c["patient_user_id"]}, {"_id": 0, "name": 1})
        out.append({"patient_user_id": c["patient_user_id"], "name": u["name"] if u else "?", "scopes": c["scopes"], "expires": c.get("expires")})
    return out
