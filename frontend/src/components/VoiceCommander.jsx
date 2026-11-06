import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { startWavRecorder } from "./recorder.js";
import { SR, matchCommand, saveLang, savedLang, speak, useVoiceLangs } from "./voice.js";

/** Floating microphone: say a page name ("दवा", "மருந்து", "reports"...) in the chosen language to navigate. */
export default function VoiceCommander({ onSos }) {
  const langs = useVoiceLangs();
  const nav = useNavigate();
  const [code, setCode] = useState(savedLang());
  const [open, setOpen] = useState(false);
  const [on, setOn] = useState(false);
  const [msg, setMsg] = useState("");
  const rec = useRef(null);
  const [prov, setProv] = useState(null);
  useEffect(() => { api("/voice/providers").then(setProv).catch(() => {}); }, []);
  const lang = langs.find((l) => l.code === code) || langs[0];

  const stop = () => { const r = rec.current; rec.current = null; r?.stop?.(); setOn(false); };
  useEffect(() => () => stop(), []); // eslint-disable-line
  const server = !!prov?.active;
  if (!SR && !server) return null;

  const route = (alts) => {
    setMsg(`"${alts[0]}"`);
    const cmd = alts.map((a) => matchCommand(a, lang)).find(Boolean);
    if (!cmd) { setMsg(`"${alts[0]}" — not understood. Try: medicines, reports, appointments, vitals, assistant.`); return; }
    if (cmd.type === "sos") { setMsg(lang.emergency); speak(lang.emergency, lang.speech); onSos?.(); nav("/emergency"); return; }
    nav(cmd.path); setOpen(false);
  };
  const startServer = async () => {
    try {
      const h = await startWavRecorder(8, (b) => { rec.current = null; setOn(false); upload(b); });
      rec.current = { stop: async () => { rec.current = null; setOn(false); upload(await h.stop()); } };
      setOn(true); setMsg("Listening… tap Stop when done");
    } catch { setMsg("Microphone not available or permission denied."); }
  };
  const upload = async (blob) => {
    if (!blob) return;
    setMsg("Understanding…");
    try { const form = new FormData(); form.append("file", blob, "speech.wav"); form.append("lang", code); const r = await api("/voice/transcribe", { method: "POST", form }); route([r.text]); }
    catch (e) { setMsg(e.message); }
  };

  const start = () => {
    if (server) return startServer();
    stop();
    const r = new SR();
    r.lang = lang.speech; r.interimResults = false; r.maxAlternatives = 3;
    r.onresult = (e) => {
      const alts = Array.from(e.results[0]).map((a) => a.transcript);
      setMsg(`"${alts[0]}"`);
      const cmd = alts.map((a) => matchCommand(a, lang)).find(Boolean);
      if (!cmd) { setMsg(`"${alts[0]}" — not understood. Try: medicines, reports, appointments, vitals, assistant.`); return; }
      if (cmd.type === "sos") { setMsg(lang.emergency); speak(lang.emergency, lang.speech); onSos?.(); nav("/emergency"); return; }
      nav(cmd.path); setOpen(false);
    };
    r.onend = () => setOn(false);
    r.onerror = () => { setOn(false); setMsg("Microphone not available or permission denied."); };
    rec.current = r; setOn(true); setMsg("Listening…"); r.start();
  };

  return (
    <div className="fixed bottom-4 right-4 z-40 flex flex-col items-end gap-2">
      {open && (
        <div className="w-72 space-y-2 rounded-xl border border-slate-200 bg-white p-3 text-sm shadow-lg">
          <label className="label" htmlFor="vc-lang">Voice language</label>
          <select id="vc-lang" className="input" value={code} onChange={(e) => { setCode(e.target.value); saveLang(e.target.value); }}>
            {langs.map((l) => <option key={l.code} value={l.code}>{l.native} ({l.name})</option>)}
          </select>
          <button className="btn-primary w-full" onClick={on ? stop : start}>{on ? "Stop" : "🎤 Speak a command"}</button>
          {msg && <p className="text-slate-600" role="status">{msg}</p>}
          <p className="text-xs text-slate-500">Say a page name, or "help" / "मदद" for emergency. Works best in Chrome or Edge.</p>
        </div>
      )}
      <button onClick={() => setOpen(!open)} aria-label="Voice commands" className={`h-14 w-14 rounded-full text-2xl text-white shadow-lg ${on ? "animate-pulse bg-red-600" : "bg-brand-600"}`}>🎤</button>
    </div>
  );
}
