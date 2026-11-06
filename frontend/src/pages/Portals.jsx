// Workspaces for professional roles: pharmacist, ambulance, hospital, lab, blood bank, admin.
import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Alert, Badge, Card, Empty, Field, Stat, textToList, toneFor, useAsync } from "../components/ui.jsx";

const q = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== "" && v != null)).toString();
const Pending = () => {
  const { user } = useAuth();
  return user.approved === false ? <Alert tone="warn">Your account is waiting for admin verification. Some actions stay locked until then.</Alert> : null;
};

/* ---------------- Pharmacist ---------------- */
function ShareLocation({ oid }) {
  const [on, setOn] = useState(false);
  const [msg, setMsg] = useState("");
  const id = useRef(null);
  const last = useRef(0);
  const stop = () => { if (id.current != null) navigator.geolocation.clearWatch(id.current); id.current = null; setOn(false); };
  useEffect(() => stop, []); // eslint-disable-line
  const start = () => {
    if (!navigator.geolocation) { setMsg("Location is not supported on this device."); return; }
    id.current = navigator.geolocation.watchPosition(async (p) => {
      if (Date.now() - last.current < 10000) return; last.current = Date.now();
      try { await api(`/pharmacy/orders/${oid}/location`, { method: "POST", body: { lat: p.coords.latitude, lng: p.coords.longitude } }); setMsg("Sharing live location"); } catch (e) { setMsg(e.message); }
    }, () => { setMsg("Location permission denied."); stop(); }, { enableHighAccuracy: true });
    setOn(true);
  };
  return <span className="flex items-center gap-2"><button className={on ? "btn-danger py-0.5 text-xs" : "btn-ghost py-0.5 text-xs"} onClick={on ? stop : start}>{on ? "Stop sharing location" : "Share delivery location"}</button>{msg && <span className="text-xs text-slate-500">{msg}</span>}</span>;
}

