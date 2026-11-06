import base64
import hashlib
import hmac
import os
import re
import secrets
import time
import uuid

import jwt

from .config import settings


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(h).decode()


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, s, h = stored.split("$")
        salt, want = base64.b64decode(s), base64.b64decode(h)
        got = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(got, want)
    except Exception:
        return False


def password_problem(pw: str) -> str | None:
    if len(pw) < 8:
        return "Password must be at least 8 characters"
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        return "Password must contain letters and digits"
    return None


def create_token(user_id: str, role: str) -> tuple[str, str]:
    jti = uuid.uuid4().hex
    payload = {"sub": user_id, "role": role, "jti": jti, "iat": int(time.time()), "exp": int(time.time()) + settings.JWT_EXPIRE_MIN * 60}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256"), jti


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])


def new_otp() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def hash_otp(email: str, purpose: str, otp: str) -> str:
    return hmac.new(settings.JWT_SECRET.encode(), f"{email}|{purpose}|{otp}".encode(), hashlib.sha256).hexdigest()


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def sign(value: str) -> str:
    return hmac.new(settings.JWT_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()[:16]
