import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { savedLang, useVoiceLangs } from "./voice.js";

/** Press-and-confirm SOS. Sends live GPS when the browser allows it. */
export default function SosButton({ compact = false }) {
  const [state, setState] = useState("idle"); // idle | confirm | sending | sent | error
  const [msg, setMsg] = useState("");

  const send = () => {
    setState("sending");
    const post = (coords) =>
      api("/emergency/sos", { method: "POST", body: { type: "sos", lat: coords?.latitude ?? null, lon: coords?.longitude ?? null, message: "Manual SOS from app" } })
        .then(() => { setState("sent"); setMsg(coords ? "Your contacts were alerted with your location." : "Your contacts were alerted (location unavailable)."); })
        .catch((e) => { setState("error"); setMsg(e.message + " — call 112 now."); });
    if (!navigator.geolocation) return post(null);
    navigator.geolocation.getCurrentPosition((p) => post(p.coords), () => post(null), { enableHighAccuracy: true, timeout: 6000 });
  };

  if (state === "confirm")
    return (
      <div className="flex items-center gap-2 rounded-xl border-2 border-red-500 bg-red-50 p-2">
        <span className="text-sm font-medium text-red-800">Send emergency alert?</span>
        <button className="btn-danger" onClick={send}>Yes, send</button>
        <button className="btn-ghost" onClick={() => setState("idle")}>Cancel</button>
      </div>
    );
  if (state === "sending") return <button className="btn-danger" disabled>Sending…</button>;
  if (state === "sent" || state === "error")
    return (
      <div className="max-w-xs text-sm" role="status">
        <p className={state === "sent" ? "font-medium text-emerald-700" : "font-medium text-red-700"}>{msg}</p>
        <p className="text-slate-600">If you are in danger, call <a className="font-semibold underline" href="tel:112">112</a> or <a className="font-semibold underline" href="tel:108">108</a>.</p>
        <button className="mt-1 text-xs text-slate-500 underline" onClick={() => setState("idle")}>Dismiss</button>
      </div>
    );
  return (
    <button className={`btn-danger ${compact ? "" : "px-6 py-3 text-base font-bold shadow-lg"}`} onClick={() => setState("confirm")} aria-label="Emergency SOS">
      🚨 SOS
    </button>
  );
}


/** Voice-based emergency assistant: say "help" / "madad" / "bachao" -> 10-second countdown -> SOS (cancel any time). */
export function VoiceSos() {
  const SR = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);
  const [on, setOn] = useState(false);
  const [heard, setHeard] = useState("");
  const [count, setCount] = useState(0);
  const [done, setDone] = useState("");
  const rec = useRef(null);
  const langs = useVoiceLangs();
  const lang = langs.find((l) => l.code === savedLang()) || langs[0];

  const fire = () => {
    const post = (c) => api("/emergency/sos", { method: "POST", body: { type: "sos", lat: c?.latitude ?? null, lon: c?.longitude ?? null, message: "Voice-activated SOS" } })
      .then(() => setDone("Alert sent to your emergency contacts. Call 112 if in danger.")).catch((e) => setDone(e.message + " - call 112 now."));
    navigator.geolocation ? navigator.geolocation.getCurrentPosition((p) => post(p.coords), () => post(null), { timeout: 5000 }) : post(null);
  };
  useEffect(() => {
    if (count <= 0) return;
    const t = setTimeout(() => { if (count === 1) fire(); setCount(count - 1); }, 1000);
    return () => clearTimeout(t);
  }, [count]); // eslint-disable-line

  const start = () => {
    const r = new SR();
    r.continuous = true; r.interimResults = false; r.lang = lang.speech;
    r.onresult = (e) => {
      const said = e.results[e.results.length - 1][0].transcript.toLowerCase();
      setHeard(said);
      const words = [...new Set(langs.flatMap((l) => l.code === lang.code || l.code === "en" ? l.emergency_words : []))];
      if (words.some((w) => said.includes(w.toLowerCase()))) { setCount(10); setDone(""); }
    };
    r.onend = () => { if (rec.current) { try { r.start(); } catch { /* already started */ } } };
    rec.current = r; r.start(); setOn(true);
  };
  const stop = () => { const r = rec.current; rec.current = null; r?.stop(); setOn(false); };
  useEffect(() => () => { const r = rec.current; rec.current = null; r?.stop(); }, []);

  if (!SR) return <p className="text-sm text-slate-500">Voice emergency assistant is not supported in this browser (try Chrome).</p>;
  return (
    <div className="space-y-2 text-sm">
      {count > 0 ? (
        <div className="rounded-xl border-2 border-red-500 bg-red-50 p-3"><p className="font-bold text-red-800">Emergency heard. Sending alert in {count}s</p><button className="btn-ghost mt-2" onClick={() => setCount(0)}>I'm OK - cancel</button></div>
      ) : on ? (
        <div><p className="font-medium text-emerald-700">🎤 Listening… say "help"{lang.code !== "en" ? ` or the word for help in ${lang.name}` : ""}</p>{heard && <p className="text-xs text-slate-500">Heard: "{heard}"</p>}<button className="btn-ghost mt-1" onClick={stop}>Turn off</button></div>
      ) : <button className="btn-ghost" onClick={start}>🎤 Turn on voice emergency assistant</button>}
      {done && <p className="font-medium">{done}</p>}
      <p className="text-xs text-slate-500">Keep this page open. The browser asks for microphone permission; audio is not recorded or stored by MediSmart.</p>
    </div>
  );
}
