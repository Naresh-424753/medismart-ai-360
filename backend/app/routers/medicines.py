import re
import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..common import audit, log_event, new_id, now, notify, today
from ..config import settings
from ..db import get_db
from ..deps import current_user, require_roles
from ..security import sign
from ..services import drugs, ledger, report_analyzer

router = APIRouter(tags=["medicines & prescriptions"])
patient_only = require_roles("patient")
doctor_only = require_roles("doctor")


class MedIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    dose: str = ""
    times: list[str] = ["08:00"]
    duration_days: int = Field(default=7, ge=1, le=730)
    start_date: str | None = None
    stock: int | None = Field(default=None, ge=0)
    expiry: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    instructions: str = ""


class TakenIn(BaseModel):
    time: str
    date: str | None = None


class InteractionIn(BaseModel):
    names: list[str]


class PrescribedItem(BaseModel):
    name: str
    dose: str = ""
    times: list[str] = ["08:00"]
    duration_days: int = 5
    instructions: str = ""


class RxIn(BaseModel):
    patient_user_id: str
    diagnosis: str = ""
    items: list[PrescribedItem]
    notes: str = ""


class OrderIn(BaseModel):
    pharmacy_id: str
    items: list[dict]
    address: str
    payment_method: str = Field(default="upi", pattern=r"^(upi|cod)$")
    rx_id: str | None = None
    dest_lat: float | None = Field(default=None, ge=-90, le=90)
    dest_lng: float | None = Field(default=None, ge=-180, le=180)


def _valid_times(times: list[str]):
    for t in times:
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t):
            raise HTTPException(400, f"Invalid time '{t}', use HH:MM (24h)")


async def _warnings(db, user_id: str, name: str, exclude_id: str | None = None) -> list[dict]:
    prof = await db.patients.find_one({"user_id": user_id}, {"_id": 0}) or {}
    allergies = [a["name"] for a in prof.get("allergies", [])]
    active = [m["name"] async for m in db.medicines.find({"user_id": user_id, "active": True}) if m["id"] != exclude_id]
    out = [{"type": "allergy", "severity": "severe", "message": a["message"]} for a in drugs.check_allergies(name, allergies)]
    out += [{"type": "interaction", "severity": i["severity"], "message": f"{i['drugs'][0]} + {i['drugs'][1]}: {i['message']}"} for i in drugs.check_interactions(active + [name]) if drugs.canon(name) in i["drugs"]]
    return out


@router.get("/medicines/search")
async def search(q: str, user: dict = Depends(current_user)):
    return drugs.search(q)


@router.get("/medicines/info/{name}")
async def info(name: str, user: dict = Depends(current_user)):
    c = drugs.canon(name)
    if not c:
        raise HTTPException(404, "Medicine not found in the local database")
    return {"name": c, **drugs.DRUGS[c], "disclaimer": "General information only. Follow your prescription."}


@router.post("/medicines/interactions")
async def interactions(body: InteractionIn, user: dict = Depends(current_user)):
    return {"interactions": drugs.check_interactions(body.names), "unknown": [n for n in body.names if not drugs.canon(n)]}


@router.post("/medicines", status_code=201)
async def add_med(body: MedIn, user: dict = Depends(patient_only)):
    db = get_db()
    _valid_times(body.times)
    start = body.start_date or today()
    end = (datetime.strptime(start, "%Y-%m-%d") + timedelta(days=body.duration_days - 1)).strftime("%Y-%m-%d")
    doc = {"id": new_id(), "user_id": user["id"], "name": body.name.strip(), "canonical": drugs.canon(body.name), "dose": body.dose, "times": sorted(set(body.times)),
           "start_date": start, "end_date": end, "stock": body.stock, "expiry": body.expiry, "instructions": body.instructions, "active": True, "created_at": now()}
    warns = await _warnings(db, user["id"], body.name)
    await db.medicines.insert_one(dict(doc))
    await log_event(db, user["id"], "medicine", f"Started {doc['name']} {doc['dose']}".strip())
    doc.pop("_id", None)
    return {**doc, "warnings": warns}


@router.get("/medicines")
async def list_meds(active_only: bool = True, user: dict = Depends(patient_only)):
    q = {"user_id": user["id"]}
    if active_only:
        q["active"] = True
    return await get_db().medicines.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.delete("/medicines/{mid}")
