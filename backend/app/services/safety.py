"""Drug-safety, vitals and geo helpers (framework-free, unit-tested)."""
from __future__ import annotations

import math

# ----------------------------------------------------------- drug interactions
# DEMO LIST ONLY - short and not exhaustive. Verify with a pharmacist or a
# licensed database (RxNorm / DrugBank / CDSCO) before clinical use.
INTERACTIONS = [
    ({"warfarin"}, {"aspirin", "ibuprofen", "diclofenac", "naproxen", "clopidogrel"}, "major",
     "Higher bleeding risk."),
    ({"clopidogrel"}, {"omeprazole", "esomeprazole"}, "moderate", "Omeprazole can reduce clopidogrel's effect."),
    ({"simvastatin", "atorvastatin"}, {"clarithromycin", "erythromycin", "itraconazole"}, "major",
     "Raised statin levels can cause muscle damage."),
    ({"sildenafil", "tadalafil"}, {"isosorbide", "nitroglycerin", "glyceryl trinitrate"}, "major",
     "Dangerous drop in blood pressure."),
    ({"tramadol"}, {"sertraline", "fluoxetine", "escitalopram"}, "major", "Risk of serotonin syndrome and seizures."),
    ({"lisinopril", "enalapril", "ramipril"}, {"spironolactone", "potassium chloride"}, "major",
     "High potassium (hyperkalaemia) risk."),
    ({"lisinopril", "enalapril", "ramipril", "losartan", "telmisartan"}, {"ibuprofen", "diclofenac", "naproxen"}, "moderate",
     "NSAIDs can blunt BP control and strain the kidneys."),
    ({"methotrexate"}, {"ibuprofen", "diclofenac", "naproxen", "aspirin"}, "major", "Methotrexate toxicity risk."),
    ({"digoxin"}, {"amiodarone", "verapamil", "clarithromycin"}, "major", "Raised digoxin levels."),
    ({"ciprofloxacin", "levofloxacin"}, {"antacid", "calcium", "iron", "magnesium"}, "moderate",
     "Take at least 2 hours apart; minerals reduce absorption."),
    ({"levothyroxine"}, {"calcium", "iron", "antacid"}, "moderate", "Take at least 4 hours apart."),
    ({"sertraline", "fluoxetine", "escitalopram"}, {"ibuprofen", "aspirin", "diclofenac"}, "moderate",
     "Increased bleeding risk."),
    ({"metformin"}, {"alcohol"}, "moderate", "Alcohol raises lactic acidosis risk."),
]

ALLERGY_CLASSES = {
    "penicillin": {"penicillin", "amoxicillin", "ampicillin", "amoxiclav", "augmentin", "cloxacillin", "piperacillin"},
    "sulfa": {"sulfamethoxazole", "cotrimoxazole", "sulfasalazine", "sulfadiazine"},
    "nsaid": {"aspirin", "ibuprofen", "diclofenac", "naproxen", "aceclofenac", "ketorolac", "nimesulide"},
    "cephalosporin": {"cefixime", "cefuroxime", "ceftriaxone", "cephalexin", "cefpodoxime"},
    "macrolide": {"azithromycin", "clarithromycin", "erythromycin"},
}


def _norm(name: str) -> str:
    return name.strip().lower()


def check_interactions(drugs: list[str]) -> list[dict]:
    names = [_norm(d) for d in drugs if d and d.strip()]
    found = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for group_a, group_b, severity, note in INTERACTIONS:
                if (a in group_a and b in group_b) or (b in group_a and a in group_b):
                    found.append({"drugs": [a, b], "severity": severity, "note": note})
    return found


def check_allergies(drugs: list[str], allergies: list[str]) -> list[dict]:
    alerts = []
    allergy_names = [_norm(a) for a in allergies if a and a.strip()]
    for drug in (_norm(d) for d in drugs if d and d.strip()):
        for allergy in allergy_names:
            members = ALLERGY_CLASSES.get(allergy, set()) | {allergy}
            if drug in members or any(m in drug for m in members):
                alerts.append({"drug": drug, "allergy": allergy,
                               "note": f"{drug} belongs to or matches the '{allergy}' allergy group."})
    return alerts


# ----------------------------------------------------------------- vitals rules
def evaluate_vitals(r: dict) -> list[dict]:
    """Return alerts for one reading. Thresholds are for typical adults."""
    alerts = []

    def add(metric, level, msg):
        alerts.append({"metric": metric, "level": level, "message": msg})

    hr, spo2, temp = r.get("heart_rate"), r.get("spo2"), r.get("temperature_c")
    sys_, dia, glu, rr = r.get("systolic"), r.get("diastolic"), r.get("glucose"), r.get("resp_rate")

    if hr is not None:
        if hr < 40 or hr > 150:
            add("heart_rate", "critical", f"Heart rate {hr:g} bpm is dangerously abnormal.")
        elif hr < 50 or hr > 120:
            add("heart_rate", "warning", f"Heart rate {hr:g} bpm is outside the usual resting range.")
    if spo2 is not None:
        if spo2 < 90:
            add("spo2", "critical", f"SpO2 {spo2:g}% is very low.")
        elif spo2 < 94:
            add("spo2", "warning", f"SpO2 {spo2:g}% is below normal.")
    if temp is not None:
        if temp >= 39.5 or temp < 34:
            add("temperature_c", "critical", f"Temperature {temp:g}°C is dangerous.")
        elif temp >= 38.0 or temp < 35:
            add("temperature_c", "warning", f"Temperature {temp:g}°C is abnormal.")
    if sys_ is not None and dia is not None:
        if sys_ >= 180 or dia >= 120 or sys_ < 80:
            add("blood_pressure", "critical", f"Blood pressure {sys_:g}/{dia:g} needs urgent attention.")
        elif sys_ >= 140 or dia >= 90 or sys_ < 90:
            add("blood_pressure", "warning", f"Blood pressure {sys_:g}/{dia:g} is outside the usual range.")
    if glu is not None:
        if glu < 54 or glu > 400:
            add("glucose", "critical", f"Glucose {glu:g} mg/dL is dangerous.")
        elif glu < 70 or glu > 250:
            add("glucose", "warning", f"Glucose {glu:g} mg/dL is outside the target range.")
    if rr is not None:
        if rr < 8 or rr > 30:
            add("resp_rate", "critical", f"Respiratory rate {rr:g}/min is dangerous.")
        elif rr < 10 or rr > 24:
            add("resp_rate", "warning", f"Respiratory rate {rr:g}/min is abnormal.")
    if r.get("fall_detected"):
        add("fall", "critical", "A fall was detected.")
    return alerts


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))
