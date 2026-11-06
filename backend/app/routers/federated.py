"""Federated-learning coordinator. Hospitals pull the global model, train locally, and push only weight updates."""
import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..common import audit, new_id, now
from ..db import get_db
from ..deps import require_roles
from ..services import federated as F
from ..services import ml

router = APIRouter(prefix="/federated", tags=["federated learning"])
admin_only = require_roles("admin", "super_admin")
hospital_only = require_roles("hospital")
staff = require_roles("admin", "super_admin", "hospital")
MAX_NORM = 25.0


async def _round(db, disease: str):
    return await db.fl_rounds.find_one({"disease": disease, "status": "open"}, {"_id": 0})


async def _model(db, disease: str) -> dict:
    m = await db.fl_models.find_one({"disease": disease}, {"_id": 0})
    if m:
        return m
    names, _, _ = F.spec_scaler(disease)
    m = {"disease": disease, "features": names, "w": [0.0] * len(names), "b": 0.0, "version": 0, "history": [], "created_at": now()}
    await db.fl_models.insert_one(dict(m))
    return m


class StartIn(BaseModel):
    disease: str
    min_participants: int = Field(default=2, ge=1, le=100)
    clip: float | None = Field(default=5.0, gt=0, le=MAX_NORM)
    noise_multiplier: float = Field(default=0.0, ge=0, le=5)
    epochs: int = Field(default=3, ge=1, le=50)
    lr: float = Field(default=0.1, gt=0, le=1)


@router.post("/rounds")
async def start_round(body: StartIn, user: dict = Depends(admin_only)):
    if body.disease not in ml.SPECS:
        raise HTTPException(404, f"Unknown model. Choose from {list(ml.SPECS)}")
    db = get_db()
    if await _round(db, body.disease):
        raise HTTPException(409, "A round is already open for this model")
    m = await _model(db, body.disease)
    r = {"id": new_id(), "disease": body.disease, "round": m["version"] + 1, "base_version": m["version"], "status": "open", "min_participants": body.min_participants,
         "clip": body.clip, "noise_multiplier": body.noise_multiplier, "epochs": body.epochs, "lr": body.lr, "updates": [], "started_at": now()}
    await db.fl_rounds.insert_one(dict(r))
    await audit(db, user["id"], "fl_round_start", f"{body.disease} round {r['round']}")
    r.pop("_id", None)
    return r


@router.get("/status")
async def status(user: dict = Depends(staff)):
    db = get_db()
    out = []
    for d in ml.SPECS:
        m = await db.fl_models.find_one({"disease": d}, {"_id": 0}) or {"version": 0, "history": []}
        r = await _round(db, d)
        out.append({"disease": d, "title": ml.SPECS[d]["title"], "version": m["version"], "history": m.get("history", [])[-20:],
                    "open_round": None if not r else {"id": r["id"], "round": r["round"], "min_participants": r["min_participants"], "clip": r["clip"], "noise_multiplier": r["noise_multiplier"],
                                                      "epochs": r["epochs"], "lr": r["lr"], "received": [{"hospital": u["hospital_name"], "n": u["n"], "ts": u["ts"]} for u in r["updates"]]}})
    return out


@router.get("/global/{disease}")
async def global_model(disease: str, user: dict = Depends(hospital_only)):
    """Hospital downloads current global weights + the training recipe for the open round."""
    if disease not in ml.SPECS:
        raise HTTPException(404, "Unknown model")
    db = get_db()
    m = await _model(db, disease)
    r = await _round(db, disease)
    names, mu, sd = F.spec_scaler(disease)
    return {"disease": disease, "version": m["version"], "features": names, "scaler": {"mean": mu.tolist(), "sd": sd.tolist()}, "w": m["w"], "b": m["b"],
            "round": None if not r else {"id": r["id"], "round": r["round"], "epochs": r["epochs"], "lr": r["lr"], "clip": r["clip"], "noise_multiplier": r["noise_multiplier"]}}