async def stop_med(mid: str, user: dict = Depends(patient_only)):
    await get_db().medicines.update_one({"id": mid, "user_id": user["id"]}, {"$set": {"active": False, "stopped_at": now()}})
    return {"stopped": mid}


def _now_local():
    return datetime.now(ZoneInfo(settings.APP_TZ))


async def todays_schedule(db, user_id: str) -> list[dict]:
    t = today()
    nowl = _now_local()
    meds = await db.medicines.find({"user_id": user_id, "active": True, "start_date": {"$lte": t}, "end_date": {"$gte": t}}, {"_id": 0}).to_list(200)
    logs = {(l["med_id"], l["time"]) async for l in db.med_logs.find({"user_id": user_id, "date": t})}
    out = []
    for m in meds:
        for tm in m["times"]:
            due = datetime.strptime(f"{t} {tm}", "%Y-%m-%d %H:%M").replace(tzinfo=nowl.tzinfo)
            if (m["id"], tm) in logs:
                st = "taken"
            elif nowl > due + timedelta(minutes=60):
                st = "missed"
            elif nowl >= due - timedelta(minutes=15):
                st = "due"
            else:
                st = "upcoming"
            out.append({"med_id": m["id"], "name": m["name"], "dose": m["dose"], "time": tm, "status": st, "instructions": m["instructions"]})
    return sorted(out, key=lambda x: x["time"])


@router.get("/medicines/today")
async def today_sched(user: dict = Depends(patient_only)):
    s = await todays_schedule(get_db(), user["id"])
    taken = sum(1 for x in s if x["status"] == "taken")
    return {"date": today(), "schedule": s, "adherence": round(taken / len(s) * 100) if s else None}


@router.post("/medicines/{mid}/taken")
async def taken(mid: str, body: TakenIn, user: dict = Depends(patient_only)):
    db = get_db()
    m = await db.medicines.find_one({"id": mid, "user_id": user["id"]})
    if not m or body.time not in m["times"]:
        raise HTTPException(404, "Medicine/time not found")
    d = body.date or today()
    if await db.med_logs.find_one({"med_id": mid, "date": d, "time": body.time}):
        return {"ok": True, "already": True}
    await db.med_logs.insert_one({"id": new_id(), "user_id": user["id"], "med_id": mid, "date": d, "time": body.time, "ts": now()})
    if m.get("stock") is not None and m["stock"] > 0:
        await db.medicines.update_one({"id": mid}, {"$inc": {"stock": -1}})
    return {"ok": True}


@router.get("/medicines/alerts")
async def alerts(user: dict = Depends(patient_only)):
    db = get_db()
    out, t = [], today()
    soon = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    for m in await db.medicines.find({"user_id": user["id"], "active": True}, {"_id": 0}).to_list(200):
        per_day = max(len(m["times"]), 1)
        if m.get("stock") is not None and m["stock"] <= per_day * 3:
            out.append({"type": "refill", "medicine": m["name"], "message": f"{m['name']}: only {m['stock']} dose(s) left - time to refill."})
        if m.get("expiry") and m["expiry"] <= soon:
            out.append({"type": "expiry", "medicine": m["name"], "message": f"{m['name']} {'expired' if m['expiry'] < t else 'expires'} on {m['expiry']}."})
    for s in await todays_schedule(db, user["id"]):
        if s["status"] == "missed":
            out.append({"type": "missed", "medicine": s["name"], "message": f"Missed dose: {s['name']} at {s['time']}."})
    return out


@router.get("/medicines/history/adherence")
async def adherence(days: int = 14, user: dict = Depends(patient_only)):
    db = get_db()
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    logs = await db.med_logs.find({"user_id": user["id"], "date": {"$gte": since}}, {"_id": 0}).to_list(5000)
    by_day: dict = {}
    for l in logs:
        by_day[l["date"]] = by_day.get(l["date"], 0) + 1
    return [{"date": d, "doses_taken": n} for d, n in sorted(by_day.items())]


# ---- pharmacies & orders ----
@router.get("/pharmacies")
async def pharmacies(city: str | None = None, user: dict = Depends(current_user)):
    q = {"city": {"$regex": city, "$options": "i"}} if city else {}
    return await get_db().pharmacies.find(q, {"_id": 0}).to_list(100)


DEMO_VPA = "demo@medismart"  # not a real PSP handle: scanning it cannot move money


def _norm_drug(n: str) -> str:
    return re.sub(r"\b\d+(\.\d+)?\s*(mg|mcg|g|ml|iu)\b", "", n.lower()).strip()


