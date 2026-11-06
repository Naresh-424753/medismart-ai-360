"""Lab report parser + interpreter. Works on text (pasted, PDF-extracted or OCR'd)."""
from __future__ import annotations

import re

# key: (display, unit, low, high, aliases, note_low, note_high)  (adult reference ranges, general)
REFS: dict[str, dict] = {
    "hemoglobin": dict(name="Hemoglobin", unit="g/dL", low=12.0, high=17.5, alias=["hemoglobin", "haemoglobin", "hb", "hgb"], lo="May indicate anemia.", hi="May indicate dehydration or polycythemia."),
    "wbc": dict(name="WBC count", unit="/cumm", low=4000, high=11000, alias=["wbc", "total leucocyte count", "tlc", "white blood cell"], lo="Low WBC may indicate infection, marrow or drug effect.", hi="High WBC often indicates infection or inflammation."),
    "rbc": dict(name="RBC count", unit="million/cumm", low=4.0, high=6.0, alias=["rbc", "red blood cell"], lo="Low RBC is seen in anemia.", hi="High RBC can reflect dehydration."),
    "platelets": dict(name="Platelets", unit="/cumm", low=150000, high=450000, alias=["platelet count", "platelets", "plt"], lo="Low platelets - bleeding risk (e.g. dengue). See a doctor.", hi="High platelets may be reactive."),
    "hematocrit": dict(name="Hematocrit (PCV)", unit="%", low=36, high=52, alias=["hematocrit", "haematocrit", "pcv", "hct"], lo="Low - possible anemia.", hi="High - possible dehydration."),
    "glucose_fasting": dict(name="Fasting glucose", unit="mg/dL", low=70, high=99, alias=["fasting blood sugar", "fasting glucose", "fbs", "glucose fasting", "blood sugar fasting"], lo="Low glucose - risk of hypoglycemia.", hi="100-125 suggests prediabetes; 126+ suggests diabetes (confirm with doctor)."),
    "glucose_pp": dict(name="Post-meal glucose", unit="mg/dL", low=70, high=139, alias=["postprandial", "pp blood sugar", "ppbs", "post prandial", "blood sugar pp"], lo="Low glucose.", hi="140-199 suggests prediabetes; 200+ suggests diabetes."),
    "hba1c": dict(name="HbA1c", unit="%", low=4.0, high=5.6, alias=["hba1c", "glycosylated hemoglobin", "glycated hemoglobin"], lo="", hi="5.7-6.4 prediabetes; 6.5+ diabetes range."),
    "total_cholesterol": dict(name="Total cholesterol", unit="mg/dL", low=0, high=199, alias=["total cholesterol", "cholesterol total", "cholesterol"], lo="", hi="Raised cholesterol increases heart risk."),
    "ldl": dict(name="LDL cholesterol", unit="mg/dL", low=0, high=99, alias=["ldl cholesterol", "ldl"], lo="", hi="High LDL ('bad' cholesterol) raises heart risk."),
    "hdl": dict(name="HDL cholesterol", unit="mg/dL", low=40, high=200, alias=["hdl cholesterol", "hdl"], lo="Low HDL ('good' cholesterol) raises heart risk.", hi=""),
    "triglycerides": dict(name="Triglycerides", unit="mg/dL", low=0, high=149, alias=["triglycerides", "triglyceride", "tg"], lo="", hi="High triglycerides - reduce sugar, refined carbs and alcohol."),
    "creatinine": dict(name="Serum creatinine", unit="mg/dL", low=0.6, high=1.3, alias=["serum creatinine", "creatinine"], lo="", hi="High creatinine may indicate reduced kidney function."),
    "urea": dict(name="Blood urea", unit="mg/dL", low=15, high=40, alias=["blood urea", "urea"], lo="", hi="High urea may indicate dehydration or kidney issues."),
    "uric_acid": dict(name="Uric acid", unit="mg/dL", low=3.5, high=7.2, alias=["uric acid"], lo="", hi="High uric acid can cause gout."),
    "bun": dict(name="BUN", unit="mg/dL", low=7, high=20, alias=["bun", "blood urea nitrogen"], lo="", hi="High BUN may indicate kidney issues or dehydration."),
    "alt": dict(name="ALT (SGPT)", unit="U/L", low=7, high=56, alias=["alt", "sgpt", "alanine aminotransferase"], lo="", hi="High ALT suggests liver irritation or injury."),
    "ast": dict(name="AST (SGOT)", unit="U/L", low=10, high=40, alias=["ast", "sgot", "aspartate aminotransferase"], lo="", hi="High AST suggests liver or muscle injury."),
    "alp": dict(name="Alkaline phosphatase", unit="U/L", low=44, high=147, alias=["alkaline phosphatase", "alp"], lo="", hi="High ALP can be liver or bone related."),
    "bilirubin": dict(name="Total bilirubin", unit="mg/dL", low=0.1, high=1.2, alias=["total bilirubin", "bilirubin total", "bilirubin"], lo="", hi="High bilirubin causes jaundice - see a doctor."),
    "albumin": dict(name="Albumin", unit="g/dL", low=3.5, high=5.0, alias=["albumin"], lo="Low albumin - liver, kidney or nutrition issue.", hi=""),
    "tsh": dict(name="TSH", unit="mIU/L", low=0.4, high=4.0, alias=["tsh", "thyroid stimulating hormone"], lo="Low TSH may indicate hyperthyroidism.", hi="High TSH may indicate hypothyroidism."),
    "t3": dict(name="Total T3", unit="ng/dL", low=80, high=200, alias=["total t3", "t3"], lo="Low T3 - possible hypothyroidism.", hi="High T3 - possible hyperthyroidism."),
    "t4": dict(name="Total T4", unit="ug/dL", low=5.0, high=12.0, alias=["total t4", "t4"], lo="Low T4 - possible hypothyroidism.", hi="High T4 - possible hyperthyroidism."),
    "vitamin_d": dict(name="Vitamin D (25-OH)", unit="ng/mL", low=30, high=100, alias=["vitamin d", "25-oh vitamin d", "25 hydroxy vitamin d", "vit d"], lo="Vitamin D deficiency/insufficiency - sunlight, diet or supplements per doctor.", hi="Very high - avoid unsupervised supplements."),
    "vitamin_b12": dict(name="Vitamin B12", unit="pg/mL", low=200, high=900, alias=["vitamin b12", "vit b12", "b12", "cyanocobalamin"], lo="B12 deficiency - fatigue, tingling; see a doctor.", hi=""),
    "sodium": dict(name="Sodium", unit="mmol/L", low=135, high=145, alias=["sodium", "na+"], lo="Low sodium - see a doctor.", hi="High sodium - dehydration."),
    "potassium": dict(name="Potassium", unit="mmol/L", low=3.5, high=5.1, alias=["potassium", "k+"], lo="Low potassium can affect heart rhythm.", hi="High potassium can affect heart rhythm - urgent review."),
    "calcium": dict(name="Calcium", unit="mg/dL", low=8.5, high=10.5, alias=["calcium"], lo="Low calcium.", hi="High calcium."),
    "esr": dict(name="ESR", unit="mm/hr", low=0, high=20, alias=["esr", "erythrocyte sedimentation rate"], lo="", hi="Raised ESR indicates inflammation."),
    "crp": dict(name="CRP", unit="mg/L", low=0, high=5, alias=["crp", "c-reactive protein", "c reactive protein"], lo="", hi="Raised CRP indicates inflammation/infection."),
    "urine_ph": dict(name="Urine pH", unit="", low=4.6, high=8.0, alias=["urine ph", "ph"], lo="", hi=""),
    "urine_protein": dict(name="Urine protein", unit="mg/dL", low=0, high=14, alias=["urine protein", "protein urine"], lo="", hi="Protein in urine can indicate kidney problems."),
    "urine_specific_gravity": dict(name="Urine specific gravity", unit="", low=1.005, high=1.030, alias=["specific gravity"], lo="", hi=""),
    "pus_cells": dict(name="Urine pus cells", unit="/hpf", low=0, high=5, alias=["pus cells", "urine pus cells", "leucocytes"], lo="", hi="Raised pus cells may indicate urinary infection."),
}

