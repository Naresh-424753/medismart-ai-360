"""Safety-first healthcare chatbot engine (English + Hindi).

Order of handling:
1. Emergency / self-harm red flags are ALWAYS answered by rules (never delegated to an LLM).
2. Intent rules (symptoms, glossary, navigation help).
3. Optional LLM fallback is wired in routers/chatbot.py when an API key is configured.
"""
from __future__ import annotations

import re

EMERGENCY_NUMBERS = "112 (national emergency) or 108 (ambulance)"

TXT = {
    "emergency": {
        "en": f"This could be a medical emergency. Call {EMERGENCY_NUMBERS} now or go to the nearest hospital. "
              "Use the SOS button in this app to alert your emergency contacts with your live location.",
        "hi": "यह आपातकालीन स्थिति हो सकती है। तुरंत 112 या 108 (एम्बुलेंस) पर कॉल करें या नज़दीकी अस्पताल जाएँ। "
              "अपने आपातकालीन संपर्कों को लोकेशन भेजने के लिए ऐप का SOS बटन दबाएँ।",
    },
    "self_harm": {
        "en": "I'm really sorry you're feeling this way. You are not alone. Please talk to someone you trust right now, "
              "and call Tele-MANAS at 14416 (free, 24x7, many languages) or 112 if you may act on these thoughts. "
              "If you're in immediate danger, please call 112.",
        "hi": "मुझे बहुत दुख है कि आप ऐसा महसूस कर रहे हैं। आप अकेले नहीं हैं। कृपया अभी किसी भरोसेमंद व्यक्ति से बात करें "
              "और Tele-MANAS हेल्पलाइन 14416 (मुफ़्त, 24x7) पर कॉल करें। तुरंत ख़तरा हो तो 112 पर कॉल करें।",
    },
    "disclaimer": {
        "en": "This is general information, not a diagnosis. Please consult a doctor for personal advice.",
        "hi": "यह सामान्य जानकारी है, निदान नहीं। व्यक्तिगत सलाह के लिए कृपया डॉक्टर से मिलें।",
    },
    "greeting": {
        "en": "Hello! I'm the MediSmart assistant. Tell me your symptoms, ask about a medical term, or ask for help "
              "with appointments, medicines or reports.",
        "hi": "नमस्ते! मैं MediSmart सहायक हूँ। अपने लक्षण बताएँ, किसी मेडिकल शब्द का मतलब पूछें, या अपॉइंटमेंट, "
              "दवा और रिपोर्ट में मदद माँगें।",
    },
    "fallback": {
        "en": "I couldn't match that to a health topic. Try describing a symptom (for example 'fever and cough for 2 days'), "
              "or ask 'what is HbA1c?'.",
        "hi": "मैं इसे किसी स्वास्थ्य विषय से नहीं जोड़ पाया। कोई लक्षण बताएँ (जैसे 'दो दिन से बुखार और खांसी') "
              "या पूछें 'HbA1c क्या है?'।",
    },
    "see_doctor": {"en": "See a doctor if:", "hi": "डॉक्टर से मिलें अगर:"},
    "self_care": {"en": "What may help:", "hi": "क्या मदद कर सकता है:"},
    "possible": {"en": "Common causes include:", "hi": "आम कारणों में शामिल हैं:"},
}

RED_FLAGS = [
    r"chest (pain|tightness|pressure)", r"heart attack", r"सीने (में|मे) (दर्द|जकड़न)", r"seene m(e|ei)n dard",
    r"can'?t breathe", r"cannot breathe", r"difficulty (in )?breathing", r"short(ness)? of breath",
    r"सांस (नहीं|लेने में)", r"साँस (नहीं|लेने में)", r"saans nahi",
    r"face droop", r"slurred speech", r"one side (of (my|the) body )?(is )?(weak|numb)", r"sudden (weakness|numbness)",
    r"\bstroke\b", r"लकवा", r"चेहरा टेढ़ा",
    r"severe bleeding", r"bleeding (a lot|heavily|won'?t stop)", r"बहुत खून", r"खून बहना बंद नहीं",
    r"unconscious", r"passed out", r"not responding", r"seizure", r"बेहोश", r"दौरा पड़",
    r"overdose", r"poison", r"swallowed (a lot|pills|bleach)", r"ज़हर", r"जहर",
]
SELF_HARM = [r"suicid", r"kill myself", r"end my life", r"want to die", r"self[- ]?harm", r"आत्महत्या",
             r"मरना चाहता", r"मरना चाहती", r"जीना नहीं चाहता", r"जीना नहीं चाहती"]