def _match_stock(rows: list[dict], name: str) -> dict | None:
    n = _norm_drug(name)
    if not n:
        return None
    for r in rows:
        k = _norm_drug(r["name"])
        if k == n or n.startswith(k + " ") or k.startswith(n + " "):
            return r
    return None


async def _stock_rows(db, ph: dict) -> list[dict] | None:
    """None = this pharmacy has no live inventory (not linked to a pharmacist account)."""
    if not ph.get("user_id"):
        return None
    return await db.pharmacy_stock.find({"user_id": ph["user_id"]}, {"_id": 0}).to_list(3000)


def _availability(rows: list[dict] | None, items: list[dict]) -> dict:
    avail, missing, total, priced = [], [], 0.0, True
    for i in items:
        r = _match_stock(rows or [], i["name"])
        if r and r["quantity"] >= i["qty"]:
            avail.append(i["name"])
            if r.get("price"):
                total += r["price"] * i["qty"]
            else:
                priced = False
        else:
            missing.append({"name": i["name"], "have": r["quantity"] if r else 0})
            priced = False
    return {"available": avail, "missing": missing, "total": round(total, 2) if priced and not missing else None}


async def _quote(db, ph: dict, items: list[dict]):
    """Price from the pharmacy's own stock list. None when any item has no price (pharmacist then sets the amount)."""
    rows = await _stock_rows(db, ph)
    if rows is None:
        return None
    return _availability(rows, items)["total"]


async def _adjust_stock(db, ph: dict, items: list[dict], sign: int):
    for i in items:
        r = _match_stock(await _stock_rows(db, ph) or [], i["name"])
        if r:
            await db.pharmacy_stock.update_one({"user_id": ph["user_id"], "name": r["name"]}, {"$inc": {"quantity": sign * i["qty"]}, "$set": {"updated": now()}})


@router.get("/medicines/orders/suggest")
async def suggest_pharmacies(items: str, user: dict = Depends(patient_only)):
    """Rank pharmacies for a list of medicine names (comma separated): live stock, price, same city first."""
    names = [n.strip() for n in items.split(",") if n.strip()][:20]
    if not names:
        raise HTTPException(400, "No medicines given")
    db = get_db()
    want = [{"name": n, "qty": 1} for n in names]
    prof = await db.patients.find_one({"user_id": user["id"]}) or {}
    city = (prof.get("city") or "").lower()
    out = []
    for ph in await db.pharmacies.find({}, {"_id": 0}).to_list(200):
        rows = await _stock_rows(db, ph)
        av = _availability(rows, want)
        out.append({"pharmacy_id": ph["id"], "name": ph["name"], "city": ph.get("city", ""), "address": ph.get("address", ""), "open_24h": ph.get("open_24h", False), "live_inventory": rows is not None,
                    "has_upi": bool(ph.get("upi_id")), "same_city": bool(city and city == (ph.get("city") or "").lower()), **av})
    out.sort(key=lambda r: (-len(r["available"]) if r["live_inventory"] else 1, not r["same_city"], r["total"] is None, r["total"] or 0))
    return out


@router.post("/medicines/orders", status_code=201)
async def order(body: OrderIn, user: dict = Depends(patient_only)):
    db = get_db()
    ph = await db.pharmacies.find_one({"id": body.pharmacy_id})
    if not ph:
        raise HTTPException(404, "Pharmacy not found")
    items = [{"name": str(i.get("name", ""))[:80], "qty": max(1, min(99, int(i.get("qty", 1))))} for i in body.items if i.get("name")]
    if not items:
        raise HTTPException(400, "No items")
    rows = await _stock_rows(db, ph)
    if rows is not None:
        short = _availability(rows, items)["missing"]
        if short:
            raise HTTPException(409, "Not in stock at this pharmacy: " + ", ".join(f"{m['name']} (have {m['have']})" for m in short))
    amount = await _quote(db, ph, items)
    doc = {"id": new_id(), "rx_id": body.rx_id, "dest": {"lat": body.dest_lat, "lng": body.dest_lng} if body.dest_lat is not None and body.dest_lng is not None else None, "user_id": user["id"], "patient_name": user["name"], "pharmacy_id": ph["id"], "pharmacy_name": ph["name"], "items": items, "address": body.address[:300],
           "status": "placed", "created_at": now(),
           "payment": {"method": body.payment_method, "status": "cod" if body.payment_method == "cod" else "pending", "amount": amount, "utr": None}}
    await db.med_orders.insert_one(dict(doc))
    pu = await db.users.find_one({"id": ph.get("user_id")}) if ph.get("user_id") else None
    if pu:
        await notify(db, pu, "New medicine order", f"{user['name']} ordered {len(items)} item(s)", "order")
    doc.pop("_id", None)
    return doc