CATEGORIES = {
    "cbc": ["hemoglobin", "wbc", "rbc", "platelets", "hematocrit"],
    "lft": ["alt", "ast", "alp", "bilirubin", "albumin"],
    "kft": ["creatinine", "urea", "uric_acid", "bun", "sodium", "potassium", "calcium"],
    "lipid": ["total_cholesterol", "ldl", "hdl", "triglycerides"],
    "thyroid": ["tsh", "t3", "t4"],
    "sugar": ["glucose_fasting", "glucose_pp", "hba1c"],
    "urine": ["urine_ph", "urine_protein", "urine_specific_gravity", "pus_cells"],
    "vitamins": ["vitamin_d", "vitamin_b12"],
}

NUM = r"(-?\d[\d,]*\.?\d*)"


def _alias_table():
    table = []
    for key, r in REFS.items():
        for a in r["alias"]:
            table.append((a, key))
    table.sort(key=lambda t: -len(t[0]))  # longest alias first
    return table


_ALIASES = _alias_table()


def extract_values(text: str) -> dict[str, float]:
    """Pull `test name ... number` pairs out of free text. First match per test wins."""
    found: dict[str, float] = {}
    for line in text.lower().splitlines():
        line = line.strip()
        if not line:
            continue
        for alias, key in _ALIASES:
            if key in found:
                continue
            m = re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z])[^0-9\-]{{0,40}}?{NUM}", line)
            if m:
                try:
                    found[key] = float(m.group(1).replace(",", ""))
                except ValueError:
                    continue
                break
    return found


