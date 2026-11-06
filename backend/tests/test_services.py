import pytest
from app.services import chatbot, drugs, ml, report_analyzer as ra, symptoms, vitals_rules, wellness


def test_models_directionally_sensible():
    low = ml.predict("diabetes", {"age": 25, "bmi": 22, "glucose": 85, "systolic_bp": 110, "family_history": 0, "physically_active": 1})
    high = ml.predict("diabetes", {"age": 62, "bmi": 34, "glucose": 190, "systolic_bp": 150, "family_history": 1, "physically_active": 0})
    assert low["probability"] < 0.2 < 0.5 < high["probability"]
    assert high["factors"][0]["direction"] == "raises risk"
    assert 0 <= low["probability"] <= 1


@pytest.mark.parametrize("d", list(ml.SPECS))
def test_every_disease_predicts(d):
    r = ml.predict(d, {})
    assert r["level"] in {"low", "moderate", "high"} and r["advice"]
    assert ml.feature_schema(d)


def test_prediction_clamps_garbage_input():
    r = ml.predict("heart", {"age": "abc", "cholesterol": 99999, "smoker": 7})
    assert 0 <= r["probability"] <= 1


def test_health_score():
    assert ml.overall_health_score([])["score"] is None
    s = ml.overall_health_score([{"probability": 0.05}, {"probability": 0.1}])["score"]
    assert s > 80


REPORT = """
Hemoglobin      9.8 g/dL     12-15
Total WBC count 7,200 /cumm
Platelet Count  90000
Fasting Blood Sugar : 132 mg/dL
HbA1c 6.8 %
Total Cholesterol 240
HDL Cholesterol 35
LDL 160
TSH 2.1
SGPT 80
Vitamin D 12 ng/mL
Serum Creatinine 1.0
"""


def test_extract_and_analyze():
    v = ra.extract_values(REPORT)
    assert v["hemoglobin"] == 9.8
    assert v["wbc"] == 7200
    assert v["platelets"] == 90000
    assert v["glucose_fasting"] == 132
    assert v["hba1c"] == 6.8
    assert v["total_cholesterol"] == 240
    assert v["hdl"] == 35 and v["ldl"] == 160
    assert v["alt"] == 80 and v["vitamin_d"] == 12
    out = ra.analyze(v, sex="female")
    st = {f["key"]: f["status"] for f in out["findings"]}
    assert st["hemoglobin"] == "low" and st["wbc"] == "normal" and st["platelets"] == "low"
    assert st["glucose_fasting"] == "high" and st["tsh"] == "normal" and st["creatinine"] == "normal"
    assert out["abnormal_count"] >= 7
    assert "lft" in ra.detect_categories(v) and "cbc" in ra.detect_categories(v)


def test_ldl_not_confused_with_cholesterol_and_hdl():
    v = ra.extract_values("HDL Cholesterol 45\nLDL Cholesterol 120\nTotal Cholesterol 190")
    assert v == {"hdl": 45, "ldl": 120, "total_cholesterol": 190}


def test_sex_specific_hemoglobin():
    assert ra.analyze({"hemoglobin": 12.5}, "male")["findings"][0]["status"] == "low"
    assert ra.analyze({"hemoglobin": 12.5}, "female")["findings"][0]["status"] == "normal"


def test_empty_report():
    assert ra.analyze({})["total"] == 0


def test_compare():
    c = ra.compare({"hemoglobin": 12.5, "alt": 90}, {"hemoglobin": 9.8, "alt": 40})
    d = {x["test"]: x["trend"] for x in c}
    assert d["Hemoglobin"] == "improved" and d["ALT (SGPT)"] == "worsened"


def test_symptoms_and_red_flags():
    r = symptoms.check(["fever", "chills", "sweating"])
    assert r["possible_conditions"][0]["condition"].startswith("Malaria")
    assert r["urgency"] in {"see_doctor", "self_care"}
    r = symptoms.check(["headache"], "I have chest pain and difficulty breathing")
    assert r["urgency"] == "emergency" and len(r["red_flags"]) == 2
    assert symptoms.check([])["urgency"] == "unknown"


