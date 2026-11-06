"""Health assistant: rule-based core + optional LLM (Anthropic Messages API) when LLM_API_KEY is set."""
from __future__ import annotations

import os
import re

from . import drugs, symptoms

GLOSSARY = {
    "hypertension": "Persistently high blood pressure (usually 140/90 mmHg or more).",
    "hypotension": "Low blood pressure.",
    "tachycardia": "A fast heart rate (over 100 beats/min at rest).",
    "bradycardia": "A slow heart rate (under 60 beats/min at rest).",
    "anemia": "Too few red blood cells or low hemoglobin, causing tiredness and paleness.",
    "hba1c": "A blood test showing average blood sugar over the last 2-3 months.",
    "ecg": "A test recording the heart's electrical activity.",
    "mri": "An imaging scan using magnets and radio waves to see soft tissues.",
    "ct scan": "An imaging test using X-rays to create cross-section pictures of the body.",
    "biopsy": "Taking a small tissue sample to check for disease.",
    "spo2": "Oxygen saturation of your blood; normal is about 95-100%.",
    "bmi": "Body-mass index: weight (kg) divided by height (m) squared.",
    "cbc": "Complete blood count: measures red cells, white cells and platelets.",
    "lft": "Liver function test: checks liver enzymes and bilirubin.",
    "kft": "Kidney function test: creatinine, urea and electrolytes.",
    "diabetes": "A condition where blood sugar is too high because of low insulin or insulin resistance.",
    "hypothyroidism": "An underactive thyroid causing tiredness, weight gain and feeling cold.",
}

FAQ = [
    (r"\b(water|hydrat)", "Most adults need about 2-3 litres of fluids a day - more in hot weather or when exercising."),
    (r"\b(sleep|insomnia)", "Adults need 7-9 hours of sleep. Keep a fixed schedule, avoid screens an hour before bed and limit caffeine after noon."),
    (r"\b(exercise|workout|walk)", "Aim for at least 150 minutes of moderate activity a week plus 2 days of strength training."),
    (r"\b(vaccine|vaccination)", "Keep your vaccination record updated in the Records tab. Ask your doctor about flu, Hep-B, tetanus and age-specific vaccines."),
    (r"\b(blood pressure|bp)\b", "Normal BP is around 120/80 mmHg. Measure seated and rested; see a doctor if repeatedly above 140/90."),
    (r"\b(diet|food|eat)", "Choose whole grains, vegetables, fruit, pulses and lean protein; limit sugar, salt and fried foods. Try the Wellness tab for a personalised plan."),
]

HI = {
    "greeting": "नमस्ते! मैं MediSmart सहायक हूँ। आप अपने लक्षण, दवाइयों या रिपोर्ट के बारे में पूछ सकते हैं।",
    "emergency": "यह आपातकाल हो सकता है। कृपया तुरंत 112 या एम्बुलेंस (102/108) को कॉल करें, या SOS बटन दबाएँ।",
    "fallback": "मैं पूरी तरह समझ नहीं पाया। कृपया अपने लक्षण बताएं, जैसे 'बुखार और खांसी', या किसी दवा का नाम पूछें।",
    "disclaimer": "यह चिकित्सीय सलाह नहीं है। कृपया डॉक्टर से मिलें।",
}
HI_SYMPTOMS = {"बुखार": "fever", "खांसी": "cough", "सिरदर्द": "headache", "सर दर्द": "headache", "उल्टी": "vomiting", "दस्त": "diarrhea", "थकान": "fatigue", "जुकाम": "runny nose", "गले में दर्द": "sore throat", "सीने में दर्द": "chest pain", "सांस": "shortness of breath", "चक्कर": "dizziness", "बदन दर्द": "body ache", "खुजली": "itching"}


def is_hindi(text: str) -> bool:
    return bool(re.search(r"[ऀ-ॿ]", text))


