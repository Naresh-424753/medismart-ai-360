"""Small educational drug knowledge base: info, interactions, allergy classes."""
from __future__ import annotations

# name -> info. NOT exhaustive; extend or swap for a licensed drug database (e.g. RxNorm / CIMS).
DRUGS: dict[str, dict] = {
    "paracetamol": {"class": "analgesic/antipyretic", "uses": "Fever and mild-moderate pain", "adult_dose": "500-1000 mg every 6-8 h; max 4 g/day", "notes": "Avoid overdose; caution in liver disease.", "brands": ["Crocin", "Dolo 650", "Calpol"]},
    "ibuprofen": {"class": "nsaid", "uses": "Pain, inflammation, fever", "adult_dose": "200-400 mg every 6-8 h with food", "notes": "Avoid in kidney disease, ulcers; take with food.", "brands": ["Brufen", "Combiflam"]},
    "aspirin": {"class": "nsaid", "uses": "Pain; low dose for blood-clot prevention", "adult_dose": "75-325 mg/day as prescribed", "notes": "Bleeding risk.", "brands": ["Disprin", "Ecosprin"]},
    "diclofenac": {"class": "nsaid", "uses": "Pain and inflammation", "adult_dose": "50 mg two-three times daily", "notes": "Take with food; avoid in kidney/heart disease.", "brands": ["Voveran"]},
    "amoxicillin": {"class": "penicillin", "uses": "Bacterial infections", "adult_dose": "250-500 mg every 8 h", "notes": "Complete the course; avoid in penicillin allergy.", "brands": ["Mox", "Novamox"]},
    "azithromycin": {"class": "macrolide", "uses": "Respiratory and other bacterial infections", "adult_dose": "500 mg once daily for 3 days", "notes": "Can affect heart rhythm in rare cases.", "brands": ["Azithral", "Zithromax"]},
    "ciprofloxacin": {"class": "fluoroquinolone", "uses": "Urinary and GI bacterial infections", "adult_dose": "250-500 mg every 12 h", "notes": "Avoid antacids within 2 h.", "brands": ["Ciplox"]},
    "metformin": {"class": "biguanide", "uses": "Type 2 diabetes", "adult_dose": "500-1000 mg twice daily with meals", "notes": "Take with food; caution in kidney disease.", "brands": ["Glycomet", "Glucophage"]},
    "glimepiride": {"class": "sulfonylurea", "uses": "Type 2 diabetes", "adult_dose": "1-4 mg once daily", "notes": "Risk of low blood sugar.", "brands": ["Amaryl"]},
    "insulin": {"class": "insulin", "uses": "Diabetes", "adult_dose": "As prescribed", "notes": "Risk of low blood sugar.", "brands": []},
    "amlodipine": {"class": "calcium channel blocker", "uses": "High blood pressure, angina", "adult_dose": "5-10 mg once daily", "notes": "May cause ankle swelling.", "brands": ["Amlokind", "Norvasc"]},
    "atenolol": {"class": "beta blocker", "uses": "High BP, angina", "adult_dose": "25-100 mg once daily", "notes": "Don't stop suddenly; may mask low sugar.", "brands": ["Aten"]},
    "losartan": {"class": "arb", "uses": "High blood pressure", "adult_dose": "50-100 mg once daily", "notes": "Avoid in pregnancy.", "brands": ["Losar", "Cozaar"]},
    "enalapril": {"class": "ace inhibitor", "uses": "High blood pressure, heart failure", "adult_dose": "5-20 mg daily", "notes": "May cause dry cough.", "brands": ["Envas"]},
    "atorvastatin": {"class": "statin", "uses": "High cholesterol", "adult_dose": "10-40 mg at night", "notes": "Report muscle pain.", "brands": ["Atorva", "Lipitor"]},
    "warfarin": {"class": "anticoagulant", "uses": "Blood clot prevention", "adult_dose": "Dose by INR", "notes": "Regular INR tests; many interactions.", "brands": ["Warf"]},
    "clopidogrel": {"class": "antiplatelet", "uses": "Heart attack/stroke prevention", "adult_dose": "75 mg once daily", "notes": "Bleeding risk.", "brands": ["Plavix", "Clopilet"]},
    "omeprazole": {"class": "ppi", "uses": "Acidity, ulcers, GERD", "adult_dose": "20-40 mg before breakfast", "notes": "Long-term use can lower B12/magnesium.", "brands": ["Omez", "Prilosec"]},
    "pantoprazole": {"class": "ppi", "uses": "Acidity, GERD", "adult_dose": "40 mg before breakfast", "notes": "Take on empty stomach.", "brands": ["Pan 40", "Pantocid"]},
    "cetirizine": {"class": "antihistamine", "uses": "Allergy, runny nose, itching", "adult_dose": "10 mg once daily", "notes": "May cause drowsiness.", "brands": ["Cetzine", "Zyrtec"]},
    "salbutamol": {"class": "bronchodilator", "uses": "Asthma, wheezing", "adult_dose": "1-2 puffs as needed", "notes": "May cause tremor, fast heartbeat.", "brands": ["Asthalin", "Ventolin"]},
    "levothyroxine": {"class": "thyroid hormone", "uses": "Hypothyroidism", "adult_dose": "As per TSH, empty stomach", "notes": "Take 30-60 min before breakfast; separate from calcium/iron.", "brands": ["Thyronorm", "Eltroxin"]},
    "sertraline": {"class": "ssri", "uses": "Depression, anxiety", "adult_dose": "50-200 mg daily", "notes": "Do not stop suddenly.", "brands": ["Zoloft"]},
    "tramadol": {"class": "opioid", "uses": "Moderate-severe pain", "adult_dose": "50-100 mg every 6 h", "notes": "Habit-forming; avoid with SSRIs.", "brands": ["Ultracet"]},
    "calcium": {"class": "supplement", "uses": "Bone health", "adult_dose": "500-1000 mg/day", "notes": "Separate from levothyroxine, ciprofloxacin.", "brands": ["Shelcal"]},
    "iron": {"class": "supplement", "uses": "Iron deficiency anemia", "adult_dose": "As prescribed", "notes": "Take with vitamin C; may darken stools.", "brands": ["Ferrous sulfate"]},
    "vitamin d3": {"class": "supplement", "uses": "Vitamin D deficiency", "adult_dose": "As prescribed (e.g. 60,000 IU weekly)", "notes": "Avoid unsupervised high doses.", "brands": ["Uprise-D3"]},
}