# keywords (en + hi) -> knowledge
SYMPTOMS = {
    "fever": dict(kw=["fever", "temperature", "बुखार", "bukhar"],
                  causes={"en": "viral infections, flu, dengue/malaria (in season), throat or urine infections",
                          "hi": "वायरल संक्रमण, फ्लू, डेंगू/मलेरिया (मौसम में), गले या मूत्र संक्रमण"},
                  care={"en": "rest, plenty of fluids, light meals; paracetamol as per label if needed",
                        "hi": "आराम, खूब पानी/तरल, हल्का भोजन; ज़रूरत हो तो लेबल के अनुसार पैरासिटामोल"},
                  doctor={"en": "fever above 39.5°C or lasting over 3 days, rash, severe headache, stiff neck, confusion, or in infants/elderly",
                          "hi": "बुखार 39.5°C से ऊपर या 3 दिन से ज़्यादा, चकत्ते, तेज़ सिरदर्द, गर्दन अकड़ना, भ्रम, या शिशु/बुज़ुर्ग में"}),
    "cough": dict(kw=["cough", "खांसी", "khansi", "खाँसी"],
                  causes={"en": "common cold, allergies, bronchitis, asthma, acid reflux",
                          "hi": "सर्दी-ज़ुकाम, एलर्जी, ब्रोंकाइटिस, अस्थमा, एसिड रिफ्लक्स"},
                  care={"en": "warm fluids, honey (not for under 1 year), steam, avoid smoke and dust",
                        "hi": "गुनगुना पानी, शहद (1 साल से बड़ों के लिए), भाप, धुएँ और धूल से बचाव"},
                  doctor={"en": "cough over 2-3 weeks, blood in sputum, breathlessness, wheezing, weight loss or night sweats (TB screening)",
                          "hi": "खांसी 2-3 हफ़्ते से ज़्यादा, बलगम में खून, सांस फूलना, घरघराहट, वज़न घटना या रात में पसीना (टीबी जाँच)"}),
    "headache": dict(kw=["headache", "सिरदर्द", "सिर दर्द", "sir dard", "migraine"],
                     causes={"en": "tension, dehydration, lack of sleep, migraine, eye strain, sinus problems",
                             "hi": "तनाव, पानी की कमी, नींद की कमी, माइग्रेन, आँखों पर ज़ोर, साइनस"},
                     care={"en": "rest in a quiet room, hydrate, regular sleep, limit screen time",
                           "hi": "शांत कमरे में आराम, पानी पिएँ, नियमित नींद, स्क्रीन कम करें"},
                     doctor={"en": "sudden worst-ever headache, after head injury, with fever and stiff neck, weakness, vision change or vomiting",
                             "hi": "अचानक बहुत तेज़ सिरदर्द, चोट के बाद, बुखार और गर्दन अकड़ने के साथ, कमज़ोरी, धुंधलापन या उल्टी"}),
    "stomach": dict(kw=["stomach", "abdominal", "diarrhea", "diarrhoea", "vomit", "loose motion", "पेट", "दस्त", "उल्टी"],
                    causes={"en": "food infection, gastritis, indigestion, constipation, stomach flu",
                            "hi": "भोजन से संक्रमण, गैस्ट्राइटिस, अपच, कब्ज़, पेट का फ्लू"},
                    care={"en": "ORS and fluids in small sips, light bland food, avoid oily/spicy food",
                          "hi": "ORS और तरल थोड़ा-थोड़ा, हल्का भोजन, तला-मसालेदार न खाएँ"},
                    doctor={"en": "blood in stool or vomit, severe or one-sided pain, signs of dehydration, symptoms beyond 2 days, or in young children",
                            "hi": "मल या उल्टी में खून, तेज़ या एक तरफ़ दर्द, पानी की कमी के लक्षण, 2 दिन से ज़्यादा, या छोटे बच्चों में"}),
    "throat": dict(kw=["sore throat", "throat pain", "गले में दर्द", "gala dard", "गला"],
                   causes={"en": "viral infection, strep throat, allergies, acid reflux",
                           "hi": "वायरल संक्रमण, स्ट्रेप गला, एलर्जी, एसिड रिफ्लक्स"},
                   care={"en": "warm salt-water gargles, warm fluids, rest", "hi": "गुनगुने नमक के पानी से गरारे, गर्म तरल, आराम"},
                   doctor={"en": "difficulty swallowing or breathing, fever above 3 days, white patches, swollen neck glands",
                           "hi": "निगलने या सांस में तकलीफ़, 3 दिन से ज़्यादा बुखार, सफ़ेद धब्बे, गले की गाँठें"}),
    "fatigue": dict(kw=["tired", "fatigue", "weakness", "थकान", "कमज़ोरी", "कमजोरी", "thakan"],
                    causes={"en": "poor sleep, anemia, thyroid problems, vitamin deficiency, diabetes, stress",
                            "hi": "नींद की कमी, खून की कमी, थायराइड, विटामिन की कमी, डायबिटीज़, तनाव"},
                    care={"en": "regular sleep, balanced meals with iron and protein, hydration, light exercise",
                          "hi": "नियमित नींद, आयरन और प्रोटीन वाला संतुलित भोजन, पानी, हल्का व्यायाम"},
                    doctor={"en": "tiredness lasting weeks, with weight change, breathlessness, pale skin or low mood - consider CBC, thyroid, sugar, B12 and vitamin D tests",
                            "hi": "हफ़्तों की थकान, वज़न में बदलाव, सांस फूलना, पीलापन या उदासी - CBC, थायराइड, शुगर, B12 व विटामिन D जाँच पर विचार करें"}),
    "dizziness": dict(kw=["dizzy", "dizziness", "giddy", "चक्कर", "chakkar"],
                      causes={"en": "dehydration, low blood pressure or sugar, anemia, inner-ear problems",
                              "hi": "पानी की कमी, कम बीपी या शुगर, खून की कमी, कान के अंदर की समस्या"},
                      care={"en": "sit or lie down, drink fluids, rise slowly", "hi": "बैठ या लेट जाएँ, तरल लें, धीरे-धीरे उठें"},
                      doctor={"en": "repeated episodes, fainting, chest pain, palpitations or weakness on one side",
                              "hi": "बार-बार चक्कर, बेहोशी, सीने में दर्द, धड़कन तेज़ होना या एक तरफ़ कमज़ोरी"}),
    "rash": dict(kw=["rash", "itching", "itch", "skin", "खुजली", "चकत्ते", "दाने"],
                 causes={"en": "allergy, heat rash, fungal infection, eczema, insect bites",
                         "hi": "एलर्जी, घमौरियाँ, फंगल संक्रमण, एक्ज़ीमा, कीड़े का काटना"},
                 care={"en": "keep skin clean and dry, avoid scratching and known triggers, mild moisturiser",
                       "hi": "त्वचा साफ़ और सूखी रखें, खुजलाएँ नहीं, ज्ञात कारणों से बचें, हल्का मॉइस्चराइज़र"},
                 doctor={"en": "rash with fever, swelling of lips/face, breathing trouble, rapid spreading, or blisters",
                         "hi": "बुखार के साथ चकत्ते, होंठ/चेहरे में सूजन, सांस की तकलीफ़, तेज़ी से फैलना, या फफोले"}),
    "back_pain": dict(kw=["back pain", "backache", "कमर दर्द", "कमर में दर्द", "kamar dard"],
                      causes={"en": "muscle strain, poor posture, disc problems", "hi": "मांसपेशियों में खिंचाव, गलत मुद्रा, डिस्क की समस्या"},
                      care={"en": "stay gently active, hot or cold packs, posture correction", "hi": "हल्की गतिविधि, गर्म/ठंडी सिकाई, बैठने का सही तरीका"},
                      doctor={"en": "numbness or weakness in legs, loss of bladder/bowel control, fever, or pain after injury",
                              "hi": "पैरों में सुन्नपन या कमज़ोरी, मल-मूत्र पर नियंत्रण न रहना, बुखार, या चोट के बाद दर्द"}),
}

