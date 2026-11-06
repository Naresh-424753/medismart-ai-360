"""Explainable disease-risk models.

IMPORTANT: these are DEMO models. They are trained at start-up on synthetic
data generated from published-style risk-factor relationships (age, BMI, BP,
glucose ...). They show the pipeline (train -> predict -> explain) and are NOT
clinically validated. Replace `_generate()` with a real dataset (e.g. Pima
diabetes, UCI heart, CKD, Framingham) to get real models.
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

# feature: (label, min, max, default, mean, sd, true_weight, kind)  kind: num|bin
SPECS: dict[str, dict] = {
    "diabetes": {
        "title": "Diabetes Risk",
        "intercept": -1.6,
        "features": {
            "age": ("Age (years)", 1, 110, 40, 45, 14, 0.55, "num"),
            "bmi": ("BMI", 10, 60, 25, 27, 5.5, 0.65, "num"),
            "glucose": ("Fasting glucose (mg/dL)", 50, 400, 100, 105, 25, 1.4, "num"),
            "systolic_bp": ("Systolic BP (mmHg)", 70, 250, 120, 124, 16, 0.35, "num"),
            "family_history": ("Family history of diabetes (0/1)", 0, 1, 0, 0.3, 0.46, 0.7, "bin"),
            "physically_active": ("Physically active (0/1)", 0, 1, 1, 0.55, 0.5, -0.5, "bin"),
        },
    },
    "heart": {
        "title": "Heart Disease Risk",
        "intercept": -1.9,
        "features": {
            "age": ("Age (years)", 1, 110, 45, 50, 14, 0.9, "num"),
            "male": ("Male sex (0/1)", 0, 1, 0, 0.5, 0.5, 0.6, "bin"),
            "cholesterol": ("Total cholesterol (mg/dL)", 100, 450, 190, 205, 40, 0.7, "num"),
            "systolic_bp": ("Systolic BP (mmHg)", 70, 250, 120, 128, 18, 0.7, "num"),
            "smoker": ("Smoker (0/1)", 0, 1, 0, 0.25, 0.43, 0.8, "bin"),
            "diabetic": ("Diabetic (0/1)", 0, 1, 0, 0.12, 0.33, 0.7, "bin"),
            "bmi": ("BMI", 10, 60, 25, 27, 5.5, 0.3, "num"),
        },
    },
    "kidney": {
        "title": "Kidney Disease Risk",
        "intercept": -2.2,
        "features": {
            "age": ("Age (years)", 1, 110, 45, 50, 15, 0.6, "num"),
            "creatinine": ("Serum creatinine (mg/dL)", 0.3, 15, 1.0, 1.1, 0.5, 1.6, "num"),
            "systolic_bp": ("Systolic BP (mmHg)", 70, 250, 120, 128, 18, 0.6, "num"),
            "diabetic": ("Diabetic (0/1)", 0, 1, 0, 0.15, 0.36, 0.8, "bin"),
            "hypertensive": ("Hypertension (0/1)", 0, 1, 0, 0.3, 0.46, 0.7, "bin"),
            "proteinuria": ("Protein in urine (0/1)", 0, 1, 0, 0.1, 0.3, 1.2, "bin"),
        },
    },
    "liver": {
        "title": "Liver Disease Risk",
        "intercept": -2.0,
        "features": {
            "age": ("Age (years)", 1, 110, 40, 44, 14, 0.3, "num"),
            "alt": ("ALT / SGPT (U/L)", 5, 600, 30, 38, 25, 1.0, "num"),
            "ast": ("AST / SGOT (U/L)", 5, 600, 28, 35, 22, 0.9, "num"),
            "bilirubin": ("Total bilirubin (mg/dL)", 0.1, 20, 0.8, 0.9, 0.5, 1.1, "num"),
            "alcohol_use": ("Regular alcohol use (0/1)", 0, 1, 0, 0.25, 0.43, 0.9, "bin"),
            "bmi": ("BMI", 10, 60, 25, 27, 5.5, 0.4, "num"),
        },
    },
    "stroke": {
        "title": "Stroke Risk",
        "intercept": -2.3,
        "features": {
            "age": ("Age (years)", 1, 110, 50, 52, 15, 1.1, "num"),
            "hypertension": ("Hypertension (0/1)", 0, 1, 0, 0.3, 0.46, 0.8, "bin"),
            "heart_disease": ("Heart disease (0/1)", 0, 1, 0, 0.08, 0.27, 0.9, "bin"),
            "glucose": ("Fasting glucose (mg/dL)", 50, 400, 100, 105, 25, 0.6, "num"),
            "bmi": ("BMI", 10, 60, 25, 27, 5.5, 0.3, "num"),
            "smoker": ("Smoker (0/1)", 0, 1, 0, 0.25, 0.43, 0.6, "bin"),
        },
    },
    "hypertension": {
        "title": "Blood Pressure (Hypertension) Risk",
        "intercept": -1.5,
        "features": {
            "age": ("Age (years)", 1, 110, 40, 45, 15, 0.8, "num"),
            "bmi": ("BMI", 10, 60, 25, 27, 5.5, 0.6, "num"),
            "systolic_bp": ("Systolic BP (mmHg)", 70, 250, 120, 124, 16, 1.5, "num"),
            "diastolic_bp": ("Diastolic BP (mmHg)", 40, 150, 80, 80, 10, 0.9, "num"),
            "high_salt_diet": ("High-salt diet (0/1)", 0, 1, 0, 0.4, 0.49, 0.5, "bin"),
            "smoker": ("Smoker (0/1)", 0, 1, 0, 0.25, 0.43, 0.4, "bin"),
            "family_history": ("Family history of hypertension (0/1)", 0, 1, 0, 0.35, 0.48, 0.6, "bin"),
            "physically_active": ("Physically active (0/1)", 0, 1, 1, 0.55, 0.5, -0.4, "bin"),
        },
    },
    "thyroid": {
        "title": "Thyroid Disorder Risk",
        "intercept": -2.1,
        "features": {
            "age": ("Age (years)", 1, 110, 40, 45, 15, 0.4, "num"),
            "male": ("Male sex (0/1)", 0, 1, 0, 0.5, 0.5, -0.6, "bin"),
            "tsh": ("TSH (mIU/L)", 0.01, 100, 2.5, 2.8, 2.0, 1.4, "num"),
            "family_history": ("Family history of thyroid disease (0/1)", 0, 1, 0, 0.2, 0.4, 0.8, "bin"),
            "fatigue": ("Persistent fatigue (0/1)", 0, 1, 0, 0.3, 0.46, 0.5, "bin"),
            "weight_change": ("Unexplained weight change (0/1)", 0, 1, 0, 0.2, 0.4, 0.6, "bin"),
            "neck_swelling": ("Neck swelling / goitre (0/1)", 0, 1, 0, 0.05, 0.22, 1.1, "bin"),
        },
    },
    "anemia": {
        "title": "Anemia Risk",
        "intercept": -1.8,
        "features": {
            "age": ("Age (years)", 1, 110, 35, 40, 17, 0.1, "num"),
            "male": ("Male sex (0/1)", 0, 1, 0, 0.5, 0.5, -0.9, "bin"),
            "hemoglobin": ("Hemoglobin (g/dL)", 3, 20, 13, 13.2, 1.8, -1.9, "num"),
            "fatigue": ("Persistent fatigue / weakness (0/1)", 0, 1, 0, 0.3, 0.46, 0.6, "bin"),
            "pale_skin": ("Pale skin / nails (0/1)", 0, 1, 0, 0.12, 0.33, 0.8, "bin"),
            "heavy_periods": ("Heavy menstrual bleeding (0/1)", 0, 1, 0, 0.12, 0.33, 0.7, "bin"),
            "vegetarian_diet": ("Vegetarian diet with low iron intake (0/1)", 0, 1, 0, 0.3, 0.46, 0.4, "bin"),
        },
    },
    "cancer": {
        "title": "Cancer Risk (lifestyle & history screening)",
        "intercept": -2.6,
        "features": {
            "age": ("Age (years)", 1, 110, 45, 48, 16, 1.0, "num"),
            "smoker": ("Smoker (0/1)", 0, 1, 0, 0.25, 0.43, 0.9, "bin"),
            "tobacco_chewing": ("Chews tobacco / gutka (0/1)", 0, 1, 0, 0.12, 0.33, 0.9, "bin"),
            "alcohol_use": ("Regular alcohol use (0/1)", 0, 1, 0, 0.25, 0.43, 0.5, "bin"),
            "family_history_cancer": ("Close relative with cancer (0/1)", 0, 1, 0, 0.15, 0.36, 0.8, "bin"),
            "bmi": ("BMI", 10, 60, 25, 27, 5.5, 0.3, "num"),
            "unexplained_weight_loss": ("Unexplained weight loss (0/1)", 0, 1, 0, 0.05, 0.22, 1.0, "bin"),
            "persistent_lump_or_cough": ("Persistent lump, sore or cough >3 weeks (0/1)", 0, 1, 0, 0.06, 0.24, 1.1, "bin"),
        },
    },
}


def _generate(disease: str, n: int = 6000, seed: int = 7):
    spec = SPECS[disease]
    rng = np.random.default_rng(seed)
    cols, logit = [], np.full(n, spec["intercept"], dtype=float)
    for _, (_, lo, hi, _, mu, sd, w, kind) in spec["features"].items():
        if kind == "bin":
            x = rng.binomial(1, mu, n).astype(float)
            z = (x - mu) / sd
        else:
            x = np.clip(rng.normal(mu, sd, n), lo, hi)
            z = (x - mu) / sd
        logit += w * z
        cols.append(x)
    p = 1 / (1 + np.exp(-logit))
    y = rng.binomial(1, p)
    return np.column_stack(cols), y


@lru_cache(maxsize=None)
def _model(disease: str):
    X, y = _generate(disease)
    pipe = make_pipeline(StandardScaler(), LogisticRegression(max_iter=500))
    pipe.fit(X, y)
    return pipe


def feature_schema(disease: str) -> list[dict]:
    return [
        {"name": k, "label": v[0], "min": v[1], "max": v[2], "default": v[3], "binary": v[7] == "bin"}
        for k, v in SPECS[disease]["features"].items()
    ]


def level_for(p: float) -> str:
    return "low" if p < 0.2 else "moderate" if p < 0.5 else "high"


ADVICE = {
    "diabetes": {
        "low": "Keep a balanced diet and stay active. Re-check fasting glucose yearly.",
        "moderate": "Reduce refined sugar, aim for 150 min/week of activity and get HbA1c / fasting glucose tested.",
        "high": "Please consult a doctor soon for HbA1c and fasting glucose tests and a lifestyle plan.",
    },
    "heart": {
        "low": "Maintain healthy habits; check BP and cholesterol every year.",
        "moderate": "Limit salt and saturated fat, stop smoking if you smoke and get a lipid profile and ECG.",
        "high": "Please see a cardiologist or physician soon. Seek emergency care for chest pain or breathlessness.",
    },
    "kidney": {
        "low": "Stay hydrated and keep BP and sugar controlled.",
        "moderate": "Get serum creatinine, eGFR and a urine albumin test; avoid long-term NSAID use.",
        "high": "Please consult a nephrologist or physician soon for kidney function tests.",
    },
    "liver": {
        "low": "Limit alcohol and keep a healthy weight.",
        "moderate": "Reduce alcohol and fatty foods and repeat a liver function test (LFT).",
        "high": "Please consult a doctor soon for an LFT review and an ultrasound if advised.",
    },
    "stroke": {
        "low": "Keep BP, sugar and weight in check.",
        "moderate": "Control BP, avoid smoking and review risk factors with your doctor.",
        "high": "Please consult a doctor soon. Know the FAST signs (Face, Arm, Speech, Time) and call emergency services if they appear.",
    },
    "hypertension": {
        "low": "Check BP at least yearly, limit salt and stay active.",
        "moderate": "Monitor BP at home, cut salt, lose excess weight and review with a doctor.",
        "high": "Please see a doctor soon for BP confirmation and treatment. Seek urgent care for severe headache, chest pain or breathlessness.",
    },
    "thyroid": {
        "low": "No action needed now; test TSH if symptoms develop.",
        "moderate": "Consider a TSH / T3 / T4 test, especially with fatigue, weight change or family history.",
        "high": "Please consult a doctor or endocrinologist for thyroid tests (TSH, T3, T4, anti-TPO) and an ultrasound if advised.",
    },
    "anemia": {
        "low": "Eat iron-rich foods (greens, pulses, jaggery, meat) with vitamin C and test CBC yearly.",
        "moderate": "Get a CBC with iron studies and B12/folate levels; improve iron and vitamin intake.",
        "high": "Please see a doctor soon for CBC, iron studies and the cause (diet, blood loss or other); do not self-medicate with high-dose iron.",
    },
    "cancer": {
        "low": "Avoid tobacco, limit alcohol, stay active and follow age-appropriate screening schedules.",
        "moderate": "Stop tobacco/alcohol, discuss screening (oral, breast, cervical, colon) with your doctor.",
        "high": "Please see a doctor soon to examine the warning signs and arrange the right tests. This is a screening score, not a cancer diagnosis.",
    },
}

DISCLAIMER = (
    "Demo model trained on synthetic data - for education and screening support only. "
    "It is not a diagnosis. Please consult a qualified doctor."
)


def predict(disease: str, values: dict) -> dict:
    if disease not in SPECS:
        raise KeyError(disease)
    spec = SPECS[disease]
    model = _model(disease)
    row, z_rows = [], []
    for k, (label, lo, hi, default, mu, sd, _, kind) in spec["features"].items():
        v = values.get(k, default)
        try:
            v = float(v)
        except (TypeError, ValueError):
            v = float(default)
        v = min(max(v, lo), hi)
        row.append(v)
    X = np.array([row])
    p = float(model.predict_proba(X)[0, 1])
    scaler, lr = model.steps[0][1], model.steps[1][1]
    z = scaler.transform(X)[0]
    contrib = z * lr.coef_[0]
    names = list(spec["features"].items())
    factors = sorted(
        (
            {
                "feature": k,
                "label": v[0],
                "value": row[i],
                "impact": round(float(contrib[i]), 3),
                "direction": "raises risk" if contrib[i] > 0.05 else "lowers risk" if contrib[i] < -0.05 else "neutral",
            }
            for i, (k, v) in enumerate(names)
        ),
        key=lambda f: -abs(f["impact"]),
    )
    lvl = level_for(p)
    return {
        "disease": disease,
        "title": spec["title"],
        "probability": round(p, 4),
        "score": round(p * 100),
        "level": lvl,
        "factors": factors,
        "advice": ADVICE[disease][lvl],
        "disclaimer": DISCLAIMER,
    }


def overall_health_score(predictions: list[dict]) -> dict:
    """100 = best. Weighted average of (1 - risk) with a penalty for any high-risk result."""
    if not predictions:
        return {"score": None, "label": "No assessments yet"}
    avg = sum(p["probability"] for p in predictions) / len(predictions)
    worst = max(p["probability"] for p in predictions)
    score = round(100 * (1 - (0.6 * avg + 0.4 * worst)))
    label = "Good" if score >= 75 else "Fair" if score >= 50 else "Needs attention"
    return {"score": max(0, min(100, score)), "label": label}


def bmi(weight_kg: float, height_cm: float) -> float:
    return round(weight_kg / ((height_cm / 100) ** 2), 1)
