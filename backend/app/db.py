from .config import settings

_client = None
_db = None


MOCK_ACTIVE = False


def is_mock() -> bool:
    return MOCK_ACTIVE or settings.MONGO_URL == "mock"


def use_mock():
    """Emergency fallback: switch to the in-memory database (data is lost on restart)."""
    global _client, _db, MOCK_ACTIVE
    from mongomock_motor import AsyncMongoMockClient
    _client = AsyncMongoMockClient()
    _db = _client[settings.DB_NAME]
    MOCK_ACTIVE = True
    return _db


def get_db():
    global _client, _db
    if _db is None:
        if settings.MONGO_URL == "mock":
            from mongomock_motor import AsyncMongoMockClient
            _client = AsyncMongoMockClient()
        else:
            from motor.motor_asyncio import AsyncIOMotorClient
            _client = AsyncIOMotorClient(settings.MONGO_URL, serverSelectionTimeoutMS=5000, appname="medismart")
        _db = _client[settings.DB_NAME]
    return _db


def reset_db():
    """Used by tests to start from a clean in-memory database."""
    global _client, _db
    _client = _db = None


async def check_connection(db):
    """Fail fast with a readable message instead of timing out on the first request."""
    if is_mock():
        return
    try:
        await db.command("ping")
    except Exception as e:
        raise RuntimeError(f"Cannot reach MongoDB ({type(e).__name__}). Check MONGO_URL in backend/.env, that mongod is running, and the username/password.") from e


INDEXES = [
    ("users", "email", {"unique": True}), ("users", "id", {"unique": True}), ("patients", "user_id", {"unique": True}), ("patients", "health_id", {"unique": True}),
    ("vitals", [("patient_id", 1), ("ts", -1)], {}), ("appointments", [("doctor_id", 1), ("date", 1)], {}), ("appointments", [("patient_user_id", 1), ("date", 1)], {}),
    ("audit_logs", [("ts", -1)], {}), ("notifications", [("user_id", 1), ("ts", -1)], {}), ("events", [("user_id", 1), ("ts", -1)], {}),
    ("vital_alerts", [("patient_id", 1), ("ts", -1)], {}), ("med_orders", [("user_id", 1), ("created_at", -1)], {}), ("med_orders", "pharmacy_id", {}),
    ("pharmacy_stock", [("user_id", 1), ("name", 1)], {}), ("medicines", [("user_id", 1), ("active", 1)], {}), ("med_logs", [("user_id", 1), ("date", 1)], {}),
    ("reports", [("user_id", 1), ("ts", -1)], {}), ("risk_assessments", [("user_id", 1), ("ts", -1)], {}),
    ("ledger_blocks", [("chain", 1), ("index", 1)], {"unique": True}), ("wearable_samples", "k", {"unique": True}),
    ("board_cases", "patient_id", {}), ("board_cases", "panel.doctor_user_id", {}), ("fl_models", "disease", {"unique": True}), ("fl_rounds", [("disease", 1), ("status", 1)], {}),
    ("ews_state", "user_id", {"unique": True}), ("ews_settings", "user_id", {"unique": True}), ("ews_events", [("user_id", 1), ("ts", -1)], {}),
    ("otps", [("email", 1), ("purpose", 1)], {}), ("users", "role", {}), ("contact_messages", [("status", 1), ("ts", -1)], {}), ("revoked_tokens", "jti", {"unique": True}),
]


async def ensure_indexes(db):
    """Creates indexes on a real MongoDB. One failing index (e.g. old duplicate data) is logged and does not stop startup."""
    if is_mock():
        return
    import logging
    for coll, keys, opts in INDEXES:
        try:
            await db[coll].create_index(keys, **opts)
        except Exception as e:
            logging.getLogger("medismart.db").warning("index %s %s not created: %s", coll, keys, e)
