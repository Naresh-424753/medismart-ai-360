import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { Alert, Badge, Card, Empty, Field, useAsync } from "../components/ui.jsx";

export default function Labs() {
  const [cat, setCat] = useState([]);
  const [pick, setPick] = useState([]);
  const [home, setHome] = useState(false);
  const [address, setAddress] = useState("");
  const [slot, setSlot] = useState("");
  const [rows, setRows] = useState([]);
  const [ok, setOk] = useState("");
  const { busy, error, run } = useAsync();
  const load = () => api("/labs/bookings").then(setRows).catch(() => {});
  useEffect(() => { api("/labs/catalog").then(setCat).catch(() => {}); load(); }, []);
  const total = cat.filter((t) => pick.includes(t.id)).reduce((s, t) => s + t.price, 0) + (home ? 100 : 0);
  const book = (e) => { e.preventDefault(); run(async () => { await api("/labs/bookings", { method: "POST", body: { test_ids: pick, home_collection: home, address, slot } }); setPick([]); setOk("Booked. We'll notify you at each step."); load(); }); };
  return (
    <>
      <h1 className="text-xl font-bold">Lab tests</h1><Alert tone="error">{error}</Alert><Alert tone="ok">{ok}</Alert>
      <Card title="Book tests or a health package">
        <form onSubmit={book} className="space-y-3">
          <div className="grid gap-1 md:grid-cols-2">{cat.map((t) => <label key={t.id} className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm"><span className="flex items-center gap-2"><input type="checkbox" checked={pick.includes(t.id)} onChange={(e) => setPick(e.target.checked ? [...pick, t.id] : pick.filter((x) => x !== t.id))} />{t.name}</span><span className="text-slate-500">₹{t.price}</span></label>)}</div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={home} onChange={(e) => setHome(e.target.checked)} />Home sample collection (+₹100)</label>
          <div className="grid gap-3 md:grid-cols-2">{home && <Field label="Address"><input className="input" required value={address} onChange={(e) => setAddress(e.target.value)} /></Field>}<Field label="Preferred slot"><input className="input" placeholder="2026-11-05 08:00-10:00" value={slot} onChange={(e) => setSlot(e.target.value)} /></Field></div>
          <button className="btn-primary" disabled={busy || !pick.length}>Book · ₹{total}</button>
        </form>
      </Card>
      <Card title="My bookings">
        {rows.length === 0 && <Empty>None yet.</Empty>}
        <ul className="divide-y divide-slate-100 text-sm">{rows.map((b) => <li key={b.id} className="flex flex-wrap items-center justify-between gap-2 py-2"><span>{b.tests.map((t) => t.name).join(", ")} · ₹{b.total} · {b.created_at.slice(0, 10)}</span><span className="flex items-center gap-2"><Badge tone={b.status === "completed" ? "good" : "info"}>{b.status.replace(/_/g, " ")}</Badge>{b.verified && <Link className="text-brand-700 underline" to="/reports">View report</Link>}</span></li>)}</ul>
      </Card>
    </>
  );
}