def test_drug_interactions_and_allergies():
    i = drugs.check_interactions(["Warfarin", "Ecosprin"])
    assert i and i[0]["severity"] == "severe"
    assert drugs.check_interactions(["paracetamol", "cetirizine"]) == []
    assert drugs.check_interactions(["ibuprofen", "diclofenac"])[0]["severity"] == "moderate"
    assert drugs.check_interactions(["metformin", "metformin"]) == []
    assert drugs.check_allergies("Amoxicillin", ["Penicillin"])
    assert drugs.check_allergies("Ibuprofen", ["NSAID"])
    assert not drugs.check_allergies("paracetamol", ["penicillin"])
    assert drugs.canon("Dolo 650") == "paracetamol"
    assert drugs.search("diabetes")


def test_vitals():
    assert vitals_rules.evaluate({"heart_rate": 72, "spo2": 98, "temperature": 36.8}) == []
    a = vitals_rules.evaluate({"spo2": 88, "heart_rate": 118, "fall_detected": True})
    assert vitals_rules.overall(a) == "critical"
    assert {x["metric"] for x in a} == {"spo2", "heart_rate", "fall"}
    assert vitals_rules.overall([]) == "normal"


def test_wellness():
    c = wellness.calculate(70, 170, 30, "male", "moderate", "lose")
    assert c["bmi"] == 24.2 and c["bmr"] == 1618 and c["calorie_target"] < c["tdee"]
    assert wellness.screen("depression", [2, 2])["positive_screen"]
    assert not wellness.screen("anxiety", [1, 0])["positive_screen"]
    with pytest.raises(ValueError):
        wellness.screen("anxiety", [5, 1])
    assert "extra salt" in wellness.diet_plan(2000, ["Hypertension"])["avoid"]


def test_chatbot():
    assert chatbot.reply("hello")["intent"] == "greeting"
    assert chatbot.reply("I have chest pain")["emergency"]
    assert chatbot.reply("what is hba1c?")["intent"] == "term"
    assert chatbot.reply("what is paracetamol used for?")["intent"] == "medicine"
    assert chatbot.reply("fever and cough since 2 days")["intent"] == "symptoms"
    h = chatbot.reply("मुझे बुखार और खांसी है")
    assert h["lang"] == "hi" and h["intent"] == "symptoms"
    assert chatbot.reply("मेरे सीने में दर्द है")["emergency"]
    assert chatbot.reply("zzzz")["intent"] == "fallback"


# ---- added: new risk models, radiology explainer, image screening ----
def test_new_risk_models_exist_and_respond_to_inputs():
    from app.services import ml
    for d in ("hypertension", "thyroid", "anemia", "cancer"):
        assert d in ml.SPECS and ml.predict(d, {})["level"] in ("low", "moderate", "high")
    assert ml.predict("anemia", {"hemoglobin": 7, "male": 0, "fatigue": 1, "pale_skin": 1})["probability"] > ml.predict("anemia", {"hemoglobin": 15, "male": 1})["probability"]
    assert ml.predict("thyroid", {"tsh": 30, "neck_swelling": 1})["probability"] > ml.predict("thyroid", {"tsh": 2})["probability"]
    assert ml.predict("hypertension", {"systolic_bp": 170, "diastolic_bp": 105})["level"] == "high"


def test_radiology_explainer_flags_urgent_and_ignores_negations():
    from app.services import radiology
    r = radiology.explain("Chest X-ray: No pneumothorax. Right lower lobe consolidation with small pleural effusion. Cardiomegaly.")
    terms = {f["term"] for f in r["findings"]}
    assert {"consolidation", "pleural effusion", "cardiomegaly"} <= terms and "pneumothorax" not in terms
    e = radiology.explain("ECG shows ST elevation in leads II, III, aVF. Sinus tachycardia.")
    assert e["modality"] == "ecg" and e["urgent_count"] >= 1 and e["findings"][0]["severity"] == "urgent"


def test_image_screening_heuristics_run():
    import cv2
    import numpy as np
    from app.services import image_ai
    img = (np.random.default_rng(0).normal(120, 40, (256, 256, 3))).clip(0, 255).astype(np.uint8)
    data = cv2.imencode(".png", img)[1].tobytes()
    for t in ("chest_xray", "brain_mri", "skin", "retina", "cataract", "segment"):
        r = image_ai.analyze(data, t)
        assert r["mode"] == "heuristic-demo" and r["overlay_png"].startswith("data:image/png") and "report" in r
    assert image_ai.analyze(data, "fracture")["available"] is False
