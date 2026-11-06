import { useEffect, useState } from "react";
import { api } from "../api.js";
import RxOrder from "../components/RxOrder.jsx";
import { useSearchParams } from "react-router-dom";
import { PatientOrder } from "../components/OrderPay.jsx";
import { Alert, Badge, Card, Disclaimer, Field, textToList, toneFor, useAsync } from "../components/ui.jsx";

const blank = { name: "", dose: "", times: "08:00", duration_days: 7, stock: "", expiry: "", instructions: "" };

export default function Medicines() {
  const [sched, setSched] = useState({ schedule: [], adherence: null });
  const [meds, setMeds] = useState([]);
  const [rxs, setRxs] = useState([]);
  const [rxOrder, setRxOrder] = useState(null);
  const [sp] = useSearchParams();
  const [alerts, setAlerts] = useState([]);
  const [adh, setAdh] = useState([]);
  const [f, setF] = useState(blank);
  const [warn, setWarn] = useState([]);
  const [info, setInfo] = useState(null);
  const [q, setQ] = useState("");
  const [pharm, setPharm] = useState([]);
  const [orders, setOrders] = useState([]);
  const [order, setOrder] = useState({ pharmacy_id: "", items: "", address: "", payment_method: "upi" });
  const [ocr, setOcr] = useState(null);
  const { busy, error, run } = useAsync();

  const load = () =>
    run(async () => {
      setSched(await api("/medicines/today"));
      setMeds(await api("/medicines"));
      setRxs(await api("/prescriptions"));
      setAlerts(await api("/medicines/alerts"));
      setAdh(await api("/medicines/history/adherence"));
      setPharm(await api("/pharmacies"));
      setOrders(await api("/medicines/orders"));
    });
  useEffect(() => { load(); }, []);

  const take = (d) => run(async () => { await api(`/medicines/${d.med_id}/taken`, { method: "POST", body: { time: d.time } }); load(); });
  const add = (e) => {
    e.preventDefault();
    run(async () => {
      const body = { name: f.name, dose: f.dose, times: textToList(f.times), duration_days: +f.duration_days, instructions: f.instructions };
      if (f.stock !== "") body.stock = +f.stock;
      if (f.expiry) body.expiry = f.expiry;
      const r = await api("/medicines", { method: "POST", body });
      setWarn(r.warnings || []); setF(blank); load();
    });
  };
  useEffect(() => { const id = sp.get("rx"); const r = rxs.find((x) => x.id === id); if (r && !rxOrder) setRxOrder({ id: r.id, names: r.items.map((i) => i.name) }); }, [rxs]); // eslint-disable-line
  const stop = (id) => run(async () => { await api(`/medicines/${id}`, { method: "DELETE" }); load(); });
  const lookup = (e) => { e.preventDefault(); run(async () => setInfo(await api(`/medicines/info/${encodeURIComponent(q)}`))); };
  const importRx = (id) => run(async () => { await api(`/prescriptions/${id}/import`, { method: "POST" }); load(); });
  const readRx = (file) => { const form = new FormData(); form.append("file", file); run(async () => setOcr(await api("/prescriptions/read", { method: "POST", form }))); };
  const place = (e) => {
    e.preventDefault();
    run(async () => {
      await api("/medicines/orders", { method: "POST", body: { pharmacy_id: order.pharmacy_id, address: order.address, payment_method: order.payment_method, items: textToList(order.items).map((n) => ({ name: n, qty: 1 })) } });
      setOrder({ ...order, items: "" }); load();
    });
  };

  return (
    <>
      <h1 className="text-xl font-bold">Medicines</h1>
      <Alert tone="error">{error}</Alert>
      {alerts.map((a, i) => <Alert key={i} tone={a.type === "missed" ? "error" : "warn"}>{a.message}</Alert>)}
      {warn.map((w, i) => <Alert key={i} tone="warn">{w.message || String(w)}</Alert>)}

      <Card title="Today's doses" action={sched.adherence != null && <Badge tone={sched.adherence >= 80 ? "good" : "warn"}>{sched.adherence}% taken</Badge>}>
        {sched.schedule.length === 0 && <p className="text-sm text-slate-500">No doses scheduled today.</p>}
        <ul className="divide-y divide-slate-100 text-sm">
          {sched.schedule.map((d) => (
            <li key={`${d.med_id}${d.time}`} className="flex items-center justify-between py-2">
              <span><b>{d.time}</b> · {d.name} {d.dose} {d.instructions && <span className="text-slate-500">· {d.instructions}</span>}</span>
              {d.status === "taken" ? <Badge tone="good">taken</Badge> : <span className="flex items-center gap-2"><Badge tone={toneFor(d.status)}>{d.status}</Badge><button className="btn-ghost py-1" onClick={() => take(d)}>Mark taken</button></span>}
            </li>
          ))}
        </ul>
        {adh.length > 0 && <p className="mt-3 text-xs text-slate-500">Last 14 days: {adh.map((a) => `${a.date.slice(5)}: ${a.doses_taken}`).join(" · ")}</p>}
      </Card>

      <Card title="Add a medicine (interaction & allergy check runs automatically)">
        <form onSubmit={add} className="grid gap-3 md:grid-cols-3">
          <Field label="Name"><input className="input" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Dose"><input className="input" placeholder="500 mg" value={f.dose} onChange={(e) => setF({ ...f, dose: e.target.value })} /></Field>
          <Field label="Times (HH:MM, comma separated)"><input className="input" value={f.times} onChange={(e) => setF({ ...f, times: e.target.value })} /></Field>
          <Field label="Days"><input className="input" type="number" min="1" value={f.duration_days} onChange={(e) => setF({ ...f, duration_days: e.target.value })} /></Field>
          <Field label="Stock (doses left)"><input className="input" type="number" min="0" value={f.stock} onChange={(e) => setF({ ...f, stock: e.target.value })} /></Field>
          <Field label="Expiry"><input className="input" type="date" value={f.expiry} onChange={(e) => setF({ ...f, expiry: e.target.value })} /></Field>
          <div className="md:col-span-2"><Field label="Instructions"><input className="input" value={f.instructions} onChange={(e) => setF({ ...f, instructions: e.target.value })} /></Field></div>
          <div className="flex items-end"><button className="btn-primary w-full" disabled={busy}>Add</button></div>
        </form>
      </Card>

      <Card title="My active medicines">
        {meds.length === 0 && <p className="text-sm text-slate-500">None.</p>}
        <ul className="divide-y divide-slate-100 text-sm">
          {meds.map((m) => (
            <li key={m.id} className="flex items-center justify-between py-2">
              <span><b>{m.name}</b> {m.dose} · {m.times.join(", ")} · until {m.end_date}{m.stock != null && ` · ${m.stock} left`}</span>
              <button className="btn-ghost py-1" onClick={() => stop(m.id)}>Stop</button>
            </li>
          ))}
        </ul>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Medicine information">
          <form onSubmit={lookup} className="flex gap-2"><input className="input" placeholder="e.g. paracetamol" value={q} onChange={(e) => setQ(e.target.value)} required /><button className="btn-primary">Search</button></form>
          {info && <div className="mt-3 space-y-1 text-sm">{Object.entries(info).map(([k, v]) => <p key={k}><b className="capitalize">{k.replace(/_/g, " ")}:</b> {Array.isArray(v) ? v.join(", ") : typeof v === "object" ? JSON.stringify(v) : String(v)}</p>)}</div>}
        </Card>
        <Card title="Read a prescription photo (OCR)">
          <input className="input" type="file" accept="image/*" onChange={(e) => e.target.files[0] && readRx(e.target.files[0])} />
          {ocr && <div className="mt-2 text-sm"><p>{ocr.medicines_detected.length ? ocr.medicines_detected.map((m) => `${m.name} ${m.dose}`).join(", ") : "No known medicines detected."}</p><p className="text-xs text-slate-500">{ocr.note}</p></div>}
        </Card>
      </div>

      <Card title="Prescriptions from my doctors">
        {rxs.length === 0 && <p className="text-sm text-slate-500">None yet.</p>}
        {rxs.map((r) => (
          <div key={r.id} className="border-b border-slate-100 py-2 text-sm last:border-0">
            <div className="flex items-center justify-between">
              <span><b>{r.code}</b> · Dr. {r.doctor_name} · {r.created_at.slice(0, 10)} {r.diagnosis && `· ${r.diagnosis}`}</span>
              <span className="flex items-center gap-2">{r.ordered ? <Badge tone="good">ordered</Badge> : <button className="btn-primary py-1" onClick={() => setRxOrder({ id: r.id, names: r.items.map((i) => i.name) })}>Order medicines</button>}
              {r.imported ? <Badge tone="good">in my schedule</Badge> : <button className="btn-ghost py-1" onClick={() => importRx(r.id)}>Add to schedule</button>}</span>
            </div>
            {rxOrder?.id === r.id && <div className="my-2"><RxOrder names={rxOrder.names} rxId={r.id} onClose={() => setRxOrder(null)} onPlaced={() => { setRxOrder(null); load(); }} /></div>}
            <p className="text-slate-600">{r.items.map((i) => `${i.name} ${i.dose}`).join(" · ")}</p>
            {r.warnings?.map((w, i) => <p key={i} className="text-xs text-amber-700">⚠ {w}</p>)}
            <p className="text-xs text-slate-400">Pharmacy verification code: {r.code}</p>
          </div>
        ))}
      </Card>

      <Card title="Order medicines">
        <form onSubmit={place} className="grid gap-3 md:grid-cols-3">
          <Field label="Pharmacy"><select className="input" required value={order.pharmacy_id} onChange={(e) => setOrder({ ...order, pharmacy_id: e.target.value })}><option value="">Choose…</option>{pharm.map((p) => <option key={p.id} value={p.id}>{p.name} {p.city && `· ${p.city}`}</option>)}</select></Field>
          <Field label="Medicines (comma separated)"><input className="input" required value={order.items} onChange={(e) => setOrder({ ...order, items: e.target.value })} /></Field>
          <Field label="Delivery address"><input className="input" required value={order.address} onChange={(e) => setOrder({ ...order, address: e.target.value })} /></Field>
          <Field label="Payment"><select className="input" value={order.payment_method} onChange={(e) => setOrder({ ...order, payment_method: e.target.value })}><option value="upi">Pay online with UPI QR</option><option value="cod">Cash on delivery</option></select></Field>
          <div><button className="btn-primary" disabled={busy}>Place order</button></div>
        </form>
        <ul className="mt-3 divide-y divide-slate-100">{orders.map((o) => <PatientOrder key={o.id} o={o} reload={load} />)}</ul>
      </Card>
      <Disclaimer />
    </>
  );
}
