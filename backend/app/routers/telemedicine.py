"""Real-time telemedicine: WebRTC audio/video between doctor and patient. This server only does *signalling* (relaying offers,
answers and ICE candidates); media flows peer-to-peer, encrypted by WebRTC (DTLS-SRTP). Add a TURN server for strict networks."""
import asyncio
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from ..common import new_id, now
from ..config import settings
from ..db import get_db
from ..deps import current_user, user_from_token

router = APIRouter(prefix="/telemedicine", tags=["telemedicine"])
RELAY = {"offer", "answer", "candidate", "chat", "media-state", "hangup"}
MAX_MSG = 64 * 1024


class Rooms:
    """room id -> {user_id: websocket}; at most the two appointment parties."""

    def __init__(self):
        self.rooms: dict[str, dict[str, WebSocket]] = {}

    def join(self, rid: str, uid: str, ws) -> dict:
        room = self.rooms.setdefault(rid, {})
        old = room.get(uid)
        room[uid] = ws
        return {"replaced": old, "peers": [u for u in room if u != uid]}

    def leave(self, rid: str, uid: str, ws) -> None:
        room = self.rooms.get(rid, {})
        if room.get(uid) is ws:
            room.pop(uid, None)
        if not room:
            self.rooms.pop(rid, None)

    def peer(self, rid: str, uid: str):
        return next((w for u, w in self.rooms.get(rid, {}).items() if u != uid), None)


rooms = Rooms()


def ice_servers() -> list[dict]:
    out = [{"urls": settings.STUN_URLS}] if settings.STUN_URLS else []
    if settings.TURN_URL:
        out.append({"urls": [settings.TURN_URL], "username": settings.TURN_USERNAME, "credential": settings.TURN_CREDENTIAL})
    return out


def in_window(a: dict) -> bool:
    if settings.TELE_ANYTIME:
        return True
    try:
        start = datetime.strptime(f"{a['date']} {a['time']}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(settings.APP_TZ))
    except ValueError:
        return False
    t = datetime.now(ZoneInfo(settings.APP_TZ))
    return start - timedelta(minutes=15) <= t <= start + timedelta(minutes=90)


async def _authorize(db, user: dict, aid: str) -> dict:
    a = await db.appointments.find_one({"id": aid}, {"_id": 0})
    if not a or user["id"] not in (a["patient_user_id"], a["doctor_user_id"]):
        raise HTTPException(404, "Appointment not found")
    if a["status"] not in ("booked", "confirmed"):
        raise HTTPException(409, f"Appointment is {a['status']}")
    if not in_window(a):
        raise HTTPException(425, "The call room opens 15 minutes before the appointment time")
    return a


@router.get("/{aid}/config")
async def config(aid: str, user: dict = Depends(current_user)):
    a = await _authorize(get_db(), user, aid)
    doctor = user["id"] == a["doctor_user_id"]
    return {"ice_servers": ice_servers(), "role": "doctor" if doctor else "patient", "me": user["id"], "initiator": a["doctor_user_id"],
            "other_name": a["patient_name"] if doctor else a["doctor_name"], "date": a["date"], "time": a["time"], "mode": a["mode"], "fallback_url": a.get("video_url")}


@router.websocket("/ws/{aid}")
async def signalling(ws: WebSocket, aid: str):
    """First message must be {"type":"auth","token":"<jwt>"} (keeps the token out of URLs and server logs)."""
    await ws.accept()
    db = get_db()
    try:
        first = json.loads(await asyncio.wait_for(ws.receive_text(), 10))
        if first.get("type") != "auth":
            raise HTTPException(401)
        user = await user_from_token(first.get("token", ""))
        a = await _authorize(db, user, aid)
    except (HTTPException, ValueError, asyncio.TimeoutError, WebSocketDisconnect) as e:
        code = getattr(e, "status_code", 401)
        try:
            await ws.send_text(json.dumps({"type": "error", "status": code, "message": getattr(e, "detail", "Not allowed")}))
            await ws.close(code=4401)
        except Exception:
            pass
        return
    uid = user["id"]
    j = rooms.join(aid, uid, ws)
    if j["replaced"] is not None:
        try:
            await j["replaced"].close(code=4409)
        except Exception:
            pass
    await ws.send_text(json.dumps({"type": "joined", "peers": len(j["peers"]), "initiator": a["doctor_user_id"]}))
    started = None
    peer = rooms.peer(aid, uid)
    if peer:
        started = now()
        await db.call_sessions.insert_one({"id": new_id(), "appointment_id": aid, "started_at": started, "ended_at": None})
        for w in (ws, peer):
            await w.send_text(json.dumps({"type": "ready", "initiator": a["doctor_user_id"]}))
    try:
        while True:
            raw = await ws.receive_text()
            if len(raw) > MAX_MSG:
                continue
            try:
                m = json.loads(raw)
            except ValueError:
                continue
            if m.get("type") not in RELAY:
                continue
            p = rooms.peer(aid, uid)
            if p:
                m["from"] = uid
                if m["type"] == "chat":
                    m["text"] = str(m.get("text", ""))[:2000]
                await p.send_text(json.dumps(m))
    except WebSocketDisconnect:
        pass
    finally:
        rooms.leave(aid, uid, ws)
        p = rooms.peer(aid, uid)
        if p:
            try:
                await p.send_text(json.dumps({"type": "peer-left"}))
            except Exception:
                pass
        if p is None:  # last person left -> close the session record
            await db.call_sessions.update_many({"appointment_id": aid, "ended_at": None}, {"$set": {"ended_at": now()}})


@router.get("/{aid}/sessions")
async def sessions(aid: str, user: dict = Depends(current_user)):
    db = get_db()
    a = await db.appointments.find_one({"id": aid}, {"_id": 0})
    if not a or user["id"] not in (a["patient_user_id"], a["doctor_user_id"]):
        raise HTTPException(404, "Appointment not found")
    return await db.call_sessions.find({"appointment_id": aid}, {"_id": 0}).sort("started_at", -1).to_list(50)
