import os
import re
import secrets
from pathlib import Path


def _load_env_file() -> None:
    """Reads backend/.env into the environment (real environment variables win). Without this, .env would be silently ignored."""
    f = Path(__file__).resolve().parents[1] / ".env"
    if not f.is_file():
        return
    for line in f.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if v[:1] in "\"'" and v[-1:] == v[:1] and len(v) >= 2:
            v = v[1:-1]
        elif " #" in v:  # inline comment (values with # must be quoted)
            v = v.split(" #", 1)[0].strip()
        os.environ.setdefault(k.strip(), v)


_load_env_file()


def _b(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes"}


def _dev_secret() -> str:
    if not _b("DEV_MODE", "1"):
        return ""
    f = os.path.join(os.getenv("DEV_SECRET_DIR", "data"), ".dev_secret")
    try:
        return open(f).read().strip() or (_ for _ in ()).throw(OSError)
    except OSError:
        v = secrets.token_urlsafe(48)
        try:
            os.makedirs(os.path.dirname(f), exist_ok=True)
            with open(f, "w") as fh:
                fh.write(v)
            os.chmod(f, 0o600)
        except OSError:
            pass
        return v


class Settings:
    APP_NAME = "MediSmart AI 360"
    # "mock" -> in-memory database (demo/tests, data is lost on restart)
    MONGO_URL = os.getenv("MONGO_URL", "mock")
    DB_NAME = os.getenv("DB_NAME", "medismart")
    # If MongoDB cannot be reached at start, run on the in-memory database instead of refusing to start (data is lost on restart). Dev only.
    MONGO_FALLBACK = _b("MONGO_FALLBACK", "0")
    # No secret is stored in code. If JWT_SECRET is unset, DEV_MODE generates one and keeps it in data/.dev_secret (git-ignored);
    # DEV_MODE=0 refuses to start without it.
    JWT_SECRET = os.getenv("JWT_SECRET") or _dev_secret()
    JWT_EXPIRE_MIN = int(os.getenv("JWT_EXPIRE_MIN", "720"))
    # DEV_MODE returns OTPs in API responses so you can demo without SMS/email. NEVER enable in production.
    DEV_MODE = _b("DEV_MODE", "1")
    CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
    UPLOAD_DIR = os.getenv("UPLOAD_DIR", "data/uploads")
    # Set to a Google Cloud Storage bucket name to keep (encrypted) uploads there instead of on local disk.
    GCS_BUCKET = os.getenv("GCS_BUCKET", "")
    MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))
    # Fernet key (base64 urlsafe 32 bytes) for encrypting uploaded documents at rest
    DATA_KEY = os.getenv("DATA_KEY", "")
    # Credentials are never hard-coded: set them in backend/.env, or create the admin with `python create_admin.py`.
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")  # empty -> a random one-time password is generated and printed once
    DEMO_EMAIL_DOMAIN = os.getenv("DEMO_EMAIL_DOMAIN", "")  # needed only when SEED_DEMO=1
    DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "")  # empty -> random, printed once
    SEED_DEMO = _b("SEED_DEMO", "1")
    APP_TZ = os.getenv("APP_TZ", "Asia/Kolkata")
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASS = os.getenv("SMTP_PASS", "")
    SMTP_FROM = os.getenv("SMTP_FROM", "")
    # Shown on the public Contact page (optional)
    SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "")
    SUPPORT_PHONE = os.getenv("SUPPORT_PHONE", "")
    # WhatsApp number with country code, digits only (e.g. 919876543210). Shows a "Chat on WhatsApp" button.
    SUPPORT_WHATSAPP = re.sub(r"\D", "", os.getenv("SUPPORT_WHATSAPP", ""))
    TWILIO_SID = os.getenv("TWILIO_SID", "")
    TWILIO_TOKEN = os.getenv("TWILIO_TOKEN", "")
    TWILIO_SMS_FROM = os.getenv("TWILIO_SMS_FROM", "")
    TWILIO_WA_FROM = os.getenv("TWILIO_WA_FROM", "")  # e.g. whatsapp:+14155238886
    # Telemedicine (WebRTC). Calls work peer-to-peer with STUN; add a TURN server for users behind strict NAT/firewalls.
    STUN_URLS = [u.strip() for u in os.getenv("STUN_URLS", "stun:stun.l.google.com:19302").split(",") if u.strip()]
    TURN_URL = os.getenv("TURN_URL", "")
    TURN_USERNAME = os.getenv("TURN_USERNAME", "")
    TURN_CREDENTIAL = os.getenv("TURN_CREDENTIAL", "")
    TELE_ANYTIME = _b("TELE_ANYTIME", "1")  # 1 = allow joining at any time (demo); 0 = only from 15 min before to 90 min after the slot
    # Server-side speech-to-text for regional languages (all optional; without them the browser's own speech recognition is used)
    STT_PROVIDER = os.getenv("STT_PROVIDER", "auto")  # auto | whisper | bhashini
    WHISPER_API_KEY = os.getenv("WHISPER_API_KEY", "")
    WHISPER_BASE_URL = os.getenv("WHISPER_BASE_URL", "https://api.openai.com/v1")
    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
    BHASHINI_USER_ID = os.getenv("BHASHINI_USER_ID", "")
    BHASHINI_API_KEY = os.getenv("BHASHINI_API_KEY", "")
    BHASHINI_PIPELINE_ID = os.getenv("BHASHINI_PIPELINE_ID", "64392f96daac500b55c543cd")


settings = Settings()