GLOSSARY = {
    "hypertension": "Long-term high blood pressure (usually 130/80 mmHg or higher on repeated readings). It strains the heart, brain and kidneys.",
    "diabetes": "A condition where blood sugar stays too high because the body cannot make or use insulin properly.",
    "anemia": "Too few healthy red blood cells or too little hemoglobin, causing tiredness and paleness. Iron, B12 or folate deficiency are common causes.",
    "hba1c": "A blood test showing your average blood sugar over about 3 months. Below 5.7% is normal, 5.7-6.4% prediabetes, 6.5% or more diabetes range.",
    "cholesterol": "A fatty substance in the blood. High LDL ('bad') raises heart-disease risk; HDL ('good') is protective.",
    "creatinine": "A waste product filtered by the kidneys. A rising level can mean reduced kidney function.",
    "spo2": "Oxygen saturation: the percentage of your blood carrying oxygen. 95-100% is typical; below 94% needs attention.",
    "ecg": "Electrocardiogram - a quick recording of the heart's electrical activity that helps detect rhythm problems and heart attacks.",
    "tsh": "Thyroid-stimulating hormone. High TSH usually means an underactive thyroid; low TSH an overactive one.",
    "bmi": "Body-mass index: weight (kg) divided by height (m) squared, a rough screen for underweight or overweight.",
    "cbc": "Complete blood count - a blood test measuring red cells, white cells, hemoglobin and platelets.",
    "asthma": "A long-term condition where the airways narrow and swell, causing wheezing, cough and breathlessness.",
    "migraine": "A recurring, often one-sided throbbing headache that can come with nausea and sensitivity to light or sound.",
    "tuberculosis": "A bacterial infection mainly of the lungs, curable with a full course of medicines. Cough over 2 weeks should be tested.",
    "hemoglobin": "The protein in red blood cells that carries oxygen. Low levels indicate anemia.",
}
GLOSSARY_HI = {"बीपी": "hypertension", "ब्लड प्रेशर": "hypertension", "डायबिटीज": "diabetes", "शुगर": "diabetes",
               "एनीमिया": "anemia", "खून की कमी": "anemia", "कोलेस्ट्रॉल": "cholesterol", "थायराइड": "tsh"}

