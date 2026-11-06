import asyncio
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from ..common import _send_email, audit, clean, new_id, notify, now, public_user
from ..config import settings
from ..db import get_db
from ..deps import client_ip, current_user
from ..security import create_token, hash_otp, hash_password, new_otp, password_problem, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

SELF_SIGNUP_ROLES = {"patient", "doctor", "hospital", "lab", "pharmacist", "blood_bank", "ambulance", "family"}
NEEDS_APPROVAL = {"doctor", "hospital", "lab", "pharmacist", "blood_bank", "ambulance"}
OTP_TTL_MIN, OTP_MAX_ATTEMPTS, MAX_FAILED, LOCK_MIN = 10, 5, 5, 15


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    phone: str = Field(default="", max_length=20)
    password: str
    role: str = "patient"
    specialization: str | None = None
    license_no: str | None = None
    organization: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class OtpIn(BaseModel):
    email: EmailStr
    otp: str
    purpose: str = "register"  # register | login


class EmailIn(BaseModel):
    email: EmailStr
    purpose: str = "register"


class ResetIn(BaseModel):
    email: EmailStr
    otp: str
    new_password: str


class ChangePwIn(BaseModel):
    old_password: str
    new_password: str
    otp: str = ""


async def _issue_otp(db, user: dict, purpose: str) -> str:
    otp = new_otp()
    exp = (datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MIN)).isoformat(timespec="seconds")
    await db.otps.update_one({"email": user["email"], "purpose": purpose},
                             {"$set": {"hash": hash_otp(user["email"], purpose, otp), "expires": exp, "attempts": 0}}, upsert=True)
    # OTPs go by email only, and are never stored as an in-app notification.
    if settings.SMTP_HOST:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _send_email, user["email"], "Your MediSmart verification code",
                                                             f"Your OTP is {otp}. It is valid for {OTP_TTL_MIN} minutes. Do not share it.")
        except Exception as e:
            logging.getLogger("medismart.auth").error("OTP email failed: %s", e)
            if not settings.DEV_MODE:
                raise HTTPException(503, "Could not send the OTP email. Check the SMTP settings.")
    elif settings.DEV_MODE:
        # Never sent to the browser: only visible to whoever runs the server.
        logging.getLogger("medismart.auth").warning("DEV_MODE, SMTP not set -> OTP for %s (%s): %s", user["email"], purpose, otp)
    else:
        raise HTTPException(503, "Email is not configured (set SMTP_HOST, SMTP_USER, SMTP_PASS in backend/.env).")
    return otp


async def _check_otp(db, email: str, purpose: str, otp: str):
    rec = await db.otps.find_one({"email": email, "purpose": purpose})
    if not rec:
        raise HTTPException(400, "No OTP requested")
    if rec["attempts"] >= OTP_MAX_ATTEMPTS:
        raise HTTPException(429, "Too many attempts. Request a new OTP.")
    if rec["expires"] < now():
        raise HTTPException(400, "OTP expired. Request a new one.")
    if rec["hash"] != hash_otp(email, purpose, otp.strip()):
        await db.otps.update_one({"email": email, "purpose": purpose}, {"$inc": {"attempts": 1}})
        raise HTTPException(400, "Incorrect OTP")
    await db.otps.delete_one({"email": email, "purpose": purpose})


def _health_id() -> str:
    return "MS" + "".join(str(secrets.randbelow(10)) for _ in range(12))


