"""Notifications + SOS fan-out. Always stores an in-app notification; email (SMTP) and
SMS (Twilio) are used only when configured. Delivery providers are NOT exercised by tests."""
import asyncio
import logging
import smtplib
from email.message import EmailMessage

from ..config import settings
from ..security import new_id, now

log = logging.getLogger("medismart.notify")


def _send_email_sync(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.smtp_user, to, subject
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as s:
        s.starttls()
        s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(msg)


async def send_sms(to: str, body: str) -> None:
    if not (settings.twilio_sid and settings.twilio_token and settings.twilio_from):
        log.info("[sms disabled] to=%s body=%s", to, body)
        return
    import httpx

    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_sid}/Messages.json",
                         auth=(settings.twilio_sid, settings.twilio_token),
                         data={"To": to, "From": settings.twilio_from, "Body": body})
        r.raise_for_status()


async def send_email(to: str, subject: str, body: str) -> None:
    if not settings.smtp_host:
        log.info("[email disabled] to=%s subject=%s", to, subject)
        return
    await asyncio.get_running_loop().run_in_executor(None, _send_email_sync, to, subject, body)


async def notify_user(db, user_id: str, kind: str, title: str, body: str, level: str = "info") -> None:
    await db.notifications.insert_one({"_id": new_id(), "user_id": user_id, "kind": kind, "title": title,
                                       "body": body, "level": level, "read": False, "created": now()})
    user = await db.users.find_one({"_id": user_id})
    if user and level in ("warning", "critical"):
        try:
            await send_email(user["email"], title, body)
        except Exception:  # delivery must never break the request
            log.exception("email delivery failed")


async def raise_sos(db, patient_id: str, source: str, reason: str, lat=None, lng=None) -> dict:
    """Create an emergency event and alert contacts + consenting family/doctors."""
    event = {"_id": new_id(), "patient_id": patient_id, "source": source, "reason": reason,
             "lat": lat, "lng": lng, "status": "open", "created": now()}
    await db.emergency_events.insert_one(event)
    patient = await db.users.find_one({"_id": patient_id}) or {}
    profile = await db.patient_profiles.find_one({"_id": patient_id}) or {}
    where = f" Location: https://maps.google.com/?q={lat},{lng}" if lat is not None and lng is not None else ""
    text = f"EMERGENCY: {patient.get('name', 'A MediSmart user')} needs help ({reason}).{where}"
    for c in profile.get("emergency_contacts", []):
        if c.get("phone"):
            try:
                await send_sms(c["phone"], text)
            except Exception:
                log.exception("sms failed for %s", c.get("name"))
    async for consent in db.consents.find({"patient_id": patient_id, "active": True}):
        await notify_user(db, consent["grantee_id"], "emergency", "Emergency alert", text, "critical")
    await notify_user(db, patient_id, "emergency", "SOS sent", "Your emergency contacts were alerted.", "critical")
    return event
