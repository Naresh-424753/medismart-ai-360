"""HTTP tests for: kiosk, report explainer, messaging, hospital ops, image AI, new risk models."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.test_api import _signup


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_kiosk_is_public(client):
    assert client.post("/kiosk/bmi", json={"weight_kg": 70, "height_cm": 170}).json()["bmi"] == 24.2
    assert client.get("/kiosk/emergency-numbers").json()["national_emergency"] == "112"
    assert client.get("/kiosk/hospitals?lat=28.6&lon=77.2").json()[0]["distance_km"] is not None


def test_new_risk_models_and_explainer(client):
    h = _signup(client, "extras@test.in")
    ids = {d["id"] for d in client.get("/ai/diseases", headers=h).json()}
    assert {"hypertension", "thyroid", "anemia", "cancer"} <= ids
    assert client.post("/ai/predict/anemia", headers=h, json={"values": {"hemoglobin": 7}}).status_code == 200
    r = client.post("/extras/explain-report", headers=h, json={"text": "ECG: ST elevation in leads V1-V4. Sinus rhythm."}).json()
    assert r["modality"] == "ecg" and r["urgent_count"] >= 1
    assert client.get("/wellness/sleep-schedule?wake_time=06:30&age=30", headers=h).json()["options"][0]["bedtime"] == "21:15"
    assert len(client.get("/ai/image-models", headers=h).json()) >= 6


def test_messages_need_an_appointment(client):
    h = _signup(client, "chatpat@test.in")
    docs = client.get("/doctors", headers=h).json()
    r = client.post(f"/messages/{docs[0]['user_id']}", headers=h, json={"text": "hi"})
    assert r.status_code == 403


def test_hospital_ops(client):
    h = _signup(client, "ops@hospital.in", role="hospital", organization="Ops Hospital")
    assert client.post("/hospital-ops/staff", headers=h, json={"name": "Nurse A", "role": "nurse"}).status_code == 201
    assert client.post("/hospital-ops/inventory", headers=h, json={"item": "Gloves", "quantity": 2, "reorder_level": 10}).status_code == 201
    assert client.get("/hospital-ops/alerts", headers=h).json()["low_stock"]
    body = {"theatre": "OT-1", "patient_name": "P", "procedure": "X", "surgeon": "S", "date": "2031-01-01", "start": "09:00", "end": "10:00"}
    assert client.post("/hospital-ops/theatre", headers=h, json=body).status_code == 201
    assert client.post("/hospital-ops/theatre", headers=h, json={**body, "start": "09:30", "end": "11:00"}).status_code == 409
    assert len(client.get("/hospital-ops/forecast?days=5", headers=h).json()["forecast"]) == 5