export function PharmacistHome() {
  const [code, setCode] = useState("");
  const [rx, setRx] = useState(null);
  const [orders, setOrders] = useState([]);
  const [inv, setInv] = useState([]);
  const [alerts, setAlerts] = useState({ low_stock: [], expiring: [] });
  const [s, setS] = useState({ name: "", quantity: "", price: "", expiry: "" });
  const { busy, error, run } = useAsync();
  const load = () => run(async () => { setOrders(await api("/pharmacy/orders")); setInv(await api("/pharmacy/inventory")); setAlerts(await api("/pharmacy/alerts")); });
  useEffect(() => { load(); }, []);
  const verify = (e) => { e.preventDefault(); run(async () => setRx(await api(`/prescriptions/verify/${encodeURIComponent(code.trim())}`))); };
  const setStatus = (id, status) => run(async () => {
    let otp = "";
    if (status === "delivered") { otp = window.prompt("Enter the 4-digit delivery code shown in the patient's app:") || ""; if (!otp) return; }
    await api(`/pharmacy/orders/${id}?${q({ status, otp })}`, { method: "PATCH" }); load();
  });
  const setPrice = (id) => { const a = window.prompt("Order total in ₹ (incl. delivery):"); if (a) run(async () => { await api(`/pharmacy/orders/${id}/quote?${q({ amount: a })}`, { method: "PATCH" }); load(); }); };
  const decide = (id, decision) => run(async () => { await api(`/pharmacy/orders/${id}/payment?${q({ decision })}`, { method: "POST" }); load(); });
  const [prof, setProf] = useState({ name: "", city: "", address: "", phone: "", upi_id: "" });
  const [profOk, setProfOk] = useState("");
  useEffect(() => { api("/pharmacy/profile").then((p) => p && setProf({ name: p.name || "", city: p.city || "", address: p.address || "", phone: p.phone || "", upi_id: p.upi_id || "" })).catch(() => {}); }, []);
  const saveProf = (e) => { e.preventDefault(); run(async () => { await api("/pharmacy/profile", { method: "PUT", body: { ...prof, upi_id: prof.upi_id || null } }); setProfOk("Saved. Patients can now find and pay your pharmacy."); load(); }); };
  const saveStock = (e) => {
    e.preventDefault();
    run(async () => { await api("/pharmacy/inventory", { method: "PUT", body: { name: s.name, quantity: +s.quantity, price: +s.price || 0, ...(s.expiry ? { expiry: s.expiry } : {}) } }); setS({ name: "", quantity: "", price: "", expiry: "" }); load(); });
  };
  return (
    <>
      <h1 className="text-xl font-bold">Pharmacy</h1><Pending /><Alert tone="error">{error}</Alert>
      <Card title="Verify QR / prescription code">
        <form onSubmit={verify} className="flex gap-2"><input className="input" placeholder="Prescription code" value={code} onChange={(e) => setCode(e.target.value)} required /><button className="btn-primary" disabled={busy}>Verify</button></form>
        {rx && (rx.valid ? <div className="mt-3 text-sm"><Badge tone="good">valid</Badge> Dr. {rx.doctor} · issued {rx.issued}<ul className="mt-1">{rx.items.map((i, n) => <li key={n}>• {i.name} {i.dose}</li>)}</ul></div> : <div className="mt-3"><Badge tone="bad">invalid or tampered code</Badge></div>)}
      </Card>
      <Card title="Pharmacy profile & UPI">
        <form onSubmit={saveProf} className="grid gap-2 sm:grid-cols-2">
          <Field label="Pharmacy name"><input className="input" required value={prof.name} onChange={(e) => setProf({ ...prof, name: e.target.value })} /></Field>
          <Field label="City"><input className="input" value={prof.city} onChange={(e) => setProf({ ...prof, city: e.target.value })} /></Field>
          <Field label="Address"><input className="input" value={prof.address} onChange={(e) => setProf({ ...prof, address: e.target.value })} /></Field>
          <Field label="Phone"><input className="input" value={prof.phone} onChange={(e) => setProf({ ...prof, phone: e.target.value })} /></Field>
          <Field label="UPI ID for payments (e.g. shop@okhdfcbank)"><input className="input" value={prof.upi_id} onChange={(e) => setProf({ ...prof, upi_id: e.target.value.trim() })} /></Field>
          <div className="flex items-end"><button className="btn-primary">Save</button></div>
        </form>
        <div className="mt-2"><Alert tone="ok">{profOk}</Alert></div>
        <p className="mt-2 text-xs text-slate-500">Payments go straight from the patient to this UPI ID. The app does not see your bank, so you confirm each payment yourself after checking your UPI app.</p>
      </Card>
      <Card title="Medicine orders">
        {orders.length === 0 && <Empty>No orders.</Empty>}
        <ul className="divide-y divide-slate-100 text-sm">
          {orders.map((o) => { const p = o.payment || {}; return (
            <li key={o.id} className="space-y-2 py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span><b>{o.patient_name}</b> · {o.items.map((i) => `${i.name}×${i.qty}`).join(", ")} · {o.address}</span>
                <Badge tone={o.status === "delivered" ? "good" : "info"}>{o.status.replace(/_/g, " ")}</Badge>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <Badge tone={p.status === "paid" ? "good" : p.status === "submitted" ? "info" : "warn"}>{p.method === "cod" ? "COD" : "UPI"} · {p.status}</Badge>
                {p.amount != null ? <b>₹{p.amount}</b> : <span className="text-amber-700">price not set</span>}
                {!["paid", "submitted"].includes(p.status) && !["delivered", "rejected"].includes(o.status) && <button className="btn-ghost py-0.5 text-xs" onClick={() => setPrice(o.id)}>{p.amount != null ? "Change price" : "Set price"}</button>}
                {p.status === "submitted" && <>UTR <b>{p.utr}</b><button className="btn-primary py-0.5 text-xs" onClick={() => decide(o.id, "confirm")}>Money received</button><button className="btn-ghost py-0.5 text-xs" onClick={() => decide(o.id, "reject")}>Not received</button></>}
                {o.status === "out_for_delivery" && <ShareLocation oid={o.id} />}
                {!["delivered", "rejected"].includes(o.status) && <select className="input ml-auto w-auto py-1" value="" onChange={(e) => e.target.value && setStatus(o.id, e.target.value)}><option value="">Update…</option>{["accepted", "packed", "out_for_delivery", "delivered", "rejected"].map((x) => <option key={x} value={x}>{x.replace(/_/g, " ")}</option>)}</select>}
              </div>
            </li>); })}
        </ul>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Inventory">
          <form onSubmit={saveStock} className="grid grid-cols-2 gap-2">
            <Field label="Medicine"><input className="input" required value={s.name} onChange={(e) => setS({ ...s, name: e.target.value })} /></Field>
            <Field label="Quantity"><input className="input" type="number" min="0" required value={s.quantity} onChange={(e) => setS({ ...s, quantity: e.target.value })} /></Field>
            <Field label="Price"><input className="input" type="number" min="0" value={s.price} onChange={(e) => setS({ ...s, price: e.target.value })} /></Field>
            <Field label="Expiry"><input className="input" type="date" value={s.expiry} onChange={(e) => setS({ ...s, expiry: e.target.value })} /></Field>
            <div className="col-span-2"><button className="btn-primary">Save stock</button></div>
          </form>
          <ul className="mt-3 divide-y divide-slate-100 text-sm">{inv.map((i) => <li key={i.name} className="flex justify-between py-1"><span className="capitalize">{i.name}</span><span>{i.quantity} {i.expiry && <span className="text-xs text-slate-400">exp {i.expiry}</span>}</span></li>)}</ul>
        </Card>
        <Card title="Alerts">
          {alerts.low_stock.length + alerts.expiring.length === 0 && <Empty>No stock alerts.</Empty>}
          {alerts.low_stock.map((i) => <p key={i.name} className="text-sm"><Badge tone="warn">low</Badge> {i.name}: {i.quantity} left</p>)}
          {alerts.expiring.map((i) => <p key={i.name} className="text-sm"><Badge tone="bad">expiry</Badge> {i.name}: {i.expiry}</p>)}
        </Card>
      </div>
    </>
  );
}

