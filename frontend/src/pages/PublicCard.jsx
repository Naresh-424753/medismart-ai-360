import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

/** Public, login-free emergency medical card (opened from the QR code). */
export default function PublicCard() {
  const { token } = useParams();
  const [c, setC] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    fetch(`${BASE}/public/emergency-card/${encodeURIComponent(token)}`).then((r) => (r.ok ? r.json() : Promise.reject(new Error("Card not found")))).then(setC).catch((e) => setErr(e.message));
  }, [token]);
  if (err) return <p className="p-8 text-center text-red-700">{err}</p>;
  if (!c) return <p className="p-8 text-center text-slate-500">Loading…</p>;
  return (
    <div className="mx-auto max-w-md space-y-3 p-4">
      <div className="rounded-xl bg-red-600 p-4 text-white"><p className="text-xs uppercase tracking-wide">Emergency medical card</p><p className="text-2xl font-bold">{c.name}</p><p className="text-sm">Health ID {c.health_id}</p></div>
      <div className="card text-sm">
        <p><b>Blood group:</b> <span className="text-xl font-bold text-red-700">{c.blood_group || "unknown"}</span></p>
        <p><b>Sex / DOB:</b> {c.sex || "—"} / {c.dob || "—"}</p>
        <p><b>Allergies:</b> {c.allergies.join(", ") || "none recorded"}</p>
        <p><b>Conditions:</b> {c.conditions.join(", ") || "none recorded"}</p>
      </div>
      <div className="card text-sm"><p className="label">Emergency contacts</p>{c.emergency_contacts.length === 0 && <p className="text-slate-500">None recorded.</p>}{c.emergency_contacts.map((e, i) => <p key={i}>{e.name} ({e.relation}) · <a className="font-semibold text-brand-700 underline" href={`tel:${e.phone}`}>{e.phone}</a></p>)}</div>
      <p className="text-center text-xs text-slate-500">Call <a className="underline" href="tel:112">112</a> / <a className="underline" href="tel:108">108</a> for emergencies. Information is patient-provided.</p>
    </div>
  );
}
