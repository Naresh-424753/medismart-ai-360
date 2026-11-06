import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { Alert, Badge, toneFor } from "../components/ui.jsx";

/** Public, no-login health kiosk: big buttons for hospital lobbies, pharmacies and community centres. */
export default function Kiosk() {
  const [view, setView] = useState("home");
  return (
    <div className="min-h-screen bg-gradient-to-br from-brand-50 to-sky-50 p-4 md:p-8">
      <div className="mx-auto max-w-3xl space-y-4">
        <header className="flex items-center justify-between">
          <div><p className="text-2xl font-bold text-brand-700">MediSmart Health Kiosk</p><p className="text-sm text-slate-500">No login needed. Nothing you enter is stored.</p></div>
          {view !== "home" ? <button className="btn-primary" onClick={() => setView("home")}>⟵ Back</button> : <Link className="btn-ghost" to="/login">Log in</Link>}
        </header>
        {view === "home" && (
          <div className="grid gap-4 sm:grid-cols-2">
            {[["symptoms", "🩺", "Check my symptoms"], ["bmi", "⚖️", "BMI check"], ["hospitals", "🏥", "Nearest hospitals"], ["emergency", "🚨", "Emergency numbers"]].map(([k, i, l]) => (
              <button key={k} onClick={() => setView(k)} className="card flex h-40 flex-col items-center justify-center gap-2 text-xl font-semibold shadow-md hover:bg-brand-50"><span className="text-5xl">{i}</span>{l}</button>
            ))}
          </div>
        )}
        {view === "symptoms" && <Symptoms />}{view === "bmi" && <Bmi />}{view === "hospitals" && <Hospitals />}{view === "emergency" && <Numbers />}
        <p className="text-center text-xs text-slate-500">Educational information only, not a diagnosis. In an emergency call 112 / 108.</p>
      </div>
    </div>
  );
}

function Symptoms() {
  const [text, setText] = useState("");
  const [r, setR] = useState(null);
  const [err, setErr] = useState("");
  const go = async (e) => { e.preventDefault(); setErr(""); try { setR(await api("/kiosk/symptom-check", { method: "POST", body: { text } })); } catch (x) { setErr(x.message); } };
  return (
    <div className="card space-y-3">
      <form onSubmit={go} className="space-y-3"><label className="label text-base">Describe how you feel</label><textarea className="input min-h-[120px] text-lg" required minLength={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. fever and cough for 2 days" /><button className="btn-primary w-full py-3 text-lg">Check</button></form>
      <Alert tone="error">{err}</Alert>
      {r && (
        <div className="space-y-2 text-base">
          <p>Urgency: <Badge tone={r.urgency === "emergency" ? "bad" : toneFor(r.urgency)}>{r.urgency}</Badge></p>
          {(r.red_flags || []).length > 0 && <Alert tone="error">Warning signs: {r.red_flags.join(", ")}. Seek urgent care.</Alert>}
          <ul className="list-disc pl-5">{(r.possible_conditions || []).map((c) => <li key={c.condition}>{c.condition} <span className="text-sm text-slate-500">(see: {c.specialist})</span></li>)}</ul>
          {r.possible_conditions?.[0]?.self_care && <p className="text-slate-600">{r.possible_conditions[0].self_care}</p>}
          {r.urgency === "unknown" && <p className="text-slate-600">Could not match those symptoms. Please speak to a doctor or pharmacist.</p>}
        </div>
      )}
    </div>
  );
}

function Bmi() {
  const [f, setF] = useState({ weight_kg: "", height_cm: "" });
  const [r, setR] = useState(null);
  const [err, setErr] = useState("");
  const go = async (e) => { e.preventDefault(); setErr(""); try { setR(await api("/kiosk/bmi", { method: "POST", body: { weight_kg: +f.weight_kg, height_cm: +f.height_cm } })); } catch (x) { setErr(x.message); } };
  return (
    <form onSubmit={go} className="card space-y-3">
      <label className="label text-base">Weight (kg)</label><input className="input text-lg" type="number" step="0.1" required value={f.weight_kg} onChange={(e) => setF({ ...f, weight_kg: e.target.value })} />
      <label className="label text-base">Height (cm)</label><input className="input text-lg" type="number" required value={f.height_cm} onChange={(e) => setF({ ...f, height_cm: e.target.value })} />
      <button className="btn-primary w-full py-3 text-lg">Calculate</button><Alert tone="error">{err}</Alert>
      {r && <p className="text-center text-3xl font-bold text-brand-700">{r.bmi} <span className="text-lg font-medium text-slate-600">{r.category}</span></p>}
    </form>
  );
}

function Hospitals() {
  const [list, setList] = useState(null);
  const [msg, setMsg] = useState("");
  const load = (q) => api(`/kiosk/hospitals${q}`).then(setList).catch((e) => setMsg(e.message));
  return (
    <div className="card space-y-3">
      <button className="btn-primary w-full py-3 text-lg" onClick={() => navigator.geolocation ? navigator.geolocation.getCurrentPosition((p) => load(`?lat=${p.coords.latitude}&lon=${p.coords.longitude}`), () => { setMsg("Location blocked. Showing all hospitals."); load(""); }) : load("")}>📍 Use my location</button>
      <Alert tone="info">{msg}</Alert>
      {list && list.map((h) => <div key={h.name} className="rounded-lg border border-slate-200 p-3"><p className="text-lg font-semibold">{h.name}</p><p className="text-sm text-slate-600">{h.city} · {h.address} · {h.distance_km != null ? `${h.distance_km} km` : ""}</p><p className="text-sm">ICU beds free: <b>{h.icu_available}</b> · Emergency beds free: <b>{h.emergency_beds}</b> · <a className="text-brand-700 underline" href={`tel:${h.phone}`}>{h.phone}</a></p></div>)}
    </div>
  );
}

function Numbers() {
  const rows = [["National emergency", "112"], ["Ambulance", "108"], ["Women helpline", "1091"], ["Poison control", "1066"], ["Tele-MANAS mental health", "14416"]];
  return <div className="card space-y-2">{rows.map(([n, p]) => <a key={p} href={`tel:${p}`} className="flex items-center justify-between rounded-xl bg-red-50 px-4 py-4 text-xl font-bold text-red-700"><span>{n}</span><span>{p}</span></a>)}</div>;
}