async def _my_order(oid: str, user: dict) -> dict:
    o = await get_db().med_orders.find_one({"id": oid, "user_id": user["id"]}, {"_id": 0})
    if not o:
        raise HTTPException(404, "Order not found")
    return o


@router.get("/medicines/orders")
async def my_orders(user: dict = Depends(patient_only)):
    return await get_db().med_orders.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)


@router.get("/medicines/orders/{oid}/pay")
async def pay_info(oid: str, user: dict = Depends(patient_only)):
    """Data for the payment QR: a standard UPI deep link that any UPI app can scan."""
    db = get_db()
    o = await _my_order(oid, user)
    pay = o["payment"]
    if pay["method"] != "upi":
        raise HTTPException(400, "This order is cash on delivery")
    if pay["status"] == "paid":
        raise HTTPException(400, "Already paid")
    if pay.get("amount") is None:
        raise HTTPException(409, "The pharmacy has not set the price yet. You will be notified.")
    ph = await db.pharmacies.find_one({"id": o["pharmacy_id"]}) or {}
    vpa = ph.get("upi_id")
    demo = not vpa
    if demo and not settings.DEV_MODE:
        raise HTTPException(409, "This pharmacy has not set up UPI payments. Choose cash on delivery.")
    vpa = vpa or DEMO_VPA
    from urllib.parse import quote
    uri = f"upi://pay?pa={quote(vpa)}&pn={quote(o['pharmacy_name'][:40])}&am={pay['amount']:.2f}&cu=INR&tn={quote('MediSmart order ' + oid[:8])}&tr={oid[:20]}"
    return {"upi_uri": uri, "amount": pay["amount"], "payee": o["pharmacy_name"], "vpa": vpa, "demo": demo, "status": pay["status"]}


class UtrIn(BaseModel):
    utr: str = Field(pattern=r"^\d{12}$")


@router.post("/medicines/orders/{oid}/pay")
async def submit_payment(oid: str, body: UtrIn, user: dict = Depends(patient_only)):
    """Patient reports they paid (12-digit UPI reference). The pharmacy confirms it against its own bank/UPI app."""
    db = get_db()
    o = await _my_order(oid, user)
    pay = o["payment"]
    if pay["method"] != "upi" or pay["status"] not in {"pending", "failed", "submitted"}:
        raise HTTPException(400, "Payment cannot be submitted for this order")
    if pay.get("amount") is None:
        raise HTTPException(409, "Price not set yet")
    await db.med_orders.update_one({"id": oid}, {"$set": {"payment.status": "submitted", "payment.utr": body.utr, "payment.submitted_at": now()}})
    ph = await db.pharmacies.find_one({"id": o["pharmacy_id"]})
    pu = await db.users.find_one({"id": ph.get("user_id")}) if ph and ph.get("user_id") else None
    if pu:
        await notify(db, pu, "Payment to verify", f"{o['patient_name']} paid Rs {pay['amount']:.0f} (UPI ref {body.utr}). Check your UPI app and confirm.", "order")
    return {"status": "submitted"}


# ---- pharmacist portal ----
pharmacist_only = require_roles("pharmacist")


async def _my_pharmacy(db, user):
    ph = await db.pharmacies.find_one({"user_id": user["id"]})
    if not ph:
        raise HTTPException(409, "Set up your pharmacy profile first")
    return ph


async def _ph_order(db, user, oid):
    ph = await _my_pharmacy(db, user)
    o = await db.med_orders.find_one({"id": oid, "pharmacy_id": ph["id"]})
    if not o:
        raise HTTPException(404, "Order not found")
    return o


class PharmacyIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    city: str = ""
    address: str = ""
    phone: str = ""
    upi_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._-]{2,64}@[A-Za-z0-9]{2,32}$")


@router.get("/pharmacy/profile")
async def pharmacy_profile(user: dict = Depends(pharmacist_only)):
    return await get_db().pharmacies.find_one({"user_id": user["id"]}, {"_id": 0})


