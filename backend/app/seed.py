"""Demo data: admin account, sample hospitals, pharmacies, doctors and a demo patient."""
from .common import new_id, now
from .config import settings
from .security import hash_password
from .routers.auth import _health_id
import secrets


def _hospital(name, city, lat, lon, gen, icu, em, vent, spec):
    return {"id": new_id(), "user_id": None, "name": name, "address": f"{city} city centre", "city": city, "phone": "0000000000", "lat": lat, "lon": lon,
            "departments": ["OPD", "Emergency", "Cardiology", "Pediatrics"], "specialities": spec, "rating": 4.2, "verified": True,
            "beds": {"general": {"total": gen[0], "available": gen[1]}, "icu": {"total": icu[0], "available": icu[1]},
                     "emergency": {"total": em[0], "available": em[1]}, "ventilator": {"total": vent[0], "available": vent[1]}}}


async def seed(db):
    """First start only. Creates the administrator (password stored only as a salted scrypt hash) and, if SEED_DEMO=1, demo data.
    No e-mail address or password is written in code: they come from the environment or are generated and printed once."""
    if settings.ADMIN_EMAIL and not await db.users.find_one({"email": settings.ADMIN_EMAIL}):
        pw = settings.ADMIN_PASSWORD
        if not pw:
            pw = secrets.token_urlsafe(12)
            print(f"[MediSmart] First-run administrator created: {settings.ADMIN_EMAIL}  one-time password: {pw}  (shown once; change it after login)", flush=True)
        await db.users.insert_one({"id": new_id(), "name": "Super Admin", "email": settings.ADMIN_EMAIL, "phone": "", "role": "super_admin", "password_hash": hash_password(pw),
                                   "email_verified": True, "approved": True, "status": "active", "two_factor": False, "created_at": now()})
    elif not settings.ADMIN_EMAIL and not await db.users.find_one({"role": "super_admin"}):
        print("[MediSmart] No administrator exists. Set ADMIN_EMAIL (and optionally ADMIN_PASSWORD) in backend/.env, or run: python create_admin.py", flush=True)
    if not settings.SEED_DEMO or await db.hospitals.count_documents({}) > 0:
        return
    if not settings.DEMO_EMAIL_DOMAIN:
        print("[MediSmart] SEED_DEMO=1 needs DEMO_EMAIL_DOMAIN in backend/.env (demo accounts are named <role>@<that domain>); demo data skipped.", flush=True)
        return
    dom = settings.DEMO_EMAIL_DOMAIN
    demo_pw = settings.DEMO_PASSWORD
    if not demo_pw:
        demo_pw = secrets.token_urlsafe(10)
        print(f"[MediSmart] Demo accounts (patient@{dom}, doctor1..6@{dom}, pharmacist@{dom}) one-time password: {demo_pw}", flush=True)
    await db.hospitals.insert_many([
        _hospital("City General Hospital", "Delhi", 28.6139, 77.2090, (200, 60), (30, 4), (20, 6), (10, 2), ["Cardiology", "Neurology", "Orthopedics"]),
        _hospital("Lifeline Multispeciality", "Delhi", 28.5355, 77.3910, (150, 35), (20, 0), (12, 0), (8, 1), ["Oncology", "Nephrology"]),
        _hospital("Sunrise Medical Centre", "Mumbai", 19.0760, 72.8777, (300, 90), (40, 7), (25, 9), (14, 3), ["Cardiology", "Pediatrics"]),
        _hospital("Apex Care Hospital", "Bengaluru", 12.9716, 77.5946, (180, 50), (25, 5), (15, 4), (9, 2), ["Neurology", "Gastroenterology"]),
        _hospital("Riverside Hospital", "Lucknow", 26.8467, 80.9462, (120, 28), (15, 2), (10, 3), (6, 1), ["General Medicine", "Orthopedics"]),
    ])
    await db.pharmacies.insert_many([
        {"id": new_id(), "user_id": None, "name": "HealthPlus Pharmacy", "city": "Delhi", "address": "Connaught Place", "phone": "0000000001", "open_24h": True},
        {"id": new_id(), "user_id": None, "name": "MediCare Chemist", "city": "Mumbai", "address": "Andheri West", "phone": "0000000002", "open_24h": False},
        {"id": new_id(), "user_id": None, "name": "CityMeds", "city": "Bengaluru", "address": "MG Road", "phone": "0000000003", "open_24h": True},
    ])
    pw = hash_password(demo_pw)
    ph_uid = new_id()
    await db.users.insert_one({"id": ph_uid, "name": "Demo Pharmacist", "email": f"pharmacist@{dom}", "phone": "", "role": "pharmacist", "password_hash": pw, "email_verified": True, "approved": True, "status": "active", "two_factor": False, "created_at": now()})
    await db.pharmacies.update_one({"name": "HealthPlus Pharmacy"}, {"$set": {"user_id": ph_uid}})
    for nm, price in [("paracetamol", 20), ("metformin", 45), ("amoxicillin", 90), ("cetirizine", 25), ("azithromycin", 120), ("pantoprazole", 60), ("amlodipine", 35)]:
        await db.pharmacy_stock.insert_one({"id": new_id(), "user_id": ph_uid, "name": nm, "quantity": 100, "price": price, "expiry": "2028-01-31", "updated": now()})
    docs = [("Dr. Asha Verma", "General Physician", "Delhi", 400, 12), ("Dr. Rohan Mehta", "Cardiologist", "Delhi", 900, 15), ("Dr. Neha Iyer", "Endocrinologist", "Bengaluru", 800, 10),
            ("Dr. Sameer Khan", "Neurologist", "Mumbai", 1000, 18), ("Dr. Priya Nair", "Psychiatrist", "Delhi", 700, 9), ("Dr. Imran Ali", "Pulmonologist", "Lucknow", 600, 11)]
    for i, (name, spec, city, fee, exp) in enumerate(docs):
        uid = new_id()
        await db.users.insert_one({"id": uid, "name": name, "email": f"doctor{i + 1}@{dom}", "phone": "", "role": "doctor", "password_hash": pw, "email_verified": True, "approved": True, "status": "active", "two_factor": False, "created_at": now()})
        await db.doctors.insert_one({"id": new_id(), "user_id": uid, "name": name, "specialization": spec, "license_no": f"DEMO-{1000 + i}", "experience_years": exp, "fee": fee, "bio": f"{spec} with {exp} years of experience.",
                                     "hospital": "City General Hospital", "city": city, "availability": {"days": [0, 1, 2, 3, 4, 5], "slots": ["09:00", "09:30", "10:00", "10:30", "11:00", "14:00", "14:30", "15:00", "16:00"]}, "rating": 4.5, "rating_count": 20})
    uid = new_id()
    await db.users.insert_one({"id": uid, "name": "Demo Patient", "email": f"patient@{dom}", "phone": "", "role": "patient", "password_hash": pw, "email_verified": True, "approved": True, "status": "active", "two_factor": False, "created_at": now()})
    await db.patients.insert_one({"id": new_id(), "user_id": uid, "health_id": _health_id(), "qr_token": secrets.token_urlsafe(16), "dob": "1985-06-15", "sex": "male", "blood_group": "B+", "height_cm": 172, "weight_kg": 82,
                                  "address": "", "city": "Delhi", "allergies": [{"id": new_id(), "name": "Penicillin", "severity": "high", "reaction": "Rash"}], "diseases": [], "surgeries": [], "vaccinations": [], "emergency_contacts": []})
