from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..common import new_id, now
from ..db import get_db
from ..deps import current_user
from ..services import chatbot, languages

router = APIRouter(prefix="/chat", tags=["chatbot"])


class ChatIn(BaseModel):
    message: str
    lang: str | None = None  # "en" | "hi"


@router.post("")
async def chat(body: ChatIn, user: dict = Depends(current_user)):
    db = get_db()
    msg = body.message.strip()[:2000]
    lc = languages.code(body.lang)
    if lc in ("en", "hi"):
        base = chatbot.reply(msg, lc)
    else:
        # Regional languages: distress words get a fixed safe answer in the user's language; other answers need the LLM (below) or fall back to English.
        em = languages.emergency_hit(msg, lc)
        base = ({"reply": em, "intent": "emergency", "emergency": True, "urgency": "emergency", "lang": lc} if em else
                {"reply": "I heard you in " + languages.LANGS[lc]["name"] + ". Detailed answers in this language need the AI assistant to be enabled by the administrator; "
                          "please describe your symptoms in English or Hindi, or consult a doctor.", "intent": "unsupported_language", "lang": "en"})
    out = dict(base)
    # Emergencies always use the fixed safe answer; for everything else an LLM (if configured) may enrich the reply.
    if not base.get("emergency"):
        hist = await db.chat_history.find({"user_id": user["id"]}, {"_id": 0}).sort([("ts", -1), ("seq", -1)]).limit(8).to_list(8)
        hist = [{"role": h["role"], "content": h["content"]} for h in reversed(hist)]
        llm = await chatbot.llm_reply(msg, hist, languages.LANGS[lc]["name"])
        if llm:
            out["reply"], out["source"] = llm, "llm"
    out.setdefault("source", "rules")
    await db.chat_history.insert_many([
        {"id": new_id(), "user_id": user["id"], "role": "user", "content": msg, "ts": now(), "seq": 0},
        {"id": new_id(), "user_id": user["id"], "role": "assistant", "content": out["reply"], "ts": now(), "seq": 1},
    ])
    return out


@router.get("/history")
async def history(user: dict = Depends(current_user)):
    docs = await get_db().chat_history.find({"user_id": user["id"]}, {"_id": 0}).sort([("ts", -1), ("seq", -1)]).limit(60).to_list(60)
    return list(reversed(docs))


@router.delete("/history")
async def clear_history(user: dict = Depends(current_user)):
    await get_db().chat_history.delete_many({"user_id": user["id"]})
    return {"cleared": True}
