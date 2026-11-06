"""Background loop: appointment reminders (24 h / 1 h before) and medicine dose reminders."""
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .common import notify, now
from .config import settings
from .db import get_db

log = logging.getLogger("scheduler")


async def tick(db):
    tz = ZoneInfo(settings.APP_TZ)
    nowl = datetime.now(tz)
    # appointments
    async for a in db.appointments.find({"status": {"$in": ["booked", "confirmed"]}, "date": {"$gte": nowl.strftime("%Y-%m-%d")}}):
        when = datetime.strptime(f"{a['date']} {a['time']}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
        delta = when - nowl
        patient = await db.users.find_one({"id": a["patient_user_id"]})
        if timedelta(0) < delta <= timedelta(hours=1) and not a.get("reminded_1h"):
            await notify(db, patient, "Appointment in 1 hour", f"{a['doctor_name']} at {a['time']}" + (f" - join: {a['video_url']}" if a.get("video_url") else ""), "appointment", ("app", "sms"))
            await db.appointments.update_one({"id": a["id"]}, {"$set": {"reminded_1h": True, "reminded_24h": True}})
        elif timedelta(hours=1) < delta <= timedelta(hours=24) and not a.get("reminded_24h"):
            await notify(db, patient, "Appointment tomorrow", f"{a['doctor_name']} on {a['date']} at {a['time']}", "appointment", ("app", "email"))
            await db.appointments.update_one({"id": a["id"]}, {"$set": {"reminded_24h": True}})
    # medicines: remind at the scheduled minute, once per dose
    today = nowl.strftime("%Y-%m-%d")
    hhmm = nowl.strftime("%H:%M")
    async for m in db.medicines.find({"active": True, "start_date": {"$lte": today}, "end_date": {"$gte": today}, "times": hhmm}):
        key = {"med_id": m["id"], "date": today, "time": hhmm}
        if await db.med_reminders.find_one(key):
            continue
        await db.med_reminders.insert_one({**key, "ts": now()})
        if not await db.med_logs.find_one(key):
            await notify(db, await db.users.find_one({"id": m["user_id"]}), "Medicine reminder", f"Time to take {m['name']} {m.get('dose', '')}", "medicine", ("app", "sms"))


async def run_forever():
    while True:
        try:
            await tick(get_db())
        except Exception:
            log.exception("scheduler tick failed")
        await asyncio.sleep(45)
