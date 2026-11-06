import asyncio
import math
import smtplib
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage

from .config import settings


def new_id() -> str:
    return uuid.uuid4().hex


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def today() -> str:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo(settings.APP_TZ)).strftime("%Y-%m-%d")


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def clean(doc: dict | None, drop: tuple = ()) -> dict | None:
    if doc is None:
        return None
    doc = {k: v for k, v in doc.items() if k != "_id" and k not in drop}
    return doc


PRIVATE_USER_FIELDS = ("password_hash", "failed_logins", "locked_until")


def public_user(u: dict) -> dict:
    return clean(u, PRIVATE_USER_FIELDS)


async def log_event(db, user_id: str, kind: str, title: str, data: dict | None = None):
    """Adds an entry to the patient's health timeline."""
    await db.events.insert_one({"id": new_id(), "user_id": user_id, "kind": kind, "title": title, "data": data or {}, "ts": now()})


async def audit(db, user_id: str | None, action: str, detail: str = "", ip: str = ""):
    await db.audit_logs.insert_one({"id": new_id(), "user_id": user_id, "action": action, "detail": detail, "ip": ip, "ts": now()})


def _send_email(to: str, subject: str, body: str):
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.SMTP_FROM, to, subject
    msg.set_content(body)
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as s:
        s.starttls()
        if settings.SMTP_USER:
            s.login(settings.SMTP_USER, settings.SMTP_PASS)
        s.send_message(msg)


def _send_twilio(to: str, body: str, whatsapp: bool):
    import httpx
    frm = settings.TWILIO_WA_FROM if whatsapp else settings.TWILIO_SMS_FROM
    to = f"whatsapp:{to}" if whatsapp and not to.startswith("whatsapp:") else to
    httpx.post(f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_SID}/Messages.json",
               auth=(settings.TWILIO_SID, settings.TWILIO_TOKEN), data={"From": frm, "To": to, "Body": body}, timeout=15).raise_for_status()


async def notify(db, user: dict | None, title: str, body: str, kind: str = "info", channels: tuple = ("app",), email: str | None = None, phone: str | None = None):
    """Always stores an in-app notification; also tries email / SMS / WhatsApp if configured. Never raises."""
    uid = user["id"] if user else None
    if uid:
        await db.notifications.insert_one({"id": new_id(), "user_id": uid, "title": title, "body": body, "kind": kind, "read": False, "ts": now()})
    to_email = email or (user or {}).get("email")
    to_phone = phone or (user or {}).get("phone")
    loop = asyncio.get_running_loop()
    try:
        if "email" in channels and settings.SMTP_HOST and to_email:
            await loop.run_in_executor(None, _send_email, to_email, title, body)
        if "sms" in channels and settings.TWILIO_SID and to_phone:
            await loop.run_in_executor(None, _send_twilio, to_phone, f"{title}: {body}", False)
        if "whatsapp" in channels and settings.TWILIO_SID and settings.TWILIO_WA_FROM and to_phone:
            await loop.run_in_executor(None, _send_twilio, to_phone, f"{title}: {body}", True)
    except Exception as e:  # delivery problems must never break the request
        await db.audit_logs.insert_one({"id": new_id(), "user_id": uid, "action": "notify_failed", "detail": str(e)[:200], "ip": "", "ts": now()})