def reply(message: str, lang: str | None = None) -> dict:
    text = message.strip()
    low = text.lower()
    hindi = (lang == "hi") or is_hindi(text)
    if hindi:
        for h, e in HI_SYMPTOMS.items():
            if h in text:
                low += f" {e}"

    if re.fullmatch(r"(hi|hello|hey|namaste|नमस्ते|हेलो)[!. ]*", low.strip()):
        return {"reply": HI["greeting"] if hindi else "Hello! I'm the MediSmart assistant. Describe your symptoms, ask about a medicine or a medical term, or paste a lab report.", "intent": "greeting", "lang": "hi" if hindi else "en"}

    flags = [f for f in symptoms.RED_FLAGS if f in low]
    if flags:
        msg = HI["emergency"] if hindi else f"This could be an emergency ({', '.join(flags)}). Call 112 or your local ambulance now, or press the SOS button in the app."
        return {"reply": msg, "intent": "emergency", "emergency": True, "lang": "hi" if hindi else "en"}

    m = re.search(r"(?:what is|what's|meaning of|explain|define)\s+(?:a |an |the )?([a-z0-9 ]+?)\??$", low)
    term = (m.group(1).strip() if m else low.strip(" ?"))
    if term in GLOSSARY:
        return {"reply": GLOSSARY[term], "intent": "term", "lang": "en"}

    d = None
    for tok in re.findall(r"[a-z0-9]+(?: d3)?", low):
        d = drugs.canon(tok)
        if d and (tok in drugs.DRUGS or tok in drugs.ALIASES):
            break
        d = None
    if d and re.search(r"(medicine|tablet|dose|dosage|use|side|take|what is|about|info)", low):
        i = drugs.DRUGS[d]
        return {"reply": f"{d.title()} ({i['class']}): {i['uses']}. Typical adult dose: {i['adult_dose']}. {i['notes']} Always follow your doctor's prescription.", "intent": "medicine", "lang": "en"}

    result = symptoms.check([], low)
    if result["possible_conditions"]:
        top = result["possible_conditions"][:3]
        if hindi:
            lines = ", ".join(c["condition"] for c in top)
            return {"reply": f"आपके लक्षणों के आधार पर संभावित स्थितियाँ: {lines}. {HI['disclaimer']}", "intent": "symptoms", "data": result, "lang": "hi"}
        lines = "; ".join(f"{c['condition']} (match {int(c['match']*100)}%) - see {c['specialist']}" for c in top)
        return {"reply": f"Based on what you described, possible conditions are: {lines}. {result['disclaimer']}", "intent": "symptoms", "data": result, "lang": "en"}

    if re.search(r"appointment|book|doctor", low):
        return {"reply": "You can book a doctor from the Appointments tab - search by specialization and pick a free slot.", "intent": "appointment", "lang": "en"}
    if re.search(r"report|test result|lab", low):
        return {"reply": "Open Report Analyzer, paste or upload your lab report and I'll highlight abnormal values and explain them.", "intent": "report", "lang": "en"}
    for pat, ans in FAQ:
        if re.search(pat, low):
            return {"reply": ans, "intent": "faq", "lang": "en"}

    return {"reply": HI["fallback"] if hindi else "I didn't fully understand. Try describing symptoms (e.g. 'fever and cough for 2 days'), ask about a medicine ('what is paracetamol used for?') or a term ('what is HbA1c?').", "intent": "fallback", "lang": "hi" if hindi else "en"}


async def llm_reply(message: str, history: list[dict], language: str = "English") -> str | None:
    """Optional LLM. Set LLM_API_KEY (and optionally LLM_MODEL). Returns None if not configured/failing."""
    key = os.getenv("LLM_API_KEY")
    if not key:
        return None
    try:
        import httpx

        system = (f"You are MediSmart, a careful health-information assistant for patients in India. Reply in {language} (the user's chosen language), using simple words. "
                  "Give general education, never a diagnosis or prescription. Flag emergencies clearly and recommend seeing a doctor when appropriate. Keep answers under 150 words.")
        msgs = [{"role": h["role"], "content": h["content"]} for h in history[-8:]] + [{"role": "user", "content": message}]
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post("https://api.anthropic.com/v1/messages",
                             headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                             json={"model": os.getenv("LLM_MODEL", "claude-sonnet-5-5"), "max_tokens": 500, "system": system, "messages": msgs})
            r.raise_for_status()
            return "".join(b.get("text", "") for b in r.json().get("content", []))
    except Exception:
        return None