def _status(v: float, low: float, high: float) -> str:
    if v < low:
        return "low"
    if v > high:
        return "high"
    return "normal"


def _severity(v: float, low: float, high: float) -> str:
    if v < low:
        gap = (low - v) / low if low else 0
    elif v > high:
        gap = (v - high) / high if high else 0
    else:
        return "normal"
    return "critical" if gap > 0.5 else "moderate" if gap > 0.15 else "mild"


def analyze(values: dict[str, float], sex: str | None = None) -> dict:
    findings = []
    for key, v in values.items():
        r = REFS.get(key)
        if not r:
            continue
        low, high = r["low"], r["high"]
        if key == "hemoglobin" and sex:
            low, high = (13.0, 17.5) if sex.lower().startswith("m") else (12.0, 15.5)
        st = _status(v, low, high)
        note = r["lo"] if st == "low" else r["hi"] if st == "high" else "Within reference range."
        findings.append(
            {
                "key": key, "test": r["name"], "value": v, "unit": r["unit"],
                "low": low, "high": high, "status": st,
                "severity": _severity(v, low, high), "note": note,
            }
        )
    abnormal = [f for f in findings if f["status"] != "normal"]
    critical = [f for f in abnormal if f["severity"] == "critical"]
    if not findings:
        summary = "No known tests were found in this report. Try pasting the result lines (e.g. 'Hemoglobin 11.2 g/dL')."
    elif not abnormal:
        summary = f"All {len(findings)} detected values are within the reference range."
    else:
        names = ", ".join(f"{f['test']} ({f['status']})" for f in abnormal)
        summary = f"{len(abnormal)} of {len(findings)} values are outside the reference range: {names}."
        if critical:
            summary += " Some values are far from normal - please see a doctor promptly."
    return {
        "findings": findings, "abnormal_count": len(abnormal), "total": len(findings),
        "summary": summary,
        "disclaimer": "Automated interpretation using general adult reference ranges. Labs differ - always follow your doctor's advice.",
    }


def detect_categories(values: dict[str, float]) -> list[str]:
    return [c for c, keys in CATEGORIES.items() if any(k in values for k in keys)]


def compare(current: dict[str, float], previous: dict[str, float]) -> list[dict]:
    out = []
    for k, v in current.items():
        if k in previous and k in REFS:
            prev = previous[k]
            delta = v - prev
            pct = round(delta / prev * 100, 1) if prev else None
            r = REFS[k]
            was, now = _status(prev, r["low"], r["high"]), _status(v, r["low"], r["high"])
            trend = "improved" if (was != "normal" and now == "normal") else "worsened" if (was == "normal" and now != "normal") else "increased" if delta > 0 else "decreased" if delta < 0 else "unchanged"
            out.append({"test": r["name"], "previous": prev, "current": v, "change": round(delta, 2), "percent": pct, "trend": trend})
    return out


def ocr_image_bytes(data: bytes) -> str:
    """OCR via Tesseract if installed, otherwise raise RuntimeError."""
    try:
        import io
        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.open(io.BytesIO(data)))
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"OCR unavailable ({e}). Install tesseract-ocr or paste the report text.")


def pdf_text(data: bytes) -> str:
    try:
        import io
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"PDF text extraction failed ({e}).")
