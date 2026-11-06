"""Create (or reset) the administrator without writing any credential in a file.
   python create_admin.py            # asks for e-mail and password (hidden input)
The password is stored only as a salted scrypt hash."""
import asyncio
import getpass
import sys

from app.common import new_id, now
from app.db import get_db
from app.security import hash_password


async def main():
    from app.config import settings
    if settings.MONGO_URL == "mock":
        sys.exit("MONGO_URL is 'mock' (in-memory), so the admin would vanish when this script ends. Set MONGO_URL in backend/.env first.")
    print(f"Using database: {settings.MONGO_URL.split('@')[-1]} / {settings.DB_NAME}")
    email = input("Admin e-mail: ").strip().lower()
    pw = getpass.getpass("Password (min 12 chars): ")
    if len(pw) < 12 or pw != getpass.getpass("Repeat password: "):
        sys.exit("Passwords differ or are shorter than 12 characters.")
    db = get_db()
    ph = hash_password(pw)
    if await db.users.find_one({"email": email}):
        await db.users.update_one({"email": email}, {"$set": {"password_hash": ph, "role": "super_admin", "status": "active"}})
        print("Existing account promoted/reset.")
    else:
        await db.users.insert_one({"id": new_id(), "name": "Super Admin", "email": email, "phone": "", "role": "super_admin", "password_hash": ph,
                                   "email_verified": True, "approved": True, "status": "active", "two_factor": False, "created_at": now()})
        print("Administrator created.")

asyncio.run(main())
