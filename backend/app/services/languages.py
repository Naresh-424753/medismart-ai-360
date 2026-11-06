"""Languages for voice input/output (browser Web Speech API) and voice commands.

IMPORTANT: the emergency sentences and command keywords below were written for this project and should be reviewed by a
native speaker of each language before real-world use. Detailed health answers by the built-in rule engine exist only for
English and Hindi; other languages get full answers when an LLM key is configured (LLM_API_KEY), otherwise English.
"""
from __future__ import annotations

import re

LANGS: dict[str, dict] = {
    "en": {"name": "English", "native": "English", "speech": "en-IN", "emergency": "This may be an emergency. Call 112 or 108 now."},
    "hi": {"name": "Hindi", "native": "हिन्दी", "speech": "hi-IN", "emergency": "यह आपातकाल हो सकता है। अभी 112 या 108 पर कॉल करें।"},
    "bn": {"name": "Bengali", "native": "বাংলা", "speech": "bn-IN", "emergency": "এটি জরুরি অবস্থা হতে পারে। এখনই ১১২ বা ১০৮ নম্বরে কল করুন।"},
    "ta": {"name": "Tamil", "native": "தமிழ்", "speech": "ta-IN", "emergency": "இது அவசர நிலையாக இருக்கலாம். உடனே 112 அல்லது 108 ஐ அழைக்கவும்."},
    "te": {"name": "Telugu", "native": "తెలుగు", "speech": "te-IN", "emergency": "ఇది అత్యవసర పరిస్థితి కావచ్చు. వెంటనే 112 లేదా 108 కి కాల్ చేయండి."},
    "mr": {"name": "Marathi", "native": "मराठी", "speech": "mr-IN", "emergency": "ही आणीबाणीची परिस्थिती असू शकते. आत्ताच 112 किंवा 108 वर कॉल करा."},
    "gu": {"name": "Gujarati", "native": "ગુજરાતી", "speech": "gu-IN", "emergency": "આ કટોકટી હોઈ શકે છે. હમણાં જ 112 અથવા 108 પર કૉલ કરો."},
    "kn": {"name": "Kannada", "native": "ಕನ್ನಡ", "speech": "kn-IN", "emergency": "ಇದು ತುರ್ತು ಪರಿಸ್ಥಿತಿ ಆಗಿರಬಹುದು. ಈಗಲೇ 112 ಅಥವಾ 108 ಗೆ ಕರೆ ಮಾಡಿ."},
    "ml": {"name": "Malayalam", "native": "മലയാളം", "speech": "ml-IN", "emergency": "ഇത് അടിയന്തര സാഹചര്യമായിരിക്കാം. ഉടൻ 112 അല്ലെങ്കിൽ 108 ൽ വിളിക്കുക."},
    "pa": {"name": "Punjabi", "native": "ਪੰਜਾਬੀ", "speech": "pa-IN", "emergency": "ਇਹ ਐਮਰਜੈਂਸੀ ਹੋ ਸਕਦੀ ਹੈ। ਹੁਣੇ 112 ਜਾਂ 108 'ਤੇ ਕਾਲ ਕਰੋ।"},
}

# words that, when spoken, trigger the SOS countdown (in addition to English ones, which speech engines often return for loanwords)
EMERGENCY_WORDS: dict[str, list[str]] = {
    "en": ["help", "emergency", "ambulance", "save me"],
    "hi": ["मदद", "बचाओ", "आपातकाल", "इमरजेंसी", "एम्बुलेंस", "एंबुलेंस", "madad", "bachao"],
    "bn": ["সাহায্য", "বাঁচাও", "জরুরি", "অ্যাম্বুলেন্স"],
    "ta": ["உதவி", "காப்பாற்று", "அவசரம்", "ஆம்புலன்ஸ்"],
    "te": ["సహాయం", "కాపాడండి", "అత్యవసరం", "అంబులెన్స్"],
    "mr": ["मदत", "वाचवा", "आणीबाणी", "रुग्णवाहिका"],
    "gu": ["મદદ", "બચાવો", "કટોકટી", "એમ્બ્યુલન્સ"],
    "kn": ["ಸಹಾಯ", "ಕಾಪಾಡಿ", "ತುರ್ತು", "ಆಂಬ್ಯುಲೆನ್ಸ್"],
    "ml": ["സഹായം", "രക്ഷിക്കൂ", "അടിയന്തരം", "ആംബുലൻസ്"],
    "pa": ["ਮਦਦ", "ਬਚਾਓ", "ਐਮਰਜੈਂਸੀ", "ਐਂਬੂਲੈਂਸ"],
}