@router.post("/register", status_code=201)
async def register(body: RegisterIn, request: Request):
    db = get_db()
    if body.role not in SELF_SIGNUP_ROLES:
        raise HTTPException(400, f"Role must be one of {sorted(SELF_SIGNUP_ROLES)}")
    if (p := password_problem(body.password)):
        raise HTTPException(400, p)
    email = body.email.lower()
    existing = await db.users.find_one({"email": email})
    if existing and existing.get("email_verified"):
        raise HTTPException(409, "An account with this email already exists")
    if existing:  # never verified (typo, lost code): let the owner start again instead of being locked out
        for col in ("patients", "doctors"):
            await db[col].delete_many({"user_id": existing["id"]})
        await db.users.delete_one({"id": existing["id"]})
    uid = new_id()
    user = {"id": uid, "name": body.name.strip(), "email": email, "phone": body.phone, "role": body.role,
            "password_hash": hash_password(body.password), "email_verified": False,
            "approved": body.role not in NEEDS_APPROVAL, "status": "active", "two_factor": False,
            "organization": body.organization, "created_at": now()}
    await db.users.insert_one(dict(user))
    if body.role == "patient":
        await db.patients.insert_one({"id": new_id(), "user_id": uid, "health_id": _health_id(), "qr_token": secrets.token_urlsafe(16),
                                      "dob": None, "sex": None, "blood_group": None, "height_cm": None, "weight_kg": None, "address": "", "city": "",
                                      "allergies": [], "diseases": [], "surgeries": [], "vaccinations": [], "emergency_contacts": []})
    if body.role == "doctor":
        await db.doctors.insert_one({"id": new_id(), "user_id": uid, "name": body.name, "specialization": body.specialization or "General Physician",
                                     "license_no": body.license_no, "experience_years": 0, "fee": 500, "bio": "", "hospital": body.organization or "", "city": "",
                                     "availability": {"days": [0, 1, 2, 3, 4], "slots": ["10:00", "10:30", "11:00", "11:30", "12:00", "15:00", "15:30", "16:00"]},
                                     "rating": 0, "rating_count": 0})
    try:
        await _issue_otp(db, user, "register")
    except HTTPException:  # the verification email could not be sent: do not leave a half-created account behind
        for col in ("patients", "doctors"):
            await db[col].delete_many({"user_id": uid})
        await db.users.delete_one({"id": uid})
        raise
    await audit(db, uid, "register", body.role, client_ip(request))
    out = {"message": "Registered. Enter the OTP sent to your email to verify.", "email": email}
    if body.role in NEEDS_APPROVAL:
        out["note"] = "Your account needs admin approval before professional features are enabled."
    return out


@router.post("/resend-otp")
async def resend_otp(body: EmailIn):
    db = get_db()
    user = await db.users.find_one({"email": body.email.lower()})
    out = {"message": "If the account exists, an OTP has been sent."}
    purpose = body.purpose if body.purpose in ("register", "login") else "register"
    if user and not (purpose == "register" and user.get("email_verified")):
        await _issue_otp(db, user, purpose)
    return out


def _login_response(user: dict, token: str) -> dict:
    return {"token": token, "token_type": "bearer", "user": public_user(user)}


async def _finish_login(db, user: dict, request: Request) -> dict:
    ip, ua = client_ip(request), request.headers.get("user-agent", "")[:200]
    seen = await db.login_history.find_one({"user_id": user["id"], "ip": ip, "success": True})
    first_ever = not await db.login_history.find_one({"user_id": user["id"], "success": True})
    await db.login_history.insert_one({"id": new_id(), "user_id": user["id"], "ip": ip, "ua": ua, "success": True, "ts": now()})
    await db.users.update_one({"id": user["id"]}, {"$set": {"failed_logins": 0, "locked_until": None, "last_login": now()}})
    if not seen and not first_ever:
        await notify(db, user, "New login location", f"New sign-in from {ip or 'unknown IP'}. If this wasn't you, change your password.", "security", ("app", "email"))
        await audit(db, user["id"], "suspicious_login", f"new ip {ip}", ip)
    token, _ = create_token(user["id"], user["role"])
    await audit(db, user["id"], "login", "", ip)
    return _login_response(user, token)