/* ---------------- Ambulance ---------------- */
const NEXT = { open: "accepted", accepted: "en_route", en_route: "arrived", arrived: "transporting", transporting: "completed" };
export function AmbulanceHome() {
  const { user } = useAuth();
  const [alerts, setAlerts] = useState([]);
  const { error, run } = useAsync();
  const load = () => run(async () => setAlerts(await api("/emergency/alerts")));
  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t); }, []);
  const setStatus = (id, status) => run(async () => { await api(`/emergency/alerts/${id}?${q({ status })}`, { method: "PATCH" }); load(); });
  const share = (id) => navigator.geolocation?.getCurrentPosition((p) => run(async () => { await api(`/emergency/alerts/${id}/location`, { method: "POST", body: { lat: p.coords.latitude, lon: p.coords.longitude } }); load(); }));
  return (
    <>
      <h1 className="text-xl font-bold">Emergency requests</h1><Pending /><Alert tone="error">{error}</Alert>
      {alerts.length === 0 && <Card><Empty>No open emergencies right now. This page refreshes every 10 seconds.</Empty></Card>}
      {alerts.map((a) => (
        <Card key={a.id}>
          <div className="flex flex-wrap items-start justify-between gap-3 text-sm">
            <div className="space-y-0.5">
              <p><b>{a.patient_name}</b> · {a.type} · <Badge tone={a.status === "open" ? "bad" : a.status === "completed" ? "good" : "warn"}>{a.status.replace(/_/g, " ")}</Badge></p>
              <p className="text-slate-600">Blood {a.blood_group || "?"} · Allergies: {a.allergies.join(", ") || "none"} · Conditions: {a.conditions.join(", ") || "none"}</p>
              <p className="text-slate-500">{a.phone && <a className="underline" href={`tel:${a.phone}`}>{a.phone}</a>} {a.lat != null && <> · <a className="text-brand-700 underline" target="_blank" rel="noreferrer" href={`https://www.google.com/maps?q=${a.lat},${a.lon}`}>map</a></>} · {a.created_at.replace("T", " ").slice(0, 16)} UTC</p>
              {a.hospital && <p className="text-slate-500">Nearest ready hospital: {a.hospital.name} ({a.hospital.distance_km} km, ~{a.hospital.eta_min} min)</p>}
              {a.ambulance_loc?.eta_min != null && <p className="text-slate-500">Ambulance ETA ~{a.ambulance_loc.eta_min} min</p>}
            </div>
            {user.role === "ambulance" && (
              <div className="flex flex-wrap gap-2">
                {NEXT[a.status] && <button className="btn-primary py-1" onClick={() => setStatus(a.id, NEXT[a.status])}>{NEXT[a.status].replace(/_/g, " ")}</button>}
                {a.ambulance?.user_id === user.id && !["completed", "cancelled"].includes(a.status) && <button className="btn-ghost py-1" onClick={() => share(a.id)}>Share my location</button>}
              </div>
            )}
          </div>
        </Card>
      ))}
    </>
  );
}