class UpdateIn(BaseModel):
    disease: str
    round_id: str
    delta_w: list[float]
    delta_b: float
    n: int
    eval_prev: dict | None = None  # {"n","loss","auc"} of the PREVIOUS global model on the hospital's own held-out data


@router.post("/update")
async def push_update(body: UpdateIn, user: dict = Depends(hospital_only)):
    db = get_db()
    if not user.get("approved"):
        raise HTTPException(403, "Hospital account is pending admin verification")
    r = await db.fl_rounds.find_one({"id": body.round_id, "disease": body.disease, "status": "open"})
    if not r:
        raise HTTPException(404, "No such open round")
    m = await _model(db, body.disease)
    err = F.validate_update(body.model_dump(), len(m["w"]), MAX_NORM)
    if err:
        raise HTTPException(400, err)
    h = await db.hospitals.find_one({"user_id": user["id"]}) or {}
    up = {"hospital_user_id": user["id"], "hospital_name": h.get("name") or user["name"], "delta_w": body.delta_w, "delta_b": body.delta_b, "n": body.n, "eval_prev": body.eval_prev, "ts": now()}
    ups = [u for u in r["updates"] if u["hospital_user_id"] != user["id"]] + [up]
    await db.fl_rounds.update_one({"id": r["id"]}, {"$set": {"updates": ups}})
    done = None
    if len(ups) >= r["min_participants"]:
        done = await _aggregate(db, r["id"])
    return {"accepted": True, "received": len(ups), "needed": r["min_participants"], "aggregated": bool(done), "new_version": done["version"] if done else None}


async def _aggregate(db, rid: str):
    r = await db.fl_rounds.find_one({"id": rid, "status": "open"})
    m = await _model(db, r["disease"])
    ups = r["updates"]
    if not ups:
        raise HTTPException(409, "No updates to aggregate")
    w, b = F.fedavg(m["w"], m["b"], ups)
    ev = [u["eval_prev"] for u in ups if u.get("eval_prev") and u["eval_prev"].get("auc") is not None]
    tot = sum(e["n"] for e in ev)
    prev_auc = round(sum(e["auc"] * e["n"] for e in ev) / tot, 4) if tot else None
    entry = {"version": m["version"] + 1, "round": r["round"], "participants": len(ups), "samples": sum(u["n"] for u in ups), "prev_model_auc_on_hospital_holdouts": prev_auc, "ts": now()}
    await db.fl_models.update_one({"disease": r["disease"]}, {"$set": {"w": w.tolist(), "b": b, "version": entry["version"]}, "$push": {"history": entry}})
    await db.fl_rounds.update_one({"id": rid}, {"$set": {"status": "closed", "closed_at": now()}})
    return entry


@router.post("/rounds/{rid}/aggregate")
async def aggregate_now(rid: str, user: dict = Depends(admin_only)):
    db = get_db()
    r = await db.fl_rounds.find_one({"id": rid, "status": "open"})
    if not r:
        raise HTTPException(404, "Open round not found")
    e = await _aggregate(db, rid)
    await audit(db, user["id"], "fl_aggregate", f"{r['disease']} -> v{e['version']}")
    return e


class SimIn(BaseModel):
    disease: str = "diabetes"
    hospitals: int = Field(default=4, ge=2, le=10)
    rounds: int = Field(default=12, ge=1, le=40)
    clip: float | None = Field(default=None, gt=0)
    noise_multiplier: float = Field(default=0.0, ge=0, le=5)


@router.post("/simulate")
async def simulate(body: SimIn, user: dict = Depends(admin_only)):
    """In-process demo: N synthetic hospitals with different populations; compares local-only, federated and centralised training."""
    if body.disease not in ml.SPECS:
        raise HTTPException(404, "Unknown model")
    return F.simulate(body.disease, body.hospitals, body.rounds, clip=body.clip, sigma=body.noise_multiplier)
