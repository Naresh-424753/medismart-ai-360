import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { Alert, Badge, Card, Empty, Field, textToList, useAsync } from "../components/ui.jsx";

const blank = { name: "", dose: "", times: "08:00, 20:00", duration_days: 5, instructions: "" };
export default function Prescribe() {
  const [sp] = useSearchParams();
  const [patients, setPatients] = useState([]);
  const [pid, setPid] = useState(sp.get("patient") || "");
  const [dx, setDx] = useState("");
  const [items, setItems] = useState([{ ...blank }]);
  const [notes, setNotes] = useState("");
  const [made, setMade] = useState(null);
  const [past, setPast] = useState([]);
  const { busy, error, run } = useAsync();
  const load = () => api("/prescriptions").then(setPast).catch(() => {});
  useEffect(() => { api("/doctor/patients").then(setPatients).catch(() => {}); load(); }, []);
  const set = (i, k, v) => setItems(items.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
  const submit = (e) => {
    e.preventDefault();
    run(async () => {
      const body = { patient_user_id: pid, diagnosis: dx, notes, items: items.map((x) => ({ ...x, times: textToList(x.times), duration_days: +x.duration_days })) };
      setMade(await api("/prescriptions", { method: "POST", body })); setItems([{ ...blank }]); setDx(""); setNotes(""); load();
    });
  };
  return (
    <>
      <h1 className="text-xl font-bold">Digital prescription</h1>
      <Alert tone="error">{error}</Alert>
      {made && <Alert tone="ok">Prescription <b>{made.code}</b> issued; the patient was notified and pharmacies can verify this code. {made.warnings.length > 0 && `Warnings: ${made.warnings.join(" | ")}`}</Alert>}
      <Card title="New prescription">
        <form onSubmit={submit} className="space-y-3">
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="Patient (must have an appointment with you)"><select className="input" required value={pid} onChange={(e) => setPid(e.target.value)}><option value="">Choose…</option>{patients.map((p) => <option key={p.user_id} value={p.user_id}>{p.name}</option>)}</select></Field>
            <Field label="Diagnosis"><input className="input" value={dx} onChange={(e) => setDx(e.target.value)} /></Field>
          </div>
          {items.map((it, i) => (
            <div key={i} className="grid gap-2 rounded-lg bg-slate-50 p-3 md:grid-cols-5">
              <input className="input" placeholder="Medicine" required value={it.name} onChange={(e) => set(i, "name", e.target.value)} />
              <input className="input" placeholder="Dose (500 mg)" value={it.dose} onChange={(e) => set(i, "dose", e.target.value)} />
              <input className="input" placeholder="Times HH:MM, …" value={it.times} onChange={(e) => set(i, "times", e.target.value)} />
              <input className="input" type="number" min="1" placeholder="Days" value={it.duration_days} onChange={(e) => set(i, "duration_days", e.target.value)} />
              <div className="flex gap-2"><input className="input" placeholder="Instructions" value={it.instructions} onChange={(e) => set(i, "instructions", e.target.value)} />{items.length > 1 && <button type="button" className="btn-ghost" onClick={() => setItems(items.filter((_, j) => j !== i))}>✕</button>}</div>
            </div>
          ))}
          <button type="button" className="btn-ghost" onClick={() => setItems([...items, { ...blank }])}>+ Add medicine</button>
          <Field label="Advice / notes"><textarea className="input h-16" value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
          <button className="btn-primary" disabled={busy || !pid}>Issue prescription</button>
        </form>
      </Card>
      <Card title="Issued prescriptions">
        {past.length === 0 && <Empty>None yet.</Empty>}
        <ul className="divide-y divide-slate-100 text-sm">{past.map((p) => <li key={p.id} className="py-2"><b>{p.code}</b> · {p.created_at.slice(0, 10)} · {p.diagnosis || "—"} · {p.items.map((i) => i.name).join(", ")} {p.imported && <Badge tone="good">patient added to schedule</Badge>}</li>)}</ul>
      </Card>
    </>
  );
}