@router.post("/login")
async def login(body: LoginIn, request: Request):
    db = get_db()
    email, ip = body.email.lower(), client_ip(request)
    user = await db.users.find_one({"email": email})
    generic = HTTPException(401, "Incorrect email or password")
    if not user:
        raise generic
    if user.get("locked_until") and user["locked_until"] > now():
        raise HTTPException(423, "Account temporarily locked after repeated failures. Try again later.")
    if not verify_password(body.password, user["password_hash"]):
        fails = user.get("failed_logins", 0) + 1
        upd = {"failed_logins": fails}
        if fails >= MAX_FAILED:
            upd["locked_until"] = (datetime.now(timezone.utc) + timedelta(minutes=LOCK_MIN)).isoformat(timespec="seconds")
            upd["failed_logins"] = 0
        await db.users.update_one({"id": user["id"]}, {"$set": upd})
        await db.login_history.insert_one({"id": new_id(), "user_id": user["id"], "ip": ip, "ua": "", "success": False, "ts": now()})
        raise generic
    if user.get("status") == "suspended":
        raise HTTPException(403, "Account suspended")
    if not user.get("email_verified"):
        raise HTTPException(403, "Please verify your OTP first (use /auth/resend-otp if it expired)")
    if user.get("two_factor"):
        otp = await _issue_otp(db, user, "login")
        out = {"requires_otp": True, "message": "Enter the OTP sent to you to finish logging in."}
        return out
    return await _finish_login(db, user, request)


@router.post("/verify-otp")
async def verify_otp(body: OtpIn, request: Request):
    db = get_db()
    email = body.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or body.purpose not in ("register", "login"):
        raise HTTPException(400, "Invalid request")
    await _check_otp(db, email, body.purpose, body.otp)
    if body.purpose == "register":
        await db.users.update_one({"id": user["id"]}, {"$set": {"email_verified": True}})
        return {"message": "Verified. You can now log in.", "verified": True}
    return await _finish_login(db, user, request)


@router.post("/forgot-password")
async def forgot_password(body: EmailIn):
    db = get_db()
    user = await db.users.find_one({"email": body.email.lower()})
    out = {"message": "If the account exists, a reset OTP has been sent."}
    if user:
        otp = await _issue_otp(db, user, "reset")
    return out


@router.post("/reset-password")
async def reset_password(body: ResetIn):
    db = get_db()
    if (p := password_problem(body.new_password)):
        raise HTTPException(400, p)
    email = body.email.lower()
    user = await db.users.find_one({"email": email})
    if not user:
        raise HTTPException(400, "Invalid request")
    await _check_otp(db, email, "reset", body.otp)
    await db.users.update_one({"id": user["id"]}, {"$set": {"password_hash": hash_password(body.new_password), "failed_logins": 0, "locked_until": None, "email_verified": True}})
    await audit(db, user["id"], "password_reset")
    return {"message": "Password updated. Please log in."}


@router.post("/change-password/request")
async def change_password_request(body: ChangePwIn, user: dict = Depends(current_user)):
    """Step 1: check the current password and the new one, then send an OTP to the account owner."""
    db = get_db()
    full = await db.users.find_one({"id": user["id"]})
    if not verify_password(body.old_password, full["password_hash"]):
        raise HTTPException(400, "Old password is incorrect")
    if (p := password_problem(body.new_password)):
        raise HTTPException(400, p)
    otp = await _issue_otp(db, full, "change_pw")
    out = {"message": "An OTP was sent to your email. Enter it to confirm the password change."}
    return out


@router.post("/change-password")
async def change_password(body: ChangePwIn, user: dict = Depends(current_user)):
    """Step 2: needs the OTP from /change-password/request."""
    db = get_db()
    full = await db.users.find_one({"id": user["id"]})
    if not verify_password(body.old_password, full["password_hash"]):
        raise HTTPException(400, "Old password is incorrect")
    if (p := password_problem(body.new_password)):
        raise HTTPException(400, p)
    await _check_otp(db, full["email"], "change_pw", body.otp)
    await db.users.update_one({"id": user["id"]}, {"$set": {"password_hash": hash_password(body.new_password)}})
    await audit(db, user["id"], "password_change")
    return {"message": "Password changed"}


@router.post("/two-factor")
async def two_factor(enable: bool, user: dict = Depends(current_user)):
    await get_db().users.update_one({"id": user["id"]}, {"$set": {"two_factor": enable}})
    return {"two_factor": enable}


@router.get("/me")
async def me(user: dict = Depends(current_user)):
    return public_user({k: v for k, v in user.items() if k != "_jti"})


@router.post("/logout")
async def logout(user: dict = Depends(current_user)):
    db = get_db()
    await db.revoked_tokens.insert_one({"jti": user["_jti"], "ts": now()})
    await audit(db, user["id"], "logout")
    return {"message": "Logged out"}
