"""Tamper-evident medical-record ledger (a permissioned, hash-chained blockchain).

Each patient has a chain of blocks. A block stores only a *fingerprint* of the event (SHA-256 of a document, a consent
grant, an access event...), never the medical data itself, so the ledger can be shown to auditors without leaking PHI.
Block hash = SHA-256(index | timestamp | type | canonical payload | previous hash). Editing or deleting any past block
breaks every later hash, which `verify_chain` detects.

What this is NOT: it is not a public/decentralised network. A database administrator could rewrite the whole chain and
all hashes together. To close that gap, `merkle_root()` produces a single fingerprint of all chain heads that can be
published (e.g. to a public blockchain, a notary, or e-mailed to an auditor) as an external anchor.
"""
from __future__ import annotations

import hashlib
import json

from ..common import new_id, now

GENESIS = "0" * 64


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canon(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def block_hash(index: int, ts: str, btype: str, payload: dict, prev: str) -> str:
    return sha256_hex(f"{index}|{ts}|{btype}|{_canon(payload)}|{prev}".encode())


async def append(db, patient_id: str, btype: str, payload: dict, actor: str | None = None) -> dict:
    """Adds a block to the patient's chain. Never raises: a ledger problem must not block care."""
    try:
        last = await db.ledger_blocks.find({"chain": patient_id}, {"_id": 0}).sort("index", -1).limit(1).to_list(1)
        index = last[0]["index"] + 1 if last else 0
        prev = last[0]["hash"] if last else GENESIS
        ts = now()
        payload = {**payload, **({"actor": actor} if actor else {})}
        blk = {"id": new_id(), "chain": patient_id, "index": index, "ts": ts, "type": btype, "payload": payload, "prev_hash": prev,
               "hash": block_hash(index, ts, btype, payload, prev)}
        await db.ledger_blocks.insert_one(dict(blk))
        blk.pop("_id", None)
        return blk
    except Exception:  # pragma: no cover
        return {}


def verify_blocks(blocks: list[dict]) -> dict:
    """Pure function: validates ordering, links and hashes. Returns the first broken block, if any."""
    prev = GENESIS
    for i, b in enumerate(sorted(blocks, key=lambda x: x["index"])):
        if b["index"] != i:
            return {"valid": False, "broken_at": i, "reason": "missing or duplicated block"}
        if b["prev_hash"] != prev:
            return {"valid": False, "broken_at": i, "reason": "chain link broken (a previous block was altered or removed)"}
        if block_hash(b["index"], b["ts"], b["type"], b["payload"], b["prev_hash"]) != b["hash"]:
            return {"valid": False, "broken_at": i, "reason": "block content does not match its hash (tampered)"}
        prev = b["hash"]
    return {"valid": True, "blocks": len(blocks), "head": prev}


def merkle_root(hashes: list[str]) -> str:
    if not hashes:
        return GENESIS
    level = sorted(hashes)
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [sha256_hex((level[i] + level[i + 1]).encode()) for i in range(0, len(level), 2)]
    return level[0]


def active_grants(blocks: list[dict]) -> dict:
    """Replays access_grant / access_revoke blocks -> {grantee_email: scopes}. Decentralised-style access list derived only from the chain."""
    grants: dict = {}
    for b in sorted(blocks, key=lambda x: x["index"]):
        p = b["payload"]
        if b["type"] == "access_grant":
            grants[p["grantee"]] = {"scopes": p.get("scopes", []), "since": b["ts"], "expires": p.get("expires")}
        elif b["type"] == "access_revoke":
            grants.pop(p["grantee"], None)
    return grants
