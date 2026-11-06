import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Alert, Disclaimer } from "../components/ui.jsx";
import SosButton from "../components/SosButton.jsx";
import { hasVoiceFor, saveLang, savedLang, speak as speakText, useVoiceLangs } from "../components/voice.js";

const SR = typeof window !== "undefined" ? window.SpeechRecognition || window.webkitSpeechRecognition : null;

export default function Chat() {
  const { user } = useAuth();
  const langList = useVoiceLangs();
  const [lang, setLang] = useState(savedLang());
  const L = langList.find((l) => l.code === lang) || langList[0];
  const [msgs, setMsgs] = useState([{ role: "assistant", content: "Hello! Describe a symptom, ask about a medical term, or tap the mic. 🎤", urgency: "normal", actions: [] }]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [speak, setSpeak] = useState(false);
  const endRef = useRef(null);
  const recRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  const urlLang = lang;
  const say = (t) => {
    if (!speak) return;
    // regional languages without an LLM answer in English, so read those replies with an English voice
    speakText(t, (urlLang === "en" || !/[^\x00-\x7F]/.test(t)) ? "en-IN" : L.speech);
  };

  const send = async (e, override) => {
    e?.preventDefault();
    const message = (override ?? text).trim();
    if (!message || busy) return;
    const history = msgs.slice(-6).map(({ role, content }) => ({ role, content }));
    setMsgs((m) => [...m, { role: "user", content: message }]);
    setText("");
    setBusy(true);
    try {
      const r = await api("/chat", { method: "POST", body: { message, history, lang } });
      setMsgs((m) => [...m, { role: "assistant", content: r.reply, urgency: r.urgency, actions: r.actions }]);
      say(r.reply);
    } catch (err) {
      setMsgs((m) => [...m, { role: "assistant", content: `Sorry, something went wrong: ${err.message}`, urgency: "normal", actions: [] }]);
    } finally { setBusy(false); }
  };

  const mic = () => {
    if (!SR) return alert("Voice input is not supported in this browser. Try Chrome or Edge.");
    if (listening) return recRef.current?.stop();
    const rec = new SR();
    rec.lang = L.speech;
    rec.interimResults = false;
    rec.onresult = (ev) => send(null, ev.results[0][0].transcript);
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recRef.current = rec;
    setListening(true);
    rec.start();
  };

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-bold">Health assistant</h1>
        <div className="flex items-center gap-3 text-sm">
          <select className="input w-auto py-1" value={lang} onChange={(e) => { setLang(e.target.value); saveLang(e.target.value); }} aria-label="Language">
            {langList.map((l) => <option key={l.code} value={l.code}>{l.native}</option>)}
          </select>
          <label className="flex items-center gap-1"><input type="checkbox" checked={speak} onChange={(e) => setSpeak(e.target.checked)} /> Read aloud</label>
          {lang !== "en" && lang !== "hi" && <span className="text-xs text-amber-700">Detailed answers in {L.name} need the AI assistant enabled; otherwise replies are in English.</span>}
          {speak && !hasVoiceFor(L.speech) && <span className="text-xs text-amber-700">No {L.name} voice is installed on this device.</span>}
        </div>
      </div>
      <div className="card flex h-[60vh] flex-col">
        <div className="flex-1 space-y-3 overflow-y-auto pr-1" aria-live="polite">
          {msgs.map((m, i) => (
            <div key={i} className={m.role === "user" ? "text-right" : ""}>
              <div className={`inline-block max-w-[85%] whitespace-pre-line rounded-2xl px-4 py-2 text-left text-sm ${
                m.role === "user" ? "bg-brand-600 text-white" : m.urgency === "emergency" || m.urgency === "self_harm" ? "border-2 border-red-400 bg-red-50 text-red-900" : "bg-slate-100 text-slate-800"}`}>
                {m.content}
                {m.actions?.map((a, j) => a.type === "navigate" && user.role === "patient" ? <Link key={j} to={a.to} className="mt-2 block font-medium text-brand-700 underline">Open {a.to.slice(1)} →</Link>
                  : a.type === "call" ? <a key={j} href={`tel:${a.number}`} className="mr-3 mt-2 inline-block font-semibold text-red-700 underline">Call {a.number}</a>
                  : a.type === "sos" && user.role === "patient" ? <div key={j} className="mt-2"><SosButton compact /></div> : null)}
              </div>
            </div>
          ))}
          {busy && <p className="text-sm text-slate-400">Thinking…</p>}
          <div ref={endRef} />
        </div>
        <form onSubmit={send} className="mt-3 flex gap-2">
          <button type="button" onClick={mic} className={`btn-ghost ${listening ? "ring-2 ring-red-400" : ""}`} aria-label="Speak">{listening ? "● Listening" : "🎤"}</button>
          <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder={lang === "hi" ? "अपना सवाल लिखें…" : "Type your question…"} maxLength={1500} />
          <button className="btn-primary" disabled={busy}>Send</button>
        </form>
      </div>
      <Disclaimer />
    </>
  );
}
