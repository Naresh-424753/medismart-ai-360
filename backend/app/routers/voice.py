from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..common import log_event
from ..db import get_db
from ..deps import current_user
from ..services import languages, stt, symptoms

router = APIRouter(prefix="/voice", tags=["multilingual voice"])


@router.get("/languages")
async def langs():
    """Public: languages, speech-recognition codes, voice-command keywords and emergency words (used by the browser)."""
    return languages.public_payload()


@router.get("/providers")
async def providers():
    """Which server-side speech-to-text provider is configured (if none, the browser's own speech recognition is used)."""
    return stt.providers()


async def _read(file: UploadFile) -> bytes:
    data = await file.read()
    if len(data) > stt.MAX_BYTES:
        raise HTTPException(413, "Recording too long")
    return data


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...), lang: str = Form("hi"), user: dict = Depends(current_user)):
    lc = languages.code(lang)
    try:
        return await stt.transcribe(await _read(file), lc)
    except stt.STTError as e:
        raise HTTPException(502 if "Provider" in str(e) else 400, str(e))


@router.post("/symptom-check")
async def voice_symptom_check(file: UploadFile = File(...), lang: str = Form("hi"), user: dict = Depends(current_user)):
    """Speak symptoms in your own language -> transcript -> English -> rule-based symptom checker.
    Distress words in the original language trigger the fixed emergency message BEFORE any translation."""
    lc = languages.code(lang)
    audio = await _read(file)
    try:
        native = await stt.transcribe(audio, lc)
        em = languages.emergency_hit(native["text"], lc)
        if em:
            return {"transcript": native["text"], "emergency": True, "emergency_message": em, "provider": native["provider"], "result": None}
        english = native if lc == "en" else await stt.transcribe(audio, lc, translate_to_english=True)
    except stt.STTError as e:
        raise HTTPException(502 if "Provider" in str(e) else 400, str(e))
    res = symptoms.check([], english["text"])
    if user["role"] == "patient":
        await log_event(get_db(), user["id"], "symptoms", f"Voice symptom check ({languages.LANGS[lc]['name']})", {"urgency": res["urgency"]})
    return {"transcript": native["text"], "english_text": english["text"], "emergency": res["urgency"] == "emergency", "emergency_message": languages.LANGS[lc]["emergency"] if res["urgency"] == "emergency" else None,
            "provider": native["provider"], "result": res, "note": "Machine transcription and translation can be wrong; check the text before relying on the result."}