/* ---------------- Hospital ---------------- */
const WARDS = ["general", "icu", "emergency", "ventilator"];
export function HospitalHome() {
  const [h, setH] = useState(null);
  const [beds, setBeds] = useState({});
  const [adm, setAdm] = useState([]);
  const [bills, setBills] = useState([]);
  const [an, setAn] = useState(null);
  const [dept, setDept] = useState("OPD");
  const [serving, setServing] = useState(null);
  const [a, setA] = useState({ patient_name: "", health_id: "", ward: "general", doctor: "", reason: "" });
  const [b, setB] = useState({ patient_name: "", items: "Consultation:500" });
  const [prof, setProf] = useState({ address: "", city: "", phone: "", lat: "", lon: "", departments: "", specialities: "" });
  const { busy, error, run } = useAsync();
  const load = () => run(async () => {
    const me = await api("/hospitals/me"); setH(me);
    setBeds(Object.fromEntries(WARDS.map((w) => [w, [me.beds[w].total, me.beds[w].available]])));
    setProf({ address: me.address, city: me.city, phone: me.phone, lat: me.lat, lon: me.lon, departments: me.departments.join(", "), specialities: me.specialities.join(", ") });
    setAdm(await api("/hospitals/me/admissions")); setBills(await api("/hospitals/me/bills")); setAn(await api("/hospitals/me/analytics"));
  });
  useEffect(() => { load(); }, []);
  const saveBeds = () => run(async () => { await api("/hospitals/me/beds", { method: "PUT", body: beds }); load(); });
  const saveProf = (e) => { e.preventDefault(); run(async () => { await api("/hospitals/me", { method: "PUT", body: { address: prof.address, city: prof.city, phone: prof.phone, lat: +prof.lat || 0, lon: +prof.lon || 0, departments: textToList(prof.departments), specialities: textToList(prof.specialities) } }); load(); }); };
  const admit = (e) => { e.preventDefault(); run(async () => { await api("/hospitals/me/admissions", { method: "POST", body: { ...a, health_id: a.health_id || null } }); setA({ ...a, patient_name: "", health_id: "", reason: "" }); load(); }); };
  const discharge = (id) => run(async () => { await api(`/hospitals/me/admissions/${id}/discharge`, { method: "POST" }); load(); });
  const bill = (e) => {
    e.preventDefault();
    const items = b.items.split(",").map((x) => x.split(":")).map(([name, amount]) => ({ name: (name || "").trim(), amount: +amount || 0 }));
    run(async () => { await api("/hospitals/me/bills", { method: "POST", body: { patient_name: b.patient_name, items } }); setB({ ...b, patient_name: "" }); load(); });
  };
  const pay = (id) => run(async () => { await api(`/hospitals/me/bills/${id}`, { method: "PATCH" }); load(); });
  const next = () => run(async () => { const r = await api(`/hospitals/me/queue/next?${q({ department: dept })}`, { method: "POST" }); setServing(r.now_serving); });
  return (
    <>
      <h1 className="text-xl font-bold">{h?.name || "Hospital"}</h1><Pending /><Alert tone="error">{error}</Alert>
      {an && <div className="grid grid-cols-2 gap-4 md:grid-cols-4"><Stat label="Active admissions" value={an.active_admissions} /><Stat label="Occupancy %" value={an.occupancy_pct} /><Stat label="Revenue (paid)" value={an.revenue_total} /><Stat label="Bed demand (est.)" value={an.bed_demand_estimate} /></div>}
      <Card title="Bed availability (total / available)" action={<button className="btn-primary py-1" onClick={saveBeds} disabled={busy}>Save</button>}>
        <div className="grid gap-3 md:grid-cols-4">
          {WARDS.map((w) => beds[w] && (
            <div key={w}><span className="label">{w}</span><div className="flex gap-2">
              <input className="input" type="number" min="0" value={beds[w][0]} onChange={(e) => setBeds({ ...beds, [w]: [+e.target.value, beds[w][1]] })} />
              <input className="input" type="number" min="0" value={beds[w][1]} onChange={(e) => setBeds({ ...beds, [w]: [beds[w][0], +e.target.value] })} /></div></div>
          ))}
        </div>
      </Card>
      <Card title="Admissions">
        <form onSubmit={admit} className="grid gap-2 md:grid-cols-6">
          <input className="input md:col-span-2" placeholder="Patient name" required value={a.patient_name} onChange={(e) => setA({ ...a, patient_name: e.target.value })} />
          <input className="input" placeholder="Health ID (opt.)" value={a.health_id} onChange={(e) => setA({ ...a, health_id: e.target.value })} />
          <select className="input" value={a.ward} onChange={(e) => setA({ ...a, ward: e.target.value })}>{WARDS.map((w) => <option key={w}>{w}</option>)}</select>
          <input className="input" placeholder="Doctor" value={a.doctor} onChange={(e) => setA({ ...a, doctor: e.target.value })} />
          <button className="btn-primary" disabled={busy}>Admit</button>
        </form>
        <ul className="mt-3 divide-y divide-slate-100 text-sm">
          {adm.slice(0, 20).map((x) => <li key={x.id} className="flex items-center justify-between py-1.5"><span><b>{x.patient_name}</b> · {x.ward} · {x.admitted_at.slice(0, 10)}</span>{x.status === "admitted" ? <button className="btn-ghost py-1" onClick={() => discharge(x.id)}>Discharge</button> : <Badge>discharged</Badge>}</li>)}
        </ul>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Billing">
          <form onSubmit={bill} className="space-y-2"><input className="input" placeholder="Patient name" required value={b.patient_name} onChange={(e) => setB({ ...b, patient_name: e.target.value })} /><input className="input" placeholder="item:amount, item:amount" value={b.items} onChange={(e) => setB({ ...b, items: e.target.value })} /><button className="btn-primary">Create bill</button></form>
          <ul className="mt-3 divide-y divide-slate-100 text-sm">{bills.slice(0, 10).map((x) => <li key={x.id} className="flex items-center justify-between py-1.5"><span>{x.patient_name} · ₹{x.total}</span>{x.status === "paid" ? <Badge tone="good">paid</Badge> : <button className="btn-ghost py-1" onClick={() => pay(x.id)}>Mark paid</button>}</li>)}</ul>
        </Card>
        <Card title="OPD token queue">
          <div className="flex gap-2"><select className="input" value={dept} onChange={(e) => setDept(e.target.value)}>{(h?.departments || ["OPD"]).map((d) => <option key={d}>{d}</option>)}</select><button className="btn-primary" onClick={next}>Call next</button></div>
          {serving !== null && <p className="mt-3 text-2xl font-bold text-brand-700">Now serving: {serving ?? "queue empty"}</p>}
        </Card>
      </div>
      <Card title="Hospital profile">
        <form onSubmit={saveProf} className="grid gap-3 md:grid-cols-3">
          {[["address", "Address"], ["city", "City"], ["phone", "Phone"], ["lat", "Latitude"], ["lon", "Longitude"], ["departments", "Departments (comma)"], ["specialities", "Specialities (comma)"]].map(([k, l]) => <Field key={k} label={l}><input className="input" value={prof[k]} onChange={(e) => setProf({ ...prof, [k]: e.target.value })} /></Field>)}
          <div className="flex items-end"><button className="btn-primary">Save profile</button></div>
        </form>
        <p className="mt-2 text-xs text-slate-500">Latitude/longitude power nearest-hospital search and ambulance routing.</p>
      </Card>
    </>
  );
}

