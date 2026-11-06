"""Blockchain-style integrity layer for medical records (see services/ledger.py for the design and its limits)."""
import os

from fastapi import APIRouter, Depends, HTTPException

from ..common import new_id, now
from ..config import settings
from ..crypto import decrypt
from ..db import get_db
from ..deps import current_user, require_roles
from ..services import blobstore, ledger

router = APIRouter(prefix="/ledger", tags=["record integrity (ledger)"])
patient_only = require_roles("patient")
staff = require_roles("admin")


@router.get("/me")
async def my_chain(user: dict = Depends(patient_only)):
    db = get_db()
    blocks = await db.ledger_blocks.find({"chain": user["id"]}, {"_id": 0}).sort("index", 1).to_list(5000)
    return {"verification": ledger.verify_blocks(blocks), "blocks": list(reversed(blocks))[:200], "access_list": ledger.active_grants(blocks)}


@router.get("/me/verify")
async def verify_my_chain(user: dict = Depends(patient_only)):
    blocks = await get_db().ledger_blocks.find({"chain": user["id"]}, {"_id": 0}).sort("index", 1).to_list(100000)
    return ledger.verify_blocks(blocks)


@router.get("/me/documents/{did}/verify")
async def verify_document(did: str, user: dict = Depends(patient_only)):
    """Re-hashes the stored (decrypted) file and compares it with the fingerprint recorded on the ledger at upload time."""
    db = get_db()
    doc = await db.documents.find_one({"id": did, "user_id": user["id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Document not found")
    blk = await db.ledger_blocks.find_one({"chain": user["id"], "type": "document", "payload.document_id": did}, {"_id": 0})
    if not blk:
        return {"status": "not_anchored", "message": "This document was uploaded before the ledger was enabled, so it has no recorded fingerprint."}
    try:
        raw = blobstore.get(user["id"], did)
        current = ledger.sha256_hex(decrypt(raw))
    except Exception:
        return {"status": "unreadable", "message": "The stored file could not be read or decrypted: it may be missing or corrupted."}
    chain = await db.ledger_blocks.find({"chain": user["id"]}, {"_id": 0}).sort("index", 1).to_list(100000)
    chain_ok = ledger.verify_blocks(chain)["valid"]
    same = current == blk["payload"]["sha256"]
    return {"status": "verified" if same and chain_ok else "TAMPERED", "file_matches_ledger": same, "ledger_chain_valid": chain_ok,
            "recorded_sha256": blk["payload"]["sha256"], "current_sha256": current, "recorded_at": blk["ts"], "block_index": blk["index"]}


@router.post("/me/access/{grantee_email}/revoke")
async def revoke_all(grantee_email: str, user: dict = Depends(patient_only)):
    """Revokes every active consent for this person and records it on the ledger."""
    db = get_db()
    email = grantee_email.lower()
    r = await db.consents.update_many({"patient_user_id": user["id"], "grantee_email": email, "active": True}, {"$set": {"active": False, "revoked_at": now()}})
    await ledger.append(db, user["id"], "access_revoke", {"grantee": email}, actor=user["id"])
    return {"revoked_consents": r.modified_count}


@router.get("/admin/anchor")
async def anchor(user: dict = Depends(staff)):
    """Merkle root over every patient chain head. Publish it externally (public chain, notary, auditor e-mail) to make rewriting history detectable."""
    db = get_db()
    heads: dict = {}
    for b in await db.ledger_blocks.find({}, {"_id": 0, "chain": 1, "index": 1, "hash": 1}).sort("index", 1).to_list(1_000_000):
        heads[b["chain"]] = b["hash"]
    root = ledger.merkle_root(list(heads.values()))
    rec = {"id": new_id(), "root": root, "chains": len(heads), "ts": now()}
    await db.ledger_anchors.insert_one(dict(rec))
    rec.pop("_id", None)
    return {**rec, "how_to_use": "Publish this root outside this database. Later, recompute it: a different value means some chain was changed."}


@router.get("/admin/verify-all")
async def verify_all(user: dict = Depends(staff)):
    db = get_db()
    chains: dict = {}
    for b in await db.ledger_blocks.find({}, {"_id": 0}).to_list(1_000_000):
        chains.setdefault(b["chain"], []).append(b)
    bad = [{"chain": c, **r} for c, bl in chains.items() if not (r := ledger.verify_blocks(bl))["valid"]]
    return {"chains_checked": len(chains), "broken": bad}
