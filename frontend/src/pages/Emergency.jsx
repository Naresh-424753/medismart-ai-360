import { useEffect, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Alert, Badge, Card, Empty, Field, useAsync } from "../components/ui.jsx";
import SosButton, { VoiceSos } from "../components/SosButton.jsx";

export default function Emergency() {
  const { user } = useAuth();
  const [dir, setDir] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [pos, setPos] = useState(null);
  const [near, setNear] = useState([]);
  const [route, setRoute] = useState(null);
  const [kind, setKind] = useState("ambulance");
  const [msg, setMsg] = useState("");
  const [sent, setSent] = useState("");
  const { busy, error, run } = useAsync();

  const load = () => api("/emergency/alerts").then(setAlerts).catch(() => {});
  useEffect(() => {
    api("/emergency/directory").then(setDir).catch(() => {}); load();
    const t = setInterval(load, 10000); return () => clearInterval(t);
  }, []);
  const locate = () => navigator.geolocation?.getCurrentPosition(
    (p) => run(async () => {
      const c = { lat: p.coords.latitude, lon: p.coords.longitude }; setPos(c);
      setNear(await api(`/emergency/hospitals/nearby?lat=${c.lat}&lon=${c.lon}`)); setRoute(await api(`/emergency/route-suggestion?lat=${c.lat}&lon=${c.lon}`));
    }), () => run(async () => { throw new Error("Location permission denied. You can still send an alert without location."); }), { timeout: 8000 });
  const send = () => run(async () => { await api("/emergency/sos", { method: "POST", body: { type: kind, lat: pos?.lat ?? null, lon: pos?.lon ?? null, message: msg } }); setSent("Request sent. Your emergency contacts and nearby ambulances were notified."); setMsg(""); load(); });
  const cancel = (id) => run(async () => { await api(`/emergency/alerts/${id}?status=cancelled`, { method: "PATCH" }); load(); });

  return (
    <>
      <h1 className="text-xl font-bold">Emergency</h1>
      <Alert tone="warn">In a life-threatening emergency call <a className="font-bold underline" href="tel:112">112</a> or <a className="font-bold underline" href="tel:108">108</a> first.</Alert>
      <Alert tone="error">{error}</Alert><Alert tone="ok">{sent}</Alert>
      {["patient", "family"].includes(user.role) && (
        <Card title="Request help">
          <div className="grid gap-3 md:grid-cols-4">
            <Field label="Type"><select className="input" value={kind} onChange={(e) => setKind(e.target.value)}><option value="ambulance">Ambulance</option><option value="accident">Accident report</option><option value="sos">General SOS</option></select></Field>
            <div className="md:col-span-2"><Field label="Message (optional)"><input className="input" value={msg} onChange={(e) => setMsg(e.target.value)} /></Field></div>
            <div className="flex items-end gap-2"><button className="btn-ghost" onClick={locate}>{pos ? "Location ✓" : "Use my location"}</button><button className="btn-danger" onClick={send} disabled={busy}>Send</button></div>
          </div>
          <div className="mt-3"><SosButton compact /></div>
          <div className="mt-4 border-t border-slate-100 pt-3"><p className="mb-1 text-sm font-semibold">Voice emergency assistant</p><VoiceSos /></div>
        </Card>
      )}
      {route?.recommended && (
        <Card title="Recommended hospital (nearest with emergency beds)">
          <p className="text-sm"><b>{route.recommended.name}</b> · {route.recommended.distance_km} km · ~{route.recommended.eta_min} min · {route.recommended.emergency_beds} emergency / {route.recommended.icu_beds} ICU beds · <a className="text-brand-700 underline" href={`tel:${route.recommended.phone}`}>{route.recommended.phone}</a></p>
          <p className="text-xs text-slate-500">{route.note}</p>
        </Card>
      )}
      {near.length > 0 && <Card title="Nearby hospitals"><ul className="divide-y divide-slate-100 text-sm">{near.slice(0, 8).map((h) => <li key={h.id} className="py-1.5"><b>{h.name}</b> · {h.distance_km} km · {h.emergency_beds} emergency beds · <a className="text-brand-700 underline" target="_blank" rel="noreferrer" href={`https://www.google.com/maps/dir/?api=1&destination=${h.lat},${h.lon}`}>directions</a></li>)}</ul></Card>}
      <Card title="My emergency requests">
        {alerts.length === 0 && <Empty>None.</Empty>}
        <ul className="divide-y divide-slate-100 text-sm">
          {alerts.map((a) => (
            <li key={a.id} className="space-y-0.5 py-2">
              <div className="flex items-center justify-between"><span><b>{a.type}</b> · {a.created_at.slice(0, 16).replace("T", " ")} UTC</span><span className="flex items-center gap-2"><Badge tone={a.status === "completed" ? "good" : a.status === "cancelled" ? "muted" : "warn"}>{a.status.replace(/_/g, " ")}</Badge>{["open", "accepted"].includes(a.status) && <button className="btn-ghost py-1" onClick={() => cancel(a.id)}>Cancel</button>}</span></div>
              {a.ambulance && <p className="text-slate-600">Ambulance: {a.ambulance.name} {a.ambulance.phone && <a className="underline" href={`tel:${a.ambulance.phone}`}>{a.ambulance.phone}</a>} {a.ambulance_loc?.eta_min != null && `· ETA ~${a.ambulance_loc.eta_min} min`}</p>}
              {a.hospital && <p className="text-slate-500">Suggested hospital: {a.hospital.name}</p>}
            </li>
          ))}
        </ul>
      </Card>
      <Card title="Emergency numbers (India)"><ul className="grid gap-1 text-sm md:grid-cols-2">{dir.map((d) => <li key={d.number}>{d.name}: <a className="font-semibold text-brand-700 underline" href={`tel:${d.number}`}>{d.number}</a></li>)}</ul></Card>
    </>
  );
}
