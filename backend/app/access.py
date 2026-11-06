"""Who may see a patient's data? Patient himself; a doctor with a non-cancelled appointment or an active consent;
a family member / any grantee with an active consent covering the scope."""
from .common import now
from .services import ledger


async def can_access(db, viewer: dict, patient_user_id: str, scope: str = "summary") -> bool:
    ok = await _can_access(db, viewer, patient_user_id, scope)
    if ok and viewer["id"] != patient_user_id:  # every third-party read is recorded on the patient's ledger
        await ledger.append(db, patient_user_id, "access_event", {"viewer_role": viewer["role"], "scope": scope}, actor=viewer["id"])
    return ok


async def _can_access(db, viewer: dict, patient_user_id: str, scope: str = "summary") -> bool:
    if viewer["id"] == patient_user_id:
        return True
    if viewer["role"] in ("doctor",):
        appt = await db.appointments.find_one({"patient_user_id": patient_user_id, "doctor_user_id": viewer["id"], "status": {"$ne": "cancelled"}})
        if appt:
            return True
    q = {"patient_user_id": patient_user_id, "grantee_email": viewer["email"], "active": True}
    async for c in db.consents.find(q, {"_id": 0}):
        if scope in c["scopes"] and (not c.get("expires") or c["expires"] >= now()[:10]):
            return True
    return False
