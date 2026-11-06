import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Alert, Badge, Card, Empty, Field, Stat, useAsync } from "../components/ui.jsx";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const TABS = ["Overview & forecast", "Departments", "Staff", "Operation theatre", "Inventory", "Equipment"];

export default function HospitalOps() {
  const [tab, setTab] = useState(TABS[0]);
  return (
    <>
      <h1 className="text-xl font-bold">Hospital operations</h1>
      <div className="flex gap-1 overflow-x-auto border-b border-slate-200">{TABS.map((t) => <button key={t} onClick={() => setTab(t)} className={`whitespace-nowrap px-3 py-2 text-sm ${tab === t ? "border-b-2 border-brand-600 font-medium text-brand-700" : "text-slate-500"}`}>{t}</button>)}</div>
      {tab === TABS[0] && <Overview />}
      {tab === TABS[1] && <Departments />}
      {tab === TABS[2] && <Resource kind="staff" title="Staff" fields={[["name", "Name"], ["role", "Role (nurse, technician…)"], ["department", "Department"], ["phone", "Phone"], ["shift", "Shift", ["day", "evening", "night"]]]} cols={["name", "role", "department", "shift", "phone"]} />}
      {tab === TABS[3] && <Theatre />}
      {tab === TABS[4] && <Resource kind="inventory" title="Inventory" fields={[["item", "Item"], ["category", "Category"], ["quantity", "Quantity", "number"], ["unit", "Unit"], ["reorder_level", "Reorder level", "number"], ["expiry", "Expiry", "date"]]} cols={["item", "category", "quantity", "reorder_level", "expiry"]} />}
      {tab === TABS[5] && <Resource kind="equipment" title="Equipment" fields={[["name", "Name"], ["serial_no", "Serial no."], ["department", "Department"], ["status", "Status", ["working", "maintenance", "out_of_service"]], ["next_service", "Next service", "date"]]} cols={["name", "department", "status", "next_service"]} />}
    </>
  );
}

function Overview() {
  const [al, setAl] = useState(null);
  const [fc, setFc] = useState(null);
  useEffect(() => { api("/hospital-ops/alerts").then(setAl).catch(() => {}); api("/hospital-ops/forecast?days=7").then(setFc).catch(() => {}); }, []);
  return (
    <>
      {al && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Low stock items" value={al.low_stock.length} /><Stat label="Expiring in 30 days" value={al.expiring_soon.length} />
          <Stat label="Equipment not working" value={al.equipment_down.length} /><Stat label="Service due in 30 days" value={al.service_due.length} />
        </div>
      )}
      {fc && (
        <>
          <Card title="Admissions: last 28 days">
            <div className="h-56"><ResponsiveContainer><LineChart data={fc.history}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="date" tickFormatter={(d) => d.slice(5)} fontSize={11} /><YAxis allowDecimals={false} fontSize={11} /><Tooltip /><Line dataKey="admissions" stroke="#059669" dot={false} /></LineChart></ResponsiveContainer></div>
          </Card>
          <Card title="Next 7 days: expected admissions & bed demand">
            <div className="h-48"><ResponsiveContainer><BarChart data={fc.forecast}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="date" tickFormatter={(d) => d.slice(5)} fontSize={11} /><YAxis fontSize={11} /><Tooltip /><Bar dataKey="expected_admissions" fill="#0ea5e9" /></BarChart></ResponsiveContainer></div>
            <div className="mt-3 grid gap-2 sm:grid-cols-4">{Object.entries(fc.bed_demand).map(([w, b]) => <div key={w} className="rounded-lg border border-slate-200 p-3 text-sm"><p className="font-medium capitalize">{w}</p><p className="text-xs text-slate-500">free now {b.available_now} · need ≈ {b.expected_new_patients}</p><Badge tone={b.risk === "ok" ? "good" : "bad"}>{b.risk}</Badge></div>)}</div>
            <p className="mt-2 text-xs text-slate-500">{fc.note}</p>
          </Card>
        </>
      )}
    </>
  );
}

