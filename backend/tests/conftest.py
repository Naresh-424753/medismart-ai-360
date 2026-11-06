import os

os.environ.setdefault("MONGO_URL", "mock")
os.environ.setdefault("DEV_MODE", "1")
os.environ.setdefault("SEED_DEMO", "1")

import re

OTPS: dict = {}


def capture_otp_emails(mp):
    """OTPs are only ever emailed. API tests intercept the email and read the code from it."""
    from app.config import settings
    from app.routers import auth

    mp.setattr(settings, "SMTP_HOST", "test")
    mp.setattr(auth, "_send_email", lambda to, subject, body: OTPS.__setitem__(to, re.search(r"OTP is (\d+)", body).group(1)))
