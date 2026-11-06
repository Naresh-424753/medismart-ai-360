"""Builds model inputs from a patient's stored profile + latest vitals/labs so users don't retype everything."""
from __future__ import annotations


def _age(dob):
    if not dob:
        return None
    from datetime import date
    y, m, d = map(int, dob.split("-"))
    t = date.today()
    return t.year - y - ((t.month, t.day) < (m, d))


def build(profile: dict, vitals: dict | None, labs: dict | None) -> dict:
    vitals, labs = vitals or {}, labs or {}
    diseases = " ".join(d.get("name", "").lower() for d in profile.get("diseases", []))
    f: dict = {}
    if (a := _age(profile.get("dob"))) is not None:
        f["age"] = a
    if profile.get("height_cm") and profile.get("weight_kg"):
        f["bmi"] = round(profile["weight_kg"] / (profile["height_cm"] / 100) ** 2, 1)
    if profile.get("sex"):
        f["male"] = 1 if profile["sex"].lower().startswith("m") else 0
    if "male" in f:
        f["female"] = 1 - f["male"]
    if vitals.get("systolic"):
        f["systolic_bp"] = vitals["systolic"]
    if vitals.get("diastolic"):
        f["diastolic_bp"] = vitals["diastolic"]
    if "tsh" in labs:
        f["tsh"] = labs["tsh"]
    if "hemoglobin" in labs:
        f["hemoglobin"] = labs["hemoglobin"]
    if "glucose_fasting" in labs:
        f["glucose"] = labs["glucose_fasting"]
    elif vitals.get("glucose"):
        f["glucose"] = vitals["glucose"]
    for k_in, k_out in (("total_cholesterol", "cholesterol"), ("creatinine", "creatinine"), ("alt", "alt"), ("ast", "ast"), ("bilirubin", "bilirubin")):
        if k_in in labs:
            f[k_out] = labs[k_in]
    f["diabetic"] = 1 if "diabet" in diseases else 0
    f["hypertensive"] = f["hypertension"] = 1 if "hypertension" in diseases or "blood pressure" in diseases else 0
    f["heart_disease"] = 1 if "heart" in diseases or "cardiac" in diseases else 0
    if "diabet" in diseases:
        f["family_history"] = 1

    return f
