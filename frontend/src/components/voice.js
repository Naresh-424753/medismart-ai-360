import { useEffect, useState } from "react";
import { api } from "../api.js";

export const SR = typeof window !== "undefined" ? window.SpeechRecognition || window.webkitSpeechRecognition : null;
let cache = null;

/** Languages + voice-command vocabulary from the server (/voice/languages). Falls back to English/Hindi offline. */
export function useVoiceLangs() {
  const [langs, setLangs] = useState(cache || [
    { code: "en", name: "English", native: "English", speech: "en-IN", emergency: "This may be an emergency. Call 112 or 108 now.", emergency_words: ["help", "emergency"], commands: {} },
    { code: "hi", name: "Hindi", native: "हिन्दी", speech: "hi-IN", emergency: "यह आपातकाल हो सकता है। अभी 112 या 108 पर कॉल करें।", emergency_words: ["मदद", "बचाओ"], commands: {} },
  ]);
  useEffect(() => {
    if (cache) return;
    api("/voice/languages").then((l) => { cache = l; setLangs(l); }).catch(() => {});
  }, []);
  return langs;
}

export const savedLang = () => { try { return localStorage.getItem("ms_voice_lang") || "en"; } catch { return "en"; } };
export const saveLang = (c) => { try { localStorage.setItem("ms_voice_lang", c); } catch { /* private mode */ } };

/** Speak text with a voice matching the language tag; returns false when the browser has no voice for it. */
export function speak(text, tag) {
  if (!("speechSynthesis" in window) || !text) return false;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = tag;
  const base = tag.split("-")[0];
  const v = window.speechSynthesis.getVoices().find((x) => x.lang === tag) || window.speechSynthesis.getVoices().find((x) => x.lang.startsWith(base));
  if (v) u.voice = v;
  window.speechSynthesis.speak(u);
  return !!v || window.speechSynthesis.getVoices().length === 0;
}

export const hasVoiceFor = (tag) => !("speechSynthesis" in window) || window.speechSynthesis.getVoices().some((v) => v.lang.startsWith(tag.split("-")[0]));

/** Finds the page whose keyword appears in what the user said. */
export function matchCommand(said, lang) {
  const t = said.toLowerCase();
  if (lang.emergency_words?.some((w) => t.includes(w.toLowerCase()))) return { type: "sos" };
  for (const [path, words] of Object.entries(lang.commands || {})) {
    if (words.some((w) => t.includes(w.toLowerCase()))) return { type: "go", path };
  }
  return null;
}