ALIASES = {b.lower(): n for n, d in DRUGS.items() for b in d["brands"]}
ALIASES.update({"acetaminophen": "paracetamol", "vitamin d": "vitamin d3", "ecosprin": "aspirin"})

# frozenset({a, b}) -> (severity, message); a/b may be drug names or classes
INTERACTIONS: list[tuple[str, str, str, str]] = [
    ("warfarin", "aspirin", "severe", "Greatly increased bleeding risk."),
    ("warfarin", "nsaid", "severe", "NSAIDs raise bleeding risk with warfarin."),
    ("warfarin", "clopidogrel", "severe", "Major bleeding risk."),
    ("aspirin", "clopidogrel", "moderate", "Increased bleeding risk; only combine if prescribed."),
    ("nsaid", "nsaid", "moderate", "Two NSAIDs together raise stomach bleeding and kidney risk."),
    ("nsaid", "ace inhibitor", "moderate", "NSAIDs can reduce BP-drug effect and harm kidneys."),
    ("nsaid", "arb", "moderate", "NSAIDs can reduce BP-drug effect and harm kidneys."),
    ("ssri", "tramadol", "severe", "Risk of serotonin syndrome and seizures."),
    ("ssri", "nsaid", "moderate", "Increased bleeding risk."),
    ("beta blocker", "insulin", "moderate", "May hide symptoms of low blood sugar."),
    ("beta blocker", "sulfonylurea", "moderate", "May hide symptoms of low blood sugar."),
    ("levothyroxine", "calcium", "moderate", "Calcium reduces absorption - take 4 hours apart."),
    ("levothyroxine", "iron", "moderate", "Iron reduces absorption - take 4 hours apart."),
    ("ciprofloxacin", "calcium", "moderate", "Calcium reduces antibiotic absorption - separate by 2 hours."),
    ("ciprofloxacin", "iron", "moderate", "Iron reduces antibiotic absorption - separate by 2 hours."),
    ("statin", "azithromycin", "mild", "Rarely raises risk of muscle problems; report muscle pain."),
    ("ace inhibitor", "arb", "moderate", "Combining raises kidney and potassium risk."),
    ("paracetamol", "warfarin", "mild", "High regular paracetamol doses can raise INR."),
]

ALLERGY_CLASSES = {
    "penicillin": {"penicillin"},
    "sulfa": {"sulfonylurea"},
    "nsaid": {"nsaid"},
    "aspirin": {"aspirin"},
    "ibuprofen": {"ibuprofen"},
}


def canon(name: str) -> str | None:
    n = " ".join(name.lower().split())
    if n in DRUGS:
        return n
    if n in ALIASES:
        return ALIASES[n]
    for d in DRUGS:
        if n.startswith(d) or d in n:
            return d
    return None


def search(q: str, limit: int = 10) -> list[dict]:
    q = q.lower().strip()
    out = []
    for n, d in DRUGS.items():
        if q in n or any(q in b.lower() for b in d["brands"]) or q in d["uses"].lower() or q in d["class"]:
            out.append({"name": n, **d})
    return out[:limit]


def _tags(name: str) -> set[str]:
    c = canon(name)
    return {c, DRUGS[c]["class"]} if c else set()


def check_interactions(names: list[str]) -> list[dict]:
    found, seen = [], set()
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ta, tb = _tags(a), _tags(b)
            if not ta or not tb:
                continue
            for x, y, sev, msg in INTERACTIONS:
                if (x in ta and y in tb) or (y in ta and x in tb):
                    if canon(a) == canon(b):
                        continue
                    key = (frozenset((canon(a), canon(b))), msg)
                    if key not in seen:
                        seen.add(key)
                        found.append({"drugs": [canon(a), canon(b)], "severity": sev, "message": msg})
    order = {"severe": 0, "moderate": 1, "mild": 2}
    return sorted(found, key=lambda f: order[f["severity"]])


def check_allergies(drug: str, allergies: list[str]) -> list[dict]:
    tags = _tags(drug)
    out = []
    for al in allergies:
        a = al.lower().strip()
        classes = ALLERGY_CLASSES.get(a, {a})
        if tags & classes or (canon(drug) and a in canon(drug)) or a in drug.lower():
            out.append({"drug": drug, "allergy": al, "message": f"Patient is recorded as allergic to '{al}'. Do not take {drug} without asking a doctor."})
    return out
