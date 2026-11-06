"""Plain-language explainer for ECG, X-ray, MRI and CT *report text* (the radiologist's/cardiologist's wording).

It does not read images and does not diagnose: it matches well-known report phrases, explains them simply, and flags
phrases that normally need prompt medical attention. Negated phrases ("no pneumothorax") are ignored.
"""
from __future__ import annotations

import re

# term -> (modalities, plain explanation, severity: info | attention | urgent)
TERMS: dict[str, tuple[tuple[str, ...], str, str]] = {
    # ECG
    "sinus rhythm": (("ecg",), "The heart's natural pacemaker is driving a normal rhythm.", "info"),
    "sinus tachycardia": (("ecg",), "Heart rate above 100/min with a normal rhythm; often due to fever, pain, anxiety, anemia or exertion.", "attention"),
    "sinus bradycardia": (("ecg",), "Heart rate below 60/min; normal in athletes or sleep, but can cause dizziness in others.", "attention"),
    "atrial fibrillation": (("ecg",), "An irregular, often fast rhythm from the upper chambers; raises stroke risk and needs treatment.", "urgent"),
    "st elevation": (("ecg",), "ST-segment elevation can be a sign of an acute heart attack. This needs emergency evaluation.", "urgent"),
    "st depression": (("ecg",), "May suggest reduced blood supply to the heart muscle; needs a doctor's review.", "attention"),
    "t wave inversion": (("ecg",), "Inverted T waves can be harmless or suggest strain/ischemia; correlate with symptoms.", "attention"),
    "left bundle branch block": (("ecg",), "A delay in the heart's electrical conduction on the left side; needs cardiology review.", "attention"),
    "right bundle branch block": (("ecg",), "A delay in electrical conduction on the right side; often benign but should be reviewed.", "attention"),
    "prolonged qt": (("ecg",), "A long QT interval can predispose to dangerous rhythms; some medicines worsen it.", "attention"),
    "left ventricular hypertrophy": (("ecg", "xray", "ct"), "Thickened left heart muscle, commonly from long-standing high blood pressure.", "attention"),
    "ventricular tachycardia": (("ecg",), "A fast, dangerous rhythm from the lower chambers. Emergency.", "urgent"),
    "premature ventricular": (("ecg",), "Extra early beats from the lower chambers; usually harmless if infrequent.", "info"),
    "normal ecg": (("ecg",), "No significant abnormality was seen on the tracing.", "info"),
    # X-ray / chest
    "consolidation": (("xray", "ct"), "A dense area where air spaces are filled with fluid or pus, typical of pneumonia.", "attention"),
    "pleural effusion": (("xray", "ct"), "Fluid collected around the lung; has many causes (infection, heart failure, others).", "attention"),
    "pneumothorax": (("xray", "ct"), "Air outside the lung causing it to collapse partly or fully. Can be an emergency.", "urgent"),
    "cardiomegaly": (("xray", "ct"), "An enlarged heart shadow; may reflect heart failure, hypertension or heart disease.", "attention"),
    "pulmonary nodule": (("xray", "ct"), "A small round spot in the lung. Most are benign but need follow-up imaging.", "attention"),
    "mass": (("xray", "ct", "mri"), "A larger abnormal growth or lump; needs further tests to find out what it is.", "urgent"),
    "infiltrate": (("xray",), "A hazy area in the lung, often infection or inflammation.", "attention"),
    "fracture": (("xray", "ct"), "A break in a bone; needs orthopedic assessment and usually immobilisation.", "attention"),
    "dislocation": (("xray",), "A joint out of its normal position; needs prompt orthopedic care.", "attention"),
    "cavitation": (("xray", "ct"), "A hollow space in the lung, which can be seen in TB, abscess or tumours.", "urgent"),
    "tuberculosis": (("xray", "ct"), "Findings may be related to TB infection; confirm with sputum/cartridge tests.", "urgent"),
    "pneumonia": (("xray", "ct"), "Infection of the lung tissue; usually treated with antibiotics and rest.", "attention"),
    "atelectasis": (("xray", "ct"), "Part of the lung has collapsed or is not fully expanded.", "info"),
    "osteoarthritis": (("xray", "mri"), "Wear-and-tear changes in a joint.", "info"),
    "degenerative changes": (("xray", "mri", "ct"), "Age-related wear of bones, discs or joints; common and often managed without surgery.", "info"),
    "clear lung fields": (("xray",), "No abnormal shadows in the lungs.", "info"),
    # MRI / CT
    "hemorrhage": (("ct", "mri"), "Bleeding; in the brain this is an emergency.", "urgent"),
    "haemorrhage": (("ct", "mri"), "Bleeding; in the brain this is an emergency.", "urgent"),
    "infarct": (("ct", "mri"), "An area of tissue damaged by lack of blood supply (for example a stroke).", "urgent"),
    "midline shift": (("ct", "mri"), "The brain's centre line is pushed to one side by swelling, blood or a mass. Emergency.", "urgent"),
    "hydrocephalus": (("ct", "mri"), "Enlarged fluid spaces in the brain; needs neurosurgical review.", "urgent"),
    "lesion": (("ct", "mri"), "An area that looks different from normal tissue; the cause needs correlation with symptoms and tests.", "attention"),
    "enhancing": (("ct", "mri"), "The area takes up contrast dye, which can mean inflammation or a tumour; needs specialist review.", "attention"),
    "disc bulge": (("mri",), "A spinal disc pushing outward; may or may not press on nerves.", "attention"),
    "disc herniation": (("mri",), "A spinal disc has pushed out and may press on a nerve, causing pain or numbness.", "attention"),
    "spinal canal stenosis": (("mri", "ct"), "Narrowing of the space for the spinal cord/nerves.", "attention"),
    "meniscal tear": (("mri",), "A tear in the knee cartilage cushion.", "attention"),
    "ligament tear": (("mri",), "A torn ligament; severity decides between rest, physio or surgery.", "attention"),
    "white matter": (("mri",), "Small white-matter spots are common with age, migraine or blood-pressure changes; interpret with your doctor.", "info"),
    "sinusitis": (("ct", "mri", "xray"), "Inflamed sinus lining, usually from infection or allergy.", "info"),
    "calculus": (("ct",), "A stone (kidney, gallbladder, etc.).", "attention"),
    "nodule": (("ct", "xray", "mri"), "A small rounded lump of tissue; usually followed with repeat imaging.", "attention"),
    "metastasis": (("ct", "mri", "xray"), "Spread of cancer from another site. Needs urgent oncology review.", "urgent"),
    "metastases": (("ct", "mri", "xray"), "Spread of cancer from another site. Needs urgent oncology review.", "urgent"),
    "unremarkable": (("ecg", "xray", "ct", "mri"), "Nothing abnormal was noted.", "info"),
    "within normal limits": (("ecg", "xray", "ct", "mri"), "The finding is in the normal range.", "info"),
}
NEG = re.compile(r"\b(no|not|without|negative for|absence of|free of|rule[sd]? out|ruled out|no evidence of|no sign of)\b[^.;\n]{0,40}$", re.I)
MODALITY_HINTS = {"ecg": ("ecg", "ekg", "qrs", "pr interval", "sinus", "rhythm"), "mri": ("mri", "magnetic resonance", "t1", "t2", "flair"),
                  "ct": ("ct ", "computed tomography", "hounsfield", "contrast-enhanced"), "xray": ("x-ray", "xray", "radiograph", "chest pa", "cxr")}