function Departments() {
  const [list, setList] = useState([]);
  const [name, setName] = useState("");
  const { error, run } = useAsync();
  const load = () => api("/hospital-ops/departments").then(setList);
  useEffect(() => { load(); }, []);
  return (
    <Card title="Departments">
      <form className="mb-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); run(async () => { await api("/hospital-ops/departments", { method: "POST", body: { name } }); setName(""); load(); }); }}>
        <input className="input" required minLength={2} value={name} onChange={(e) => setName(e.target.value)} placeholder="New department" /><button className="btn-primary">Add</button>
      </form>
      <Alert tone="error">{error}</Alert>
      <div className="flex flex-wrap gap-2">{list.map((d) => <span key={d} className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-sm">{d}<button className="text-slate-400 hover:text-red-600" aria-label={`Remove ${d}`} onClick={async () => { await api(`/hospital-ops/departments/${encodeURIComponent(d)}`, { method: "DELETE" }); load(); }}>×</button></span>)}</div>
    </Card>
  );
}

function Resource({ kind, title, fields, cols }) {
  const [rows, setRows] = useState([]);
  const blank = Object.fromEntries(fields.map(([k, , t]) => [k, Array.isArray(t) ? t[0] : ""]));
  const [f, setF] = useState(blank);
  const { error, run } = useAsync();
  const load = () => api(`/hospital-ops/${kind}`).then(setRows);
  useEffect(() => { load(); }, [kind]); // eslint-disable-line
  const add = (e) => {
    e.preventDefault();
    const body = Object.fromEntries(Object.entries(f).filter(([, v]) => v !== "").map(([k, v]) => [k, fields.find((x) => x[0] === k)[2] === "number" ? Number(v) : v]));
    run(async () => { await api(`/hospital-ops/${kind}`, { method: "POST", body }); setF(blank); load(); });
  };
  return (
    <>
      <Card title={`Add to ${title.toLowerCase()}`}>
        <form onSubmit={add} className="grid gap-3 sm:grid-cols-3">
          {fields.map(([k, label, t]) => (
            <Field key={k} label={label}>
              {Array.isArray(t) ? <select className="input" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })}>{t.map((o) => <option key={o}>{o}</option>)}</select>
                : <input className="input" type={t || "text"} value={f[k]} min={t === "number" ? 0 : undefined} onChange={(e) => setF({ ...f, [k]: e.target.value })} required={k === "name" || k === "item" || k === "quantity"} />}
            </Field>
          ))}
          <div className="flex items-end"><button className="btn-primary">Add</button></div>
        </form>
        <div className="mt-3"><Alert tone="error">{error}</Alert></div>
      </Card>
      <Card title={`${title} (${rows.length})`}>
        {rows.length === 0 ? <Empty>Nothing added yet.</Empty> : (
          <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="text-left text-xs uppercase text-slate-500">{cols.map((c) => <th key={c} className="py-1 pr-3">{c.replace(/_/g, " ")}</th>)}<th /></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.id} className="border-t border-slate-100">{cols.map((c) => <td key={c} className="py-2 pr-3">{c === "status" ? <Badge tone={r[c] === "working" ? "good" : "bad"}>{r[c]}</Badge> : c === "quantity" && r.quantity <= r.reorder_level ? <Badge tone="bad">{r[c]} (low)</Badge> : String(r[c] ?? "—")}</td>)}
                <td className="text-right"><button className="text-xs text-red-600 hover:underline" onClick={async () => { await api(`/hospital-ops/${kind}/${r.id}`, { method: "DELETE" }); load(); }}>Remove</button></td></tr>
            ))}</tbody></table></div>
        )}
      </Card>
    </>
  );
}

function Theatre() {
  const [rows, setRows] = useState([]);
  const [f, setF] = useState({ theatre: "OT-1", patient_name: "", procedure: "", surgeon: "", date: new Date().toISOString().slice(0, 10), start: "09:00", end: "10:00" });
  const { error, run } = useAsync();
  const load = () => api("/hospital-ops/theatre").then(setRows);
  useEffect(() => { load(); }, []);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <>
      <Card title="Schedule a surgery">
        <form onSubmit={(e) => { e.preventDefault(); run(async () => { await api("/hospital-ops/theatre", { method: "POST", body: f }); load(); }); }} className="grid gap-3 sm:grid-cols-4">
          <Field label="Theatre"><input className="input" required value={f.theatre} onChange={set("theatre")} /></Field>
          <Field label="Patient"><input className="input" required value={f.patient_name} onChange={set("patient_name")} /></Field>
          <Field label="Procedure"><input className="input" required value={f.procedure} onChange={set("procedure")} /></Field>
          <Field label="Surgeon"><input className="input" required value={f.surgeon} onChange={set("surgeon")} /></Field>
          <Field label="Date"><input className="input" type="date" required value={f.date} onChange={set("date")} /></Field>
          <Field label="Start"><input className="input" type="time" required value={f.start} onChange={set("start")} /></Field>
          <Field label="End"><input className="input" type="time" required value={f.end} onChange={set("end")} /></Field>
          <div className="flex items-end"><button className="btn-primary">Book</button></div>
        </form>
        <div className="mt-3"><Alert tone="error">{error}</Alert></div>
      </Card>
      <Card title="Schedule">
        {rows.length === 0 ? <Empty>No surgeries scheduled.</Empty> : (
          <ul className="divide-y divide-slate-100 text-sm">{rows.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span><b>{r.theatre}</b> · {r.date} {r.start}–{r.end} · {r.procedure} · {r.patient_name} · {r.surgeon}</span>
              <span className="flex items-center gap-2"><Badge tone={r.status === "scheduled" ? "info" : r.status === "completed" ? "good" : "muted"}>{r.status}</Badge>
                {r.status === "scheduled" && <><button className="btn-ghost" onClick={async () => { await api(`/hospital-ops/theatre/${r.id}/complete`, { method: "PATCH" }); load(); }}>Done</button><button className="btn-ghost" onClick={async () => { await api(`/hospital-ops/theatre/${r.id}/cancel`, { method: "PATCH" }); load(); }}>Cancel</button></>}</span>
            </li>))}</ul>
        )}
      </Card>
    </>
  );
}