/* ---------------- Laboratory ---------------- */
export function LabHome() {
  const [rows, setRows] = useState([]);
  const [an, setAn] = useState(null);
  const [open, setOpen] = useState(null);
  const [text, setText] = useState("");
  const { error, run } = useAsync();
  const load = () => run(async () => { setRows(await api("/labs/bookings")); setAn(await api("/labs/analytics")); });
  useEffect(() => { load(); }, []);
  const status = (id, s) => run(async () => { await api(`/labs/bookings/${id}/status?${q({ status: s })}`, { method: "PATCH" }); load(); });
  const result = (id) => run(async () => { await api(`/labs/bookings/${id}/result`, { method: "POST", body: { text } }); setOpen(null); setText(""); load(); });
  const verify = (id) => run(async () => { await api(`/labs/bookings/${id}/verify`, { method: "POST" }); load(); });
  return (
    <>
      <h1 className="text-xl font-bold">Laboratory</h1><Pending /><Alert tone="error">{error}</Alert>
      {an && <div className="grid grid-cols-2 gap-4 md:grid-cols-4"><Stat label="Bookings" value={an.bookings} /><Stat label="Booked" value={an.by_status.booked} /><Stat label="Completed" value={an.by_status.completed} /><Stat label="Revenue" value={an.revenue} /></div>}
      <Card title="Test bookings">
        {rows.length === 0 && <Empty>No bookings yet.</Empty>}
        <ul className="divide-y divide-slate-100 text-sm">
          {rows.map((b) => (
            <li key={b.id} className="space-y-2 py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span><b>{b.patient_name}</b> · {b.tests.map((t) => t.name).join(", ")} · {b.home_collection ? `home: ${b.address}` : "walk-in"} {b.slot && `· ${b.slot}`}</span>
                <span className="flex flex-wrap items-center gap-2"><Badge tone={toneFor(b.status === "completed" ? "good" : "info")}>{b.status.replace(/_/g, " ")}</Badge>{b.verified && <Badge tone="good">verified</Badge>}
                  {b.status === "booked" && <button className="btn-ghost py-1" onClick={() => status(b.id, "sample_collected")}>Sample collected</button>}
                  {b.status === "sample_collected" && <button className="btn-ghost py-1" onClick={() => status(b.id, "processing")}>Processing</button>}
                  {["sample_collected", "processing"].includes(b.status) && <button className="btn-primary py-1" onClick={() => setOpen(b.id)}>Enter results</button>}
                  {b.report_id && !b.verified && <button className="btn-primary py-1" onClick={() => verify(b.id)}>Verify & release</button>}</span>
              </div>
              {open === b.id && <div className="space-y-2 rounded-lg bg-slate-50 p-3"><textarea className="input h-24" placeholder={"Hemoglobin 13.2 g/dL\nTotal cholesterol 210 mg/dL"} value={text} onChange={(e) => setText(e.target.value)} /><button className="btn-primary" onClick={() => result(b.id)} disabled={!text.trim()}>Save results</button></div>}
            </li>
          ))}
        </ul>
      </Card>
      {an && <div className="grid gap-4 md:grid-cols-2"><Card title="Most booked tests">{an.most_booked.map(([n, c]) => <p key={n} className="text-sm">{n}: {c}</p>)}</Card><Card title="Most abnormal findings">{an.most_abnormal.length ? an.most_abnormal.map(([n, c]) => <p key={n} className="text-sm">{n}: {c}</p>) : <Empty>None.</Empty>}</Card></div>}
    </>
  );
}

