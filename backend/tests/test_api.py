"""HTTP smoke test using FastAPI's TestClient (in-memory database).
Run:  cd backend && pytest -q
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

from .conftest import OTPS, capture_otp_emails


@pytest.fixture(scope="module")
def client():
    mp = pytest.MonkeyPatch()
    capture_otp_emails(mp)
    with TestClient(app) as c:  # runs lifespan -> seeds demo data
        yield c
    mp.undo()


def _signup(client, email, role="patient", **extra):
    r = client.post("/auth/register", json={"name": "Test User", "email": email, "password": "Passw0rd!x", "role": role, **extra})
    assert r.status_code == 201, r.text
    v = client.post("/auth/verify-otp", json={"email": email, "otp": OTPS[email]})
    assert v.status_code == 200, v.text
    t = client.post("/auth/login", json={"email": email, "password": "Passw0rd!x"})
    assert t.status_code == 200, t.text
    return {"Authorization": "Bearer " + t.json()["token"]}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_unauthenticated_blocked(client):
    assert client.get("/patients/me").status_code == 401


def test_patient_flow(client):
    h = _signup(client, "smoke@test.in")
    assert client.put("/patients/me", json={"dob": "1980-01-01", "sex": "male", "blood_group": "A+", "height_cm": 175, "weight_kg": 80}, headers=h).status_code == 200
    r = client.post("/ai/predict/diabetes", json={"values": {"glucose": 150}}, headers=h)
    assert r.status_code == 200 and 0 <= r.json()["probability"] <= 1
    r = client.post("/reports/analyze", json={"text": "Hemoglobin 9.5 g/dL"}, headers=h)
    assert r.status_code == 200 and r.json()["abnormal_count"] == 1
    assert client.post("/chat", json={"message": "I have fever and cough"}, headers=h).json()["intent"] == "symptoms"


def test_role_isolation(client):
    h = _signup(client, "iso@test.in")
    assert client.get("/admin/stats", headers=h).status_code == 403
    assert client.get("/doctor/dashboard", headers=h).status_code == 403


def test_device_ingest(client):
    h = _signup(client, "iot@test.in")
    key = client.post("/vitals/devices", json={"label": "esp"}, headers=h).json()["api_key"]
    assert client.post("/vitals/ingest", json={"heart_rate": 72, "spo2": 98}).status_code == 401
    r = client.post("/vitals/ingest", json={"heart_rate": 72, "spo2": 98}, headers={"X-Device-Key": key})
    assert r.status_code == 200 and r.json()["status"] == "normal"
