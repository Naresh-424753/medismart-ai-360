"""Rule-based symptom checker (triage support, not diagnosis)."""
from __future__ import annotations

RED_FLAGS = {
    "chest pain": "Chest pain can be a heart emergency.",
    "difficulty breathing": "Breathing difficulty needs urgent care.",
    "shortness of breath": "Breathlessness needs urgent care.",
    "fainting": "Fainting needs urgent evaluation.",
    "unconscious": "Loss of consciousness is an emergency.",
    "slurred speech": "Possible stroke sign.",
    "face drooping": "Possible stroke sign.",
    "weakness on one side": "Possible stroke sign.",
    "severe bleeding": "Severe bleeding is an emergency.",
    "blood in vomit": "Vomiting blood needs urgent care.",
    "seizure": "Seizures need urgent care.",
    "suicidal": "Please reach out to a crisis line or emergency services right now.",
}

# condition -> (specialist, {symptom: weight}, self-care)
CONDITIONS = {
    "Common cold": ("General Physician", {"runny nose": 2, "sneezing": 2, "sore throat": 2, "cough": 1.5, "mild fever": 1, "congestion": 2}, "Rest, fluids, steam inhalation."),
    "Influenza (flu)": ("General Physician", {"fever": 2, "body ache": 2, "chills": 2, "cough": 1.5, "fatigue": 1.5, "headache": 1, "sore throat": 1}, "Rest, fluids; see a doctor if fever lasts over 3 days."),
    "Dengue (possible)": ("General Physician", {"high fever": 2.5, "fever": 1.5, "severe headache": 1.5, "pain behind eyes": 2.5, "joint pain": 2, "rash": 1.5, "body ache": 1.5, "vomiting": 1}, "Get a dengue test (NS1/IgM) and keep hydrated."),
    "Malaria (possible)": ("General Physician", {"fever": 1.5, "chills": 2.5, "sweating": 2, "headache": 1, "vomiting": 1, "body ache": 1}, "Get a malaria test promptly."),
    "COVID-19 / viral respiratory infection": ("General Physician", {"fever": 1.5, "dry cough": 2, "cough": 1, "loss of smell": 3, "loss of taste": 3, "fatigue": 1, "sore throat": 1}, "Isolate and test; monitor SpO2."),
    "Gastroenteritis": ("General Physician", {"diarrhea": 2.5, "vomiting": 2, "nausea": 1.5, "stomach pain": 2, "fever": 1}, "ORS and fluids; see a doctor if blood in stool or lasting over 2 days."),
    "Migraine": ("Neurologist", {"headache": 2, "severe headache": 2.5, "nausea": 1.5, "light sensitivity": 2.5, "visual aura": 3}, "Rest in a dark, quiet room; hydrate."),
    "Hypertension (possible)": ("Physician / Cardiologist", {"headache": 1, "dizziness": 1.5, "blurred vision": 1.5, "palpitations": 1.5, "nosebleed": 1}, "Measure BP at rest several times and consult a doctor."),
    "Diabetes (possible)": ("Physician / Endocrinologist", {"frequent urination": 2.5, "excessive thirst": 2.5, "fatigue": 1, "blurred vision": 1.5, "weight loss": 1.5, "slow healing wounds": 2}, "Get fasting glucose and HbA1c tests."),
    "Anemia (possible)": ("General Physician", {"fatigue": 2, "pale skin": 2.5, "dizziness": 1.5, "weakness": 1.5, "palpitations": 1, "shortness of breath": 1}, "Get a CBC and iron studies."),
    "Urinary tract infection": ("General Physician / Urologist", {"burning urination": 3, "frequent urination": 2, "lower abdominal pain": 1.5, "fever": 1}, "Drink water; get a urine routine test."),
    "Asthma / bronchospasm": ("Pulmonologist", {"wheezing": 3, "cough": 1, "chest tightness": 2.5, "shortness of breath": 2}, "Use prescribed inhaler; seek urgent care if severe."),
    "Tuberculosis (screening needed)": ("Pulmonologist", {"cough over 2 weeks": 3, "night sweats": 2.5, "weight loss": 2, "blood in sputum": 3, "fever": 1}, "Get a chest X-ray and sputum test."),
    "Allergic reaction": ("General Physician", {"rash": 2, "itching": 2.5, "sneezing": 1.5, "swelling": 2, "watery eyes": 1.5}, "Avoid the trigger; seek urgent care for swelling of face/throat."),
}


def _norm(s: str) -> str:
    return " ".join(s.lower().replace("_", " ").split())


def check(symptoms: list[str], free_text: str = "") -> dict:
    given = {_norm(s) for s in symptoms if s.strip()}
    text = " ".join(given) + " " + _norm(free_text)
    # free-text mentions count as symptoms
    for cond in CONDITIONS.values():
        for sym in cond[1]:
            if sym in text:
                given.add(sym)
    flags = [{"symptom": k, "message": m} for k, m in RED_FLAGS.items() if k in text]
    results = []
    for name, (spec, weights, selfcare) in CONDITIONS.items():
        total = sum(weights.values())
        hit = sum(w for s, w in weights.items() if s in given)
        if hit <= 0:
            continue
        matched = [s for s in weights if s in given]
        results.append(
            {
                "condition": name,
                "match": round(min(hit / (total * 0.6), 1.0), 2),
                "matched_symptoms": matched,
                "specialist": spec,
                "self_care": selfcare,
            }
        )
    results.sort(key=lambda r: -r["match"])
    urgency = "emergency" if flags else "see_doctor" if results and results[0]["match"] >= 0.6 else "self_care" if results else "unknown"
    return {
        "symptoms": sorted(given),
        "red_flags": flags,
        "urgency": urgency,
        "possible_conditions": results[:5],
        "disclaimer": "This is not a diagnosis. If symptoms are severe or worsening, see a doctor or call emergency services.",
    }


def all_symptoms() -> list[str]:
    s = set()
    for _, w, _ in CONDITIONS.values():
        s.update(w)
    return sorted(s)