/* ---------------- Blood bank ---------------- */
const BG = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"];
export function BloodBankHome() {
  const [mine, setMine] = useState({ stock: [], expiring_soon: [], low: [] });
  const [s, setS] = useState({ blood_group: "O+", units: "", expiry: "" });
  const [camp, setCamp] = useState({ title: "", date: "", venue: "", city: "" });
  const [reqs, setReqs] = useState([]);
  const [ok, setOk] = useState("");
  const { error, run } = useAsync();
  const load = () => run(async () => { setMine(await api("/blood/stock/mine")); setReqs(await api("/blood/requests")); });
  useEffect(() => { load(); }, []);
  const save = (e) => { e.preventDefault(); run(async () => { await api("/blood/stock", { method: "PUT", body: { blood_group: s.blood_group, units: +s.units, ...(s.expiry ? { expiry: s.expiry } : {}) } }); load(); }); };
  const addCamp = (e) => { e.preventDefault(); run(async () => { await api("/blood/camps", { method: "POST", body: camp }); setCamp({ title: "", date: "", venue: "", city: "" }); setOk("Camp created."); }); };
  return (
    <>
      <h1 className="text-xl font-bold">Blood bank</h1><Pending /><Alert tone="error">{error}</Alert><Alert tone="ok">{ok}</Alert>
      {mine.low.length > 0 && <Alert tone="warn">Low stock: {mine.low.map((r) => `${r.blood_group} (${r.units})`).join(", ")}</Alert>}
      {mine.expiring_soon.length > 0 && <Alert tone="warn">Expiring within 7 days: {mine.expiring_soon.map((r) => `${r.blood_group} ${r.expiry}`).join(", ")}</Alert>}
      <Card title="Stock">
        <div className="grid grid-cols-4 gap-2 md:grid-cols-8">{BG.map((g) => { const r = mine.stock.find((x) => x.blood_group === g); return <div key={g} className="rounded-lg border border-slate-200 p-2 text-center"><p className="text-xs text-slate-500">{g}</p><p className="text-xl font-bold text-brand-700">{r?.units ?? 0}</p></div>; })}</div>
        <form onSubmit={save} className="mt-4 flex flex-wrap items-end gap-2">
          <Field label="Group"><select className="input" value={s.blood_group} onChange={(e) => setS({ ...s, blood_group: e.target.value })}>{BG.map((g) => <option key={g}>{g}</option>)}</select></Field>
          <Field label="Units"><input className="input w-28" type="number" min="0" required value={s.units} onChange={(e) => setS({ ...s, units: e.target.value })} /></Field>
          <Field label="Earliest expiry"><input className="input" type="date" value={s.expiry} onChange={(e) => setS({ ...s, expiry: e.target.value })} /></Field>
          <button className="btn-primary">Update stock</button>
        </form>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Open blood requests">
          {reqs.length === 0 && <Empty>No open requests.</Empty>}
          <ul className="divide-y divide-slate-100 text-sm">{reqs.map((r) => <li key={r.id} className="py-1.5"><b>{r.blood_group}</b> ×{r.units} · {r.city} {r.hospital && `· ${r.hospital}`} <Badge tone={r.urgency === "critical" ? "bad" : "warn"}>{r.urgency}</Badge></li>)}</ul>
        </Card>
        <Card title="Organise a donation camp">
          <form onSubmit={addCamp} className="grid grid-cols-2 gap-2">
            <div className="col-span-2"><input className="input" placeholder="Title" required value={camp.title} onChange={(e) => setCamp({ ...camp, title: e.target.value })} /></div>
            <input className="input" type="date" required value={camp.date} onChange={(e) => setCamp({ ...camp, date: e.target.value })} />
            <input className="input" placeholder="City" required value={camp.city} onChange={(e) => setCamp({ ...camp, city: e.target.value })} />
            <div className="col-span-2"><input className="input" placeholder="Venue" required value={camp.venue} onChange={(e) => setCamp({ ...camp, venue: e.target.value })} /></div>
            <button className="btn-primary">Create camp</button>
          </form>
        </Card>
      </div>
    </>
  );
}