def detect_modality(text: str) -> str:
    t = text.lower()
    best = max(MODALITY_HINTS, key=lambda m: sum(h in t for h in MODALITY_HINTS[m]))
    return best if any(h in t for h in MODALITY_HINTS[best]) else "xray"


def explain(text: str, modality: str | None = None) -> dict:
    text = text.strip()
    if len(text) < 10:
        raise ValueError("Paste the report text (at least a sentence).")
    mod = (modality or "").lower().replace("-", "").replace("x-ray", "xray")
    mod = mod if mod in ("ecg", "xray", "ct", "mri") else detect_modality(text)
    low = text.lower()
    found = []
    for term, (mods, expl, sev) in TERMS.items():
        if mod not in mods:
            continue
        for m in re.finditer(re.escape(term), low):
            if NEG.search(low[max(0, m.start() - 45):m.start()]):
                continue
            found.append({"term": term, "meaning": expl, "severity": sev})
            break
    found.sort(key=lambda f: {"urgent": 0, "attention": 1, "info": 2}[f["severity"]])
    urgent = [f for f in found if f["severity"] == "urgent"]
    if urgent:
        summary = "Some phrases in this report usually need prompt medical review. Please show it to your doctor today; go to an emergency department if you have severe symptoms."
    elif any(f["severity"] == "attention" for f in found):
        summary = "The report contains findings that should be discussed with your doctor, though many such findings are manageable."
    elif found:
        summary = "The recognised phrases look reassuring, but only your doctor can interpret the whole report."
    else:
        summary = "No familiar phrases were recognised. Please ask your doctor to explain the report."
    return {"modality": mod, "findings": found, "urgent_count": len(urgent), "summary": summary,
            "disclaimer": "Educational explanation of report wording only. It is not a diagnosis; your doctor must interpret the report in context."}
