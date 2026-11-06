import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { Alert, Badge, Card } from "./ui.jsx";
import { SR, saveLang, savedLang, speak, useVoiceLangs } from "./voice.js";
import { startWavRecorder } from "./recorder.js";

/** Speak your symptoms in your own language. Uses the server's Whisper/Bhashini when configured, else the browser's speech recognition (English only for the checker). */
export default function VoiceSymptoms() {
  const langs = useVoiceLangs();
  const [code, setCode] = useState(savedLang());
  const [prov, setProv] = useState(null);
  const [rec, setRec] = useState(null);
  const [busy, setBusy] = useState(false);
  const [out, setOut] = useState(null);
  const [err, setErr] = useState("");
  const br = useRef(null);
  const lang = langs.find((l) => l.code === code) || langs[0];
  useEffect(() => { api("/voice/providers").then(setProv).catch(() => setProv({ active: null })); }, []);

  const emergencyLocal = (text) => lang.emergency_words?.some((w) => text.toLowerCase().includes(w.toLowerCase()));
  const show = (r) => { setOut(r); if (r.emergency && r.emergency_message) speak(r.emergency_message, lang.speech); };

  const server = async () => {
    if (rec) {
      setBusy(true);
      const blob = await rec.stop(); setRec(null);
      await send(blob);
      return;
    }
    setErr(""); setOut(null);
    try { setRec(await startWavRecorder(30, (b) => { setRec(null); setBusy(true); send(b); })); } catch { setErr("Microphone not available or permission denied."); }
  };
  const send = async (blob) => {
    try {
      const form = new FormData(); form.append("file", blob, "speech.wav"); form.append("lang", code);
      show(await api("/voice/symptom-check", { method: "POST", form }));
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };

  const browser = () => {
    if (br.current) { br.current.stop(); return; }
    setErr(""); setOut(null);
    const r = new SR(); r.lang = lang.speech; r.interimResults = false;
    r.onresult = async (e) => {
      const text = e.results[0][0].transcript;
      if (emergencyLocal(text)) { show({ transcript: text, emergency: true, emergency_message: lang.emergency, result: null }); return; }
      if (code !== "en") { setOut({ transcript: text, result: null, unsupported: true }); return; }
      try { show({ transcript: text, english_text: text, result: await api("/ai/symptom-check", { method: "POST", body: { symptoms: [], text } }) }); } catch (x) { setErr(x.message); }
    };
    r.onend = () => { br.current = null; setBusy(false); }; r.onerror = () => { br.current = null; setBusy(false); setErr("Speech recognition failed. Try Chrome/Edge, or type your symptoms."); };
    br.current = r; setBusy(true); r.start();
  };

  if (!prov || !lang) return null;
  const useServer = !!prov.active;
  const can = useServer || !!SR;
  const res = out?.result;
  return (
    <Card title="Speak your symptoms">
      <p className="mb-2 text-sm text-slate-600">Describe how you feel in your own language. {useServer ? `Speech is converted by ${prov.active === "bhashini" ? "Bhashini" : "Whisper"} on the server.` : "This device's browser converts your speech; regional-language symptom checking needs the server's Whisper/Bhashini key."}</p>
      <div className="flex flex-wrap items-center gap-2">
        <select aria-label="Language" className="input w-auto" value={code} onChange={(e) => { setCode(e.target.value); saveLang(e.target.value); }}>{langs.map((l) => <option key={l.code} value={l.code}>{l.native} ({l.name})</option>)}</select>
        <button className={rec || br.current ? "btn-danger" : "btn-primary"} disabled={!can || (busy && !rec && !br.current)} onClick={useServer ? server : browser}>{rec ? "Stop and check" : busy ? "Working…" : "🎤 Speak"}</button>
        {!can && <span className="text-xs text-amber-700">Speech input is not supported in this browser. Type your symptoms instead.</span>}
      </div>
      <div className="mt-3 space-y-2"><Alert tone="error">{err}</Alert></div>
      {out && (
        <div className="mt-3 space-y-2 text-sm">
          <p><b>You said:</b> {out.transcript}</p>
          {out.english_text && out.english_text !== out.transcript && <p><b>In English:</b> {out.english_text}</p>}
          {out.unsupported && <Alert tone="warn">The symptom checker understands English only. Ask the administrator to enable Whisper or Bhashini for {lang.name}, or speak in English.</Alert>}
          {out.emergency && <Alert tone="error">{out.emergency_message || "This may be an emergency. Call 112 or 108 now."}</Alert>}
          {res && (
            <>
              <p>Urgency: <Badge tone={res.urgency === "emergency" ? "bad" : res.urgency === "see_doctor" ? "warn" : "good"}>{res.urgency.replace("_", " ")}</Badge> <span className="text-xs text-slate-500">symptoms understood: {res.symptoms.join(", ") || "none"}</span></p>
              <ul className="list-disc pl-5">{res.possible_conditions.slice(0, 3).map((c) => <li key={c.condition}><b>{c.condition}</b> ({Math.round(c.match * 100)}%) · see {c.specialist}</li>)}</ul>
              <button className="btn-ghost py-1" onClick={() => speak(`Urgency ${res.urgency.replace("_", " ")}. ${res.possible_conditions.slice(0, 2).map((c) => c.condition).join(", ")}. Please consult a ${res.possible_conditions[0]?.specialist || "doctor"}.`, "en-IN")}>🔊 Listen (English)</button>
            </>
          )}
          {out.note && <p className="text-xs text-slate-500">{out.note}</p>}
        </div>
      )}
    </Card>
  );
}
