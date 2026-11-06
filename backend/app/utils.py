from datetime import datetime

HIDDEN = {"password_hash", "salt", "hash", "key_hash", "_jti"}


def clean(doc):
    """Mongo document -> JSON-safe: _id -> id, UTC datetimes -> ISO 'Z', secrets removed."""
    if isinstance(doc, list):
        return [clean(d) for d in doc]
    if isinstance(doc, dict):
        return {("id" if k == "_id" else k): clean(v) for k, v in doc.items() if k not in HIDDEN}
    if isinstance(doc, datetime):
        return doc.isoformat() + "Z"
    return doc