/* ---------------- Admin ---------------- */
export function AdminHome() {
  const { user } = useAuth();
  const [st, setSt] = useState(null);
  const [users, setUsers] = useState([]);
  const [role, setRole] = useState("");
  const [search, setSearch] = useState("");
  const [pendingOnly, setPendingOnly] = useState(true);
  const [logs, setLogs] = useState([]);
  const [logins, setLogins] = useState([]);
  const [msg, setMsg] = useState("");
  const [inbox, setInbox] = useState([]);
  const { error, run } = useAsync();
  const load = () => run(async () => {
    setSt(await api("/admin/stats"));
    setInbox(await api("/contact/admin"));
    setUsers(await api(`/admin/users?${q({ role, q: search, pending: pendingOnly ? "true" : "" })}`));
    setLogs(await api("/admin/audit-logs?limit=25")); setLogins(await api("/admin/login-history"));
  });
  useEffect(() => { load(); }, [role, pendingOnly]);
  const upd = (id, p) => run(async () => { await api(`/admin/users/${id}?${q(p)}`, { method: "PATCH" }); load(); });
  const del = (u) => confirm(`Permanently delete ${u.name} (${u.email})? Their profile, records, documents and orders are removed. This cannot be undone.`) && run(async () => { await api(`/admin/users/${u.id}`, { method: "DELETE" }); setMsg(`Deleted ${u.email}`); load(); });
  const resolve = (id, status) => run(async () => { await api(`/contact/admin/${id}?${q({ status })}`, { method: "PATCH" }); load(); });
  const backup = () => run(async () => { const r = await api("/admin/backup", { method: "POST" }); setMsg(`Backup written to ${r.folder}`); });
  const mkAdmin = () => { const email = prompt("Email of the user to promote to admin"); email && run(async () => { await api(`/admin/admins?${q({ email })}`, { method: "POST" }); setMsg("Promoted."); load(); }); };
  return (
    <>
      <h1 className="text-xl font-bold">{user.role === "super_admin" ? "Super admin console" : "Admin console"}</h1>
      <Alert tone="error">{error}</Alert><Alert tone="ok">{msg}</Alert>
      {st && <div className="grid grid-cols-2 gap-4 md:grid-cols-4"><Stat label="Users" value={st.users} /><Stat label="Pending approvals" value={st.pending_approvals} /><Stat label="Open emergencies" value={st.open_emergencies} /><Stat label="Suspicious logins" value={st.suspicious_logins} /><Stat label="Appointments" value={st.appointments} /><Stat label="Reports analysed" value={st.reports} /><Stat label="Vitals readings" value={st.vitals_readings} /></div>}
      <Card title="Users & verification" action={user.role === "super_admin" && <span className="flex gap-2"><button className="btn-ghost py-1" onClick={mkAdmin}>Make admin</button><button className="btn-ghost py-1" onClick={backup}>Backup</button></span>}>
        <div className="mb-3 flex flex-wrap items-end gap-2">
          <Field label="Role"><select className="input" value={role} onChange={(e) => setRole(e.target.value)}><option value="">All</option>{["patient", "doctor", "hospital", "lab", "pharmacist", "blood_bank", "ambulance", "family", "admin"].map((r) => <option key={r} value={r}>{r}</option>)}</select></Field>
          <Field label="Search"><input className="input" value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()} /></Field>
          <label className="flex items-center gap-1 pb-2 text-sm"><input type="checkbox" checked={pendingOnly} onChange={(e) => setPendingOnly(e.target.checked)} />Pending only</label>
          <button className="btn-ghost" onClick={load}>Search</button>
        </div>
        {users.length === 0 && <Empty>No users match.</Empty>}
        <ul className="divide-y divide-slate-100 text-sm">
          {users.map((u) => (
            <li key={u.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span><b>{u.name}</b> · {u.email} · <Badge>{u.role}</Badge> {u.license_no && <span className="text-xs text-slate-500">licence {u.license_no}</span>} {u.status === "suspended" && <Badge tone="bad">suspended</Badge>}</span>
              <span className="flex gap-2">
                {!u.approved && <button className="btn-primary py-1" onClick={() => upd(u.id, { approved: "true" })}>Verify</button>}
                {u.approved && ["doctor", "hospital", "lab", "pharmacist", "blood_bank", "ambulance"].includes(u.role) && <button className="btn-ghost py-1" onClick={() => upd(u.id, { approved: "false" })}>Revoke</button>}
                {u.status === "suspended" ? <button className="btn-ghost py-1" onClick={() => upd(u.id, { suspended: "false" })}>Reinstate</button> : <button className="btn-ghost py-1" onClick={() => upd(u.id, { suspended: "true" })}>Suspend</button>}
                {u.role !== "super_admin" && u.id !== user.id && (u.role !== "admin" || user.role === "super_admin") && <button className="btn-ghost py-1 text-red-700" onClick={() => del(u)}>Delete</button>}
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-slate-500">Check licence numbers with the relevant council or authority before verifying.</p>
      </Card>
      <Card title={`Contact messages (${inbox.filter((m) => m.status === "open").length} open)`}>
        {inbox.length === 0 && <Empty>No messages yet.</Empty>}
        <ul className="divide-y divide-slate-100 text-sm">
          {inbox.map((m) => (
            <li key={m.id} className="space-y-1 py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span><b>{m.subject}</b> <Badge>{m.category}</Badge> <Badge tone={m.status === "open" ? "warn" : "good"}>{m.status}</Badge></span>
                <span className="flex gap-2"><a className="btn-ghost py-1" href={`mailto:${m.email}?subject=${encodeURIComponent("Re: " + m.subject)}`}>Reply</a>
                  {m.status === "open" ? <button className="btn-primary py-1" onClick={() => resolve(m.id, "resolved")}>Mark resolved</button> : <button className="btn-ghost py-1" onClick={() => resolve(m.id, "open")}>Reopen</button>}</span>
              </div>
              <p className="whitespace-pre-wrap text-slate-700">{m.message}</p>
              <p className="text-xs text-slate-500">{m.name} · {m.email} · {m.ts.slice(0, 16).replace("T", " ")}</p>
            </li>
          ))}
        </ul>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Audit log"><ul className="space-y-1 text-xs text-slate-600">{logs.map((l) => <li key={l.id}>{l.ts.slice(5, 19).replace("T", " ")} · {l.action} {l.detail}</li>)}</ul></Card>
        <Card title="Login history"><ul className="space-y-1 text-xs text-slate-600">{logins.slice(0, 25).map((l) => <li key={l.id}>{l.ts.slice(5, 16).replace("T", " ")} · {l.ip || "?"} · {l.success ? "ok" : <span className="text-red-600">failed</span>}</li>)}</ul></Card>
      </div>
    </>
  );
}