# page -> keywords per language (English words are matched in every language)
COMMANDS: dict[str, dict[str, list[str]]] = {
    "/": {"en": ["home", "dashboard"], "hi": ["होम", "मुख्य"], "bn": ["হোম"], "ta": ["முகப்பு"], "te": ["హోమ్"], "mr": ["होम"], "gu": ["હોમ"], "kn": ["ಮುಖಪುಟ"], "ml": ["ഹോം"], "pa": ["ਹੋਮ"]},
    "/medicines": {"en": ["medicine", "medicines", "tablet"], "hi": ["दवा", "दवाई", "गोली"], "bn": ["ওষুধ"], "ta": ["மருந்து"], "te": ["మందులు", "మందు"], "mr": ["औषध", "गोळी"], "gu": ["દવા"], "kn": ["ಔಷಧ"], "ml": ["മരുന്ന്"], "pa": ["ਦਵਾਈ"]},
    "/appointments": {"en": ["appointment", "doctor", "book"], "hi": ["अपॉइंटमेंट", "डॉक्टर", "मुलाकात"], "bn": ["অ্যাপয়েন্টমেন্ট", "ডাক্তার"], "ta": ["சந்திப்பு", "மருத்துவர்"], "te": ["అపాయింట్మెంట్", "డాక్టర్"], "mr": ["अपॉइंटमेंट", "डॉक्टर"], "gu": ["એપોઇન્ટમેન્ટ", "ડૉક્ટર"], "kn": ["ಅಪಾಯಿಂಟ್ಮೆಂಟ್", "ವೈದ್ಯ"], "ml": ["അപ്പോയിന്റ്മെന്റ്", "ഡോക്ടർ"], "pa": ["ਅਪੌਇੰਟਮੈਂਟ", "ਡਾਕਟਰ"]},
    "/reports": {"en": ["report", "reports", "lab report"], "hi": ["रिपोर्ट", "जांच"], "bn": ["রিপোর্ট"], "ta": ["அறிக்கை", "ரிப்போர்ட்"], "te": ["రిపోర్ట్"], "mr": ["रिपोर्ट", "अहवाल"], "gu": ["રિપોર્ટ"], "kn": ["ವರದಿ", "ರಿಪೋರ್ಟ್"], "ml": ["റിപ്പോർട്ട്"], "pa": ["ਰਿਪੋਰਟ"]},
    "/vitals": {"en": ["vitals", "heart rate", "pulse"], "hi": ["वाइटल", "नाड़ी", "धड़कन"], "bn": ["ভাইটাল", "হৃদস্পন্দন"], "ta": ["இதயத் துடிப்பு", "வைட்டல்"], "te": ["హృదయ స్పందన", "వైటల్"], "mr": ["हृदयाचे ठोके", "नाडी"], "gu": ["નાડી", "ધબકારા"], "kn": ["ಹೃದಯ ಬಡಿತ", "ನಾಡಿ"], "ml": ["ഹൃദയമിടിപ്പ്", "നാഡി"], "pa": ["ਨਬਜ਼", "ਧੜਕਣ"]},
    "/chat": {"en": ["assistant", "chat", "ask"], "hi": ["सहायक", "चैट", "पूछ"], "bn": ["সহকারী", "চ্যাট"], "ta": ["உதவியாளர்", "அரட்டை"], "te": ["సహాయకుడు", "చాట్"], "mr": ["सहाय्यक", "चॅट"], "gu": ["સહાયક", "ચેટ"], "kn": ["ಸಹಾಯಕ", "ಚಾಟ್"], "ml": ["സഹായി", "ചാറ്റ്"], "pa": ["ਸਹਾਇਕ", "ਚੈਟ"]},
    "/risk": {"en": ["risk", "risk check", "diabetes"], "hi": ["जोखिम", "रिस्क", "मधुमेह", "शुगर"], "bn": ["ঝুঁকি", "ডায়াবেটিস"], "ta": ["ஆபத்து", "நீரிழிவு"], "te": ["ప్రమాదం", "మధుమేహం"], "mr": ["धोका", "मधुमेह"], "gu": ["જોખમ", "ડાયાબિટીસ"], "kn": ["ಅಪಾಯ", "ಮಧುಮೇಹ"], "ml": ["അപകടസാധ്യത", "പ്രമേഹം"], "pa": ["ਜੋਖਮ", "ਸ਼ੂਗਰ"]},
    "/emergency": {"en": ["emergency page", "hospital", "nearby hospital"], "hi": ["अस्पताल"], "bn": ["হাসপাতাল"], "ta": ["மருத்துவமனை"], "te": ["ఆసుపత్రి"], "mr": ["रुग्णालय"], "gu": ["હોસ્પિટલ"], "kn": ["ಆಸ್ಪತ್ರೆ"], "ml": ["ആശുപത്രി"], "pa": ["ਹਸਪਤਾਲ"]},
    "/images": {"en": ["x-ray", "scan", "image"], "hi": ["एक्स-रे", "एक्सरे", "स्कैन"], "bn": ["এক্স-রে", "স্ক্যান"], "ta": ["எக்ஸ்ரே", "ஸ்கேன்"], "te": ["ఎక్స్-రే", "స్కాన్"], "mr": ["एक्स-रे", "स्कॅन"], "gu": ["એક્સ-રે", "સ્કેન"], "kn": ["ಎಕ್ಸ್-ರೇ", "ಸ್ಕ್ಯಾನ್"], "ml": ["എക്സ്-റേ", "സ്കാൻ"], "pa": ["ਐਕਸ-ਰੇ", "ਸਕੈਨ"]},
    "/profile": {"en": ["profile", "my health", "health id"], "hi": ["प्रोफाइल", "मेरा स्वास्थ्य", "स्वास्थ्य आईडी"], "bn": ["প্রোফাইল"], "ta": ["சுயவிவரம்"], "te": ["ప్రొఫైల్"], "mr": ["प्रोफाइल"], "gu": ["પ્રોફાઇલ"], "kn": ["ಪ್ರೊಫೈಲ್"], "ml": ["പ്രൊഫൈൽ"], "pa": ["ਪ੍ਰੋਫਾਈਲ"]},
}


def code(lang: str | None) -> str:
    c = (lang or "en").split("-")[0].lower()
    return c if c in LANGS else "en"


def emergency_hit(text: str, lang: str | None = None) -> str | None:
    """Returns the emergency message in the right language when the text contains a distress word in any supported language."""
    low = text.lower()
    for c, words in EMERGENCY_WORDS.items():
        if any(re.search(rf"(?<!\w){re.escape(w.lower())}(?!\w)", low) for w in words):
            return LANGS[code(lang) if lang else c]["emergency"]
    return None


def public_payload() -> list[dict]:
    return [{"code": c, **{k: v[k] for k in ("name", "native", "speech", "emergency")},
             "emergency_words": EMERGENCY_WORDS[c], "commands": {path: kw.get(c, []) + kw.get("en", []) for path, kw in COMMANDS.items()}} for c, v in LANGS.items()]
