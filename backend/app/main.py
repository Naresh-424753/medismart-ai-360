import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .db import check_connection, ensure_indexes, get_db, use_mock
from .routers import admin, ai, contact, board, analytics, auth, blood, chat, doctors, emergency, extras, federated, hospital_ops, hospitals, labs, ews, ledger, medicines, messaging, patients, reports, rx_scan, telemedicine, vitals, voice, wearables, wellness
from .scheduler import run_forever
from .seed import seed

log = logging.getLogger("medismart")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = get_db()
    try:
        await check_connection(db)
    except RuntimeError as e:
        if not settings.MONGO_FALLBACK:
            raise
        log.error("=" * 70)
        log.error("%s", e)
        log.error("MONGO_FALLBACK=1: running on a TEMPORARY in-memory database. Everything is lost on restart!")
        log.error("Start MongoDB and restart the backend to use the real database.")
        log.error("=" * 70)
        db = use_mock()
    await ensure_indexes(db)
    await seed(db)
    if settings.DEV_MODE:
        log.warning("DEV_MODE is on: with no SMTP set, OTPs are printed in this server console (never sent to the browser). Disable it in production.")
    if not settings.JWT_SECRET:
        raise RuntimeError("JWT_SECRET is not set. Put a long random value in backend/.env (python -c \"import secrets;print(secrets.token_urlsafe(48))\").")
    if not os.getenv("JWT_SECRET"):
        log.warning("JWT_SECRET not set: using a generated development secret from data/.dev_secret. Set JWT_SECRET before deploying.")
    task = asyncio.create_task(run_forever())
    yield
    task.cancel()


app = FastAPI(title=settings.APP_NAME, version="1.0.0", lifespan=lifespan,
              description="MediSmart AI 360 - Diagnose Early, Treat Precisely, Heal Faster. Demo software, not a medical device.")

app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

_hits: dict[str, deque] = defaultdict(deque)
RATE_LIMITS = {"/auth/login": (10, 60), "/auth/register": (10, 300), "/auth/verify-otp": (15, 300), "/auth/forgot-password": (5, 300), "/auth/resend-otp": (5, 300),
               "/contact": (5, 300), "/voice/transcribe": (20, 60), "/voice/symptom-check": (20, 60), "/kiosk/symptom-check": (30, 60), "/kiosk/bmi": (30, 60)}


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    limit = RATE_LIMITS.get(request.url.path)
    if limit and request.method == "POST":
        ip = request.client.host if request.client else "?"
        q = _hits[f"{request.url.path}|{ip}"]
        n, window = limit
        t = time.time()
        while q and q[0] < t - window:
            q.popleft()
        if len(q) >= n:
            return JSONResponse({"detail": "Too many requests. Please wait and try again."}, status_code=429)
        q.append(t)
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = "no-store"
    return resp


for r in (auth.router, patients.router, ai.router, reports.router, chat.router, medicines.router, doctors.router, vitals.router, ews.router, federated.router, emergency.router, emergency.public,
          hospitals.router, labs.router, blood.router, wellness.router, analytics.router, admin.router, admin.family,
          messaging.router, hospital_ops.router, extras.router, extras.kiosk,
          ledger.router, rx_scan.router, wearables.router, telemedicine.router, voice.router, board.router, contact.router):
    app.include_router(r)


@app.get("/", tags=["meta"])
async def root():
    return {"app": settings.APP_NAME, "docs": "/docs", "status": "ok"}


@app.get("/health", tags=["meta"])
async def health():
    await get_db().command("ping") if settings.MONGO_URL != "mock" else None
    return {"status": "ok"}
