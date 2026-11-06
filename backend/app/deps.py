from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt

from .db import get_db
from .security import decode_token

bearer = HTTPBearer(auto_error=False)


async def current_user(request: Request, cred: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    if not cred:
        raise HTTPException(401, "Not authenticated")
    return await user_from_token(cred.credentials)


async def user_from_token(token: str) -> dict:
    db = get_db()
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")
    if await db.revoked_tokens.find_one({"jti": payload["jti"]}):
        raise HTTPException(401, "Session ended - please log in again")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
    if not user or user.get("status") == "suspended":
        raise HTTPException(401, "Account unavailable")
    user["_jti"] = payload["jti"]
    return user


def require_roles(*roles: str):
    async def dep(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles and user["role"] != "super_admin":
            raise HTTPException(403, "You do not have access to this resource")
        return user
    return dep


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")