@router.put("/pharmacy/profile")
async def set_pharmacy_profile(body: PharmacyIn, user: dict = Depends(pharmacist_only)):
    db = get_db()
    data = body.model_dump()
    if await db.pharmacies.find_one({"user_id": user["id"]}):
        await db.pharmacies.update_one({"user_id": user["id"]}, {"$set": data})
    else:
        await db.pharmacies.insert_one({"id": new_id(), "user_id": user["id"], "open_24h": False, **data})
    return await db.pharmacies.find_one({"user_id": user["id"]}, {"_id": 0})


@router.get("/pharmacy/orders")
async def pharmacy_orders(user: dict = Depends(pharmacist_only)):
    db = get_db()
    ph = await db.pharmacies.find_one({"user_id": user["id"]})
    if not ph:
        return []
    rows = await db.med_orders.find({"pharmacy_id": ph["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    for r in rows:
        r.pop("delivery_otp", None)  # only the patient sees it
    return rows


@router.patch("/pharmacy/orders/{oid}/quote")
async def set_quote(oid: str, amount: float, user: dict = Depends(pharmacist_only)):
    db = get_db()
    o = await _ph_order(db, user, oid)
    if not (0 < amount <= 200000):
        raise HTTPException(400, "Invalid amount")
    if o["payment"]["status"] in {"paid", "submitted"}:
        raise HTTPException(409, "Payment already made; the price can no longer change")
    await db.med_orders.update_one({"id": oid}, {"$set": {"payment.amount": round(amount, 2)}})
    await notify(db, await db.users.find_one({"id": o["user_id"]}), "Order price ready", f"Your order total is Rs {amount:.0f}." + (" You can pay now." if o["payment"]["method"] == "upi" else " Pay on delivery."), "order")
    return {"id": oid, "amount": round(amount, 2)}


@router.post("/pharmacy/orders/{oid}/payment")
async def decide_payment(oid: str, decision: str, user: dict = Depends(pharmacist_only)):
    """Pharmacist confirms the money arrived in their UPI account (or says it did not)."""
    if decision not in {"confirm", "reject"}:
        raise HTTPException(400, "decision must be confirm or reject")
    db = get_db()
    o = await _ph_order(db, user, oid)
    if o["payment"]["status"] != "submitted":
        raise HTTPException(409, "No payment waiting for confirmation")
    st = "paid" if decision == "confirm" else "failed"
    await db.med_orders.update_one({"id": oid}, {"$set": {"payment.status": st, "payment.reviewed_at": now()}})
    await notify(db, await db.users.find_one({"id": o["user_id"]}),
                 "Payment confirmed" if st == "paid" else "Payment not found",
                 "Thank you. Your order will be packed and delivered." if st == "paid" else "The pharmacy could not find your payment. Check the UPI reference and submit again, or choose cash on delivery.", "order")
    return {"status": st}


@router.patch("/pharmacy/orders/{oid}")
async def pharmacy_update_order(oid: str, status: str, otp: str = "", user: dict = Depends(pharmacist_only)):
    if status not in {"accepted", "packed", "out_for_delivery", "delivered", "rejected"}:
        raise HTTPException(400, "Invalid status")
    db = get_db()
    o = await _ph_order(db, user, oid)
    pay = o["payment"]
    if o["status"] in {"delivered", "rejected"}:
        raise HTTPException(409, f"Order already {o['status']}")
    if status in {"packed", "out_for_delivery"} and pay["method"] == "upi" and pay["status"] != "paid":
        raise HTTPException(409, "Confirm the UPI payment before packing or dispatching")
    if status in {"accepted", "packed", "out_for_delivery", "delivered"} and pay.get("amount") is None:
        raise HTTPException(409, "Set the order price first")
    upd: dict = {"status": status}
    extra = ""
    if status == "accepted" and not o.get("stock_deducted"):
        phd = await db.pharmacies.find_one({"id": o["pharmacy_id"]})
        rows = await _stock_rows(db, phd)
        if rows is not None:
            short = _availability(rows, o["items"])["missing"]
            if short:
                raise HTTPException(409, "Cannot accept: not enough stock for " + ", ".join(m["name"] for m in short) + ". Update inventory or reject the order.")
            await _adjust_stock(db, phd, o["items"], -1)
            upd["stock_deducted"] = True
    if status == "rejected" and o.get("stock_deducted"):
        await _adjust_stock(db, await db.pharmacies.find_one({"id": o["pharmacy_id"]}), o["items"], +1)
        upd["stock_deducted"] = False
    if status == "out_for_delivery":
        upd["delivery_otp"] = f"{secrets.randbelow(10000):04d}"
        extra = f" Share code {upd['delivery_otp']} with the delivery person only when you receive the medicines."
    if status == "delivered":
        if not otp or otp != o.get("delivery_otp"):
            raise HTTPException(400, "Wrong or missing delivery code. Ask the patient for the 4-digit code in their app.")
        if pay["method"] == "cod":
            upd["payment.status"] = "paid"
    if status == "rejected" and pay["status"] == "paid":
        upd["payment.status"] = "refund_due"
    await db.med_orders.update_one({"id": oid}, {"$set": upd})
    await notify(db, await db.users.find_one({"id": o["user_id"]}), "Order update", f"Your medicine order is now: {status.replace('_', ' ')}.{extra}", "order")
    return {"id": oid, "status": status}


class LocIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


@router.post("/pharmacy/orders/{oid}/location")
async def share_location(oid: str, body: LocIn, user: dict = Depends(pharmacist_only)):
    """The pharmacy (or its rider logged in on a phone) shares the delivery position while the order is out for delivery."""
    db = get_db()
    o = await _ph_order(db, user, oid)
    if o["status"] != "out_for_delivery":
        raise HTTPException(409, "Location can be shared only while the order is out for delivery")
    pt = {"lat": round(body.lat, 5), "lng": round(body.lng, 5), "ts": now()}
    await db.med_orders.update_one({"id": oid}, {"$set": {"tracking": pt}, "$push": {"track_points": {"$each": [pt], "$slice": -200}}})
    return {"ok": True}


@router.get("/medicines/orders/{oid}/track")
async def track(oid: str, user: dict = Depends(patient_only)):
    from ..common import haversine_km
    o = await _my_order(oid, user)
    t, dest = o.get("tracking"), o.get("dest")
    dist = eta = None
    if t and dest and dest.get("lat") is not None:
        dist = round(haversine_km(t["lat"], t["lng"], dest["lat"], dest["lng"]), 2)
        eta = max(1, round(dist / 20 * 60))  # rough: 20 km/h average city speed, straight-line distance
    return {"status": o["status"], "location": t, "points": (o.get("track_points") or [])[-30:], "dest": dest, "distance_km": dist, "eta_minutes": eta,
            "note": "Position is shared by the pharmacy's rider. ETA is a rough straight-line estimate."}


@router.get("/pharmacy/inventory")
async def inventory(user: dict = Depends(pharmacist_only)):
    return await get_db().pharmacy_stock.find({"user_id": user["id"]}, {"_id": 0}).sort("name", 1).to_list(1000)


class StockIn(BaseModel):
    name: str
    quantity: int = Field(ge=0)
    price: float = Field(ge=0, default=0)
    expiry: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


@router.put("/pharmacy/inventory")
async def set_stock(body: StockIn, user: dict = Depends(pharmacist_only)):
    await get_db().pharmacy_stock.update_one({"user_id": user["id"], "name": body.name.lower()}, {"$set": {**body.model_dump(), "name": body.name.lower(), "user_id": user["id"], "updated": now()}, "$setOnInsert": {"id": new_id()}}, upsert=True)
    return {"ok": True}


@router.get("/pharmacy/alerts")
async def pharmacy_alerts(user: dict = Depends(pharmacist_only)):
    soon = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")
    items = await get_db().pharmacy_stock.find({"user_id": user["id"]}, {"_id": 0}).to_list(2000)
    return {"low_stock": [i for i in items if i["quantity"] <= 10], "expiring": [i for i in items if i.get("expiry") and i["expiry"] <= soon]}


# ---- prescriptions ----
@router.post("/prescriptions", status_code=201)
async def create_rx(body: RxIn, user: dict = Depends(doctor_only)):
    db = get_db()
    if not user.get("approved"):
        raise HTTPException(403, "Your doctor account is pending admin verification")
    appt = await db.appointments.find_one({"doctor_user_id": user["id"], "patient_user_id": body.patient_user_id, "status": {"$ne": "cancelled"}})
    if not appt:
        raise HTTPException(403, "You can only prescribe for patients who have an appointment with you")
    if not body.items:
        raise HTTPException(400, "Add at least one medicine")
    for it in body.items:
        _valid_times(it.times)
    prof = await db.patients.find_one({"user_id": body.patient_user_id}, {"_id": 0}) or {}
    allergies = [a["name"] for a in prof.get("allergies", [])]
    names = [i.name for i in body.items]
    warnings = [a["message"] for i in body.items for a in drugs.check_allergies(i.name, allergies)] + [f"{x['drugs'][0]} + {x['drugs'][1]}: {x['message']}" for x in drugs.check_interactions(names)]
    rid = new_id()
    code = rid[:10].upper()
    doc = {"id": rid, "code": code, "sig": sign(code), "patient_user_id": body.patient_user_id, "doctor_user_id": user["id"], "doctor_name": user["name"],
           "diagnosis": body.diagnosis, "items": [i.model_dump() for i in body.items], "notes": body.notes, "created_at": now(), "warnings": warnings, "imported": False}
    await db.prescriptions.insert_one(dict(doc))
    pu = await db.users.find_one({"id": body.patient_user_id})
    await notify(db, pu, "New prescription", f"Dr. {user['name']} issued a prescription ({code}). Order your medicines: open Medicines, then Prescriptions, then Order medicines.", "prescription", ("app", "email"))
    await log_event(db, body.patient_user_id, "prescription", f"Prescription {code} by {user['name']}")
    await ledger.append(db, body.patient_user_id, "prescription", {"code": code, "items_sha256": ledger.sha256_hex(str(doc["items"]).encode()), "doctor_user_id": user["id"]}, actor=user["id"])
    doc.pop("_id", None)
    return doc


@router.get("/prescriptions")
async def list_rx(user: dict = Depends(current_user)):
    db = get_db()
    q = {"patient_user_id": user["id"]} if user["role"] == "patient" else {"doctor_user_id": user["id"]} if user["role"] == "doctor" else None
    if q is None:
        raise HTTPException(403, "Not available for your role")
    rows = await db.prescriptions.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    if user["role"] == "patient":
        for r in rows:
            r["ordered"] = bool(await db.med_orders.find_one({"rx_id": r["id"], "user_id": user["id"], "status": {"$ne": "rejected"}}))
    return rows


@router.get("/prescriptions/verify/{code}")
async def verify_rx(code: str):
    """Public (no login) - used by pharmacies scanning the QR code. Returns minimal data."""
    code = code.upper()
    rx = await get_db().prescriptions.find_one({"code": code}, {"_id": 0})
    if not rx or rx["sig"] != sign(code):
        return {"valid": False}
    return {"valid": True, "code": code, "doctor": rx["doctor_name"], "issued": rx["created_at"][:10], "items": [{"name": i["name"], "dose": i["dose"]} for i in rx["items"]]}


@router.post("/prescriptions/{rid}/import")
async def import_rx(rid: str, user: dict = Depends(patient_only)):
    """Adds every prescribed item to the patient's medicine schedule."""
    db = get_db()
    rx = await db.prescriptions.find_one({"id": rid, "patient_user_id": user["id"]})
    if not rx:
        raise HTTPException(404, "Prescription not found")
    created = []
    for it in rx["items"]:
        created.append(await add_med(MedIn(name=it["name"], dose=it["dose"], times=it["times"], duration_days=it["duration_days"], instructions=it["instructions"]), user))
    await db.prescriptions.update_one({"id": rid}, {"$set": {"imported": True}})
    return {"imported": len(created), "medicines": created}


@router.post("/prescriptions/read")
async def read_rx_image(file: UploadFile = File(...), user: dict = Depends(patient_only)):
    """AI prescription reader: OCR (Tesseract) + matching against the local drug list. Handwriting is NOT reliably read."""
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large")
    try:
        text = report_analyzer.ocr_image_bytes(data)
    except RuntimeError as e:
        raise HTTPException(422, str(e))
    low = text.lower()
    found = []
    for name, d in drugs.DRUGS.items():
        hit = name in low or any(b.lower() in low for b in d["brands"])
        if hit:
            m = re.search(rf"(?:{re.escape(name)}|{'|'.join(re.escape(b.lower()) for b in d['brands']) or 'zzzz'})[^\n]{{0,25}}?(\d+\s?(?:mg|mcg|g|ml|iu))", low)
            found.append({"name": name, "dose": m.group(1) if m else "", "uses": d["uses"]})
    return {"text": text[:2000], "medicines_detected": found,
            "note": "Please verify each medicine against the original prescription. Printed text works best; handwriting often fails."}