NAV = [
    (r"appointment|book (a )?doctor|अपॉइंटमेंट|डॉक्टर से मिल", "/appointments",
     {"en": "I can take you to Appointments to search doctors and book a slot.", "hi": "मैं आपको अपॉइंटमेंट पेज पर ले चलता हूँ जहाँ आप डॉक्टर खोजकर समय बुक कर सकते हैं।"}),
    (r"medicine|tablet|dose|reminder|दवा|दवाई", "/medicines",
     {"en": "Open Medicines to see your schedule, mark doses as taken, or check interactions.", "hi": "दवा का शेड्यूल देखने, खुराक दर्ज करने या इंटरैक्शन जाँचने के लिए Medicines खोलें।"}),
    (r"report|lab result|blood test|रिपोर्ट|जाँच", "/reports",
     {"en": "Upload your lab report in Report Analyzer and I'll highlight abnormal values.", "hi": "Report Analyzer में अपनी लैब रिपोर्ट अपलोड करें, मैं असामान्य मान दिखाऊँगा।"}),
    (r"risk|diabetes risk|heart risk|जोखिम", "/risk",
     {"en": "Use Risk Check to estimate diabetes and heart-disease risk.", "hi": "डायबिटीज़ और हृदय रोग का जोखिम जानने के लिए Risk Check इस्तेमाल करें।"}),
]


def detect_lang(text: str, hint: str | None = None) -> str:
    if hint in ("en", "hi"):
        return hint
    return "hi" if re.search(r"[ऀ-ॿ]", text) else "en"


def _any(patterns, text):
    return any(re.search(p, text) for p in patterns)


def respond(message: str, lang: str | None = None) -> dict:
    lang = detect_lang(message, lang)
    text = message.lower().strip()
    out = {"lang": lang, "urgency": "normal", "actions": [], "source": "rules", "handled": True}

    if _any(SELF_HARM, text):
        out.update(urgency="self_harm", reply=TXT["self_harm"][lang],
                   actions=[{"type": "call", "number": "14416"}, {"type": "call", "number": "112"}])
        return out
    if _any(RED_FLAGS, text):
        out.update(urgency="emergency", reply=TXT["emergency"][lang],
                   actions=[{"type": "sos"}, {"type": "call", "number": "112"}, {"type": "call", "number": "108"}])
        return out

    if re.fullmatch(r"(hi|hello|hey|namaste|नमस्ते|हैलो|हेलो)[!. ]*", text):
        out["reply"] = TXT["greeting"][lang]
        return out

    # glossary: "what is X", "X kya hai", "X क्या है"
    for term, canon in [*GLOSSARY_HI.items(), *((t, t) for t in GLOSSARY)]:
        if term in text and re.search(r"what is|what are|meaning|explain|kya|क्या|मतलब|define", text):
            body = GLOSSARY[canon]
            out["reply"] = (f"{term.upper() if term.isascii() else term}: {body}\n\n{TXT['disclaimer'][lang]}")
            return out

    matches = [s for s in SYMPTOMS.values() if any(k in text for k in s["kw"])]
    if matches:
        parts = []
        for s in matches[:2]:
            parts.append(
                f"{TXT['possible'][lang]} {s['causes'][lang]}.\n"
                f"{TXT['self_care'][lang]} {s['care'][lang]}.\n"
                f"{TXT['see_doctor'][lang]} {s['doctor'][lang]}.")
        out["reply"] = "\n\n".join(parts) + f"\n\n{TXT['disclaimer'][lang]}"
        out["actions"] = [{"type": "navigate", "to": "/appointments"}]
        return out

    for pattern, route, msg in NAV:
        if re.search(pattern, text):
            out["reply"] = msg[lang]
            out["actions"] = [{"type": "navigate", "to": route}]
            return out

    out.update(reply=TXT["fallback"][lang], handled=False)
    return out
