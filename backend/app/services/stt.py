"""Server-side speech-to-text for Indian languages: OpenAI-compatible Whisper API or Bhashini (MeitY, Dhruva pipeline).

Both need credentials you provide (see .env.example); neither was called from the build sandbox, so run a real
test with your keys. Audio is expected as 16 kHz mono WAV (the browser recorder produces exactly that).
Audio is sent to the chosen provider and is NOT stored by MediSmart.
"""
from __future__ import annotations

import base64

from ..config import settings

MAX_BYTES = 5 * 1024 * 1024
BHASHINI_ASR = {"en", "hi", "bn", "ta", "te", "mr", "gu", "kn", "ml", "pa"}
PIPELINE_URL = "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline"
INFERENCE_URL = "https://dhruva-api.bhashini.gov.in/services/inference/pipeline"


class STTError(Exception):
    pass


def providers() -> dict:
    w = bool(settings.WHISPER_API_KEY)
    b = bool(settings.BHASHINI_USER_ID and settings.BHASHINI_API_KEY)
    pref = settings.STT_PROVIDER
    active = pref if pref in ("whisper", "bhashini") and ((pref == "whisper" and w) or (pref == "bhashini" and b)) else ("bhashini" if b else "whisper" if w else None)
    return {"active": active, "whisper": w, "bhashini": b, "translate_to_english": bool(w or b), "browser_fallback": True}


async def _post(url: str, **kw):
    import httpx
    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.post(url, **kw)
    if r.status_code >= 400:
        raise STTError(f"Provider returned {r.status_code}: {r.text[:200]}")
    return r.json()


async def _whisper(audio: bytes, lang: str, translate: bool) -> str:
    base = settings.WHISPER_BASE_URL.rstrip("/")
    files = {"file": ("speech.wav", audio, "audio/wav")}
    data = {"model": settings.WHISPER_MODEL, "response_format": "json"}
    if translate:
        j = await _post(f"{base}/audio/translations", headers={"Authorization": f"Bearer {settings.WHISPER_API_KEY}"}, files=files, data=data)
    else:
        if lang:
            data["language"] = lang
        j = await _post(f"{base}/audio/transcriptions", headers={"Authorization": f"Bearer {settings.WHISPER_API_KEY}"}, files=files, data=data)
    return (j.get("text") or "").strip()


async def _bhashini_config(tasks: list[dict]) -> dict:
    return await _post(PIPELINE_URL, headers={"userID": settings.BHASHINI_USER_ID, "ulcaApiKey": settings.BHASHINI_API_KEY, "Content-Type": "application/json"},
                       json={"pipelineTasks": tasks, "pipelineRequestConfig": {"pipelineId": settings.BHASHINI_PIPELINE_ID}})


def _service_id(cfg: dict, task: str) -> str:
    for item in cfg.get("pipelineResponseConfig", []):
        if item.get("taskType") == task and item.get("config"):
            return item["config"][0]["serviceId"]
    raise STTError(f"Bhashini has no {task} service for this language")


async def _bhashini(audio: bytes, lang: str, translate: bool) -> str:
    if lang not in BHASHINI_ASR:
        raise STTError("Bhashini speech recognition is not available for this language")
    tasks = [{"taskType": "asr", "config": {"language": {"sourceLanguage": lang}}}]
    if translate and lang != "en":
        tasks.append({"taskType": "translation", "config": {"language": {"sourceLanguage": lang, "targetLanguage": "en"}}})
    cfg = await _bhashini_config(tasks)
    key = cfg["pipelineInferenceAPIEndPoint"]["inferenceApiKey"]["value"]
    hdr = {"Authorization": key, "Content-Type": "application/json", "Accept": "*/*"}
    asr = {"taskType": "asr", "config": {"language": {"sourceLanguage": lang}, "serviceId": _service_id(cfg, "asr"), "audioFormat": "wav", "samplingRate": 16000}}
    out = await _post(INFERENCE_URL, headers=hdr, json={"pipelineTasks": [asr], "inputData": {"audio": [{"audioContent": base64.b64encode(audio).decode()}]}})
    text = out["pipelineResponse"][0]["output"][0]["source"].strip()
    if translate and lang != "en" and text:
        tr = {"taskType": "translation", "config": {"language": {"sourceLanguage": lang, "targetLanguage": "en"}, "serviceId": _service_id(cfg, "translation")}}
        out = await _post(INFERENCE_URL, headers=hdr, json={"pipelineTasks": [tr], "inputData": {"input": [{"source": text}]}})
        text = out["pipelineResponse"][0]["output"][0]["target"].strip()
    return text


async def transcribe(audio: bytes, lang: str, translate_to_english: bool = False) -> dict:
    p = providers()
    if not p["active"]:
        raise STTError("No speech-to-text provider is configured on the server")
    if len(audio) > MAX_BYTES:
        raise STTError("Recording is too long (max about 2.5 minutes)")
    if len(audio) < 2000:
        raise STTError("Recording is empty")
    fn = _bhashini if p["active"] == "bhashini" else _whisper
    text = await fn(audio, lang, translate_to_english)
    return {"text": text, "provider": p["active"], "language": "en" if translate_to_english else lang, "translated": translate_to_english}
