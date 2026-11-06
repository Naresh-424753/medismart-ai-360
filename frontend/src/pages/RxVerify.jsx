import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Alert, Badge, Card, Empty, Field, useAsync } from "../components/ui.jsx";
import { ScanImage } from "./RxScan.jsx";

export default function RxVerify() {
  const [q, setQ] = useState([]);
  const [cur, setCur] = useState(null);
  const [note, setNote] = useState("");
  const { busy, error, run } = useAsync();
  const load = () => api("/rx-scan/queue").then(setQ).catch((e) => setQ([]));
  useEffect(() => { load(); }, []);
  const setItem = (i, k, v) => setCur({ ...cur, items: cur.items.map((it, j) => (j === i ? { ...it, [k]: v } : it)) });
  const decide = (approve) => run(async () => {
    const items = cur.items.map((it) => ({ name: it.name, dose: it.dose || "", times: it.times, duration_days: Number(it.duration_days) || 1, instructions: it.instructions || "" }));
    await api(`/rx-scan/${cur.id}/review`, { method: "POST", body: { approve, note, items: approve ? items : null } });
    setCur(null); setNote(""); load();
  });
  return (
    <>
      <h1 className="text-xl font-bold">Prescription verification queue</h1>
      <Alert tone="info">Compare each item with the original image. Correct anything wrong before approving: an approved scan becomes the patient's medicine reminders.</Alert>
      <Alert tone="error">{error}</Alert>
      <div className="grid gap-4 md:grid-cols-3">
        <Card title={`Waiting (${q.length})`}>
          {q.length === 0 ? <Empty>Queue is empty.</Empty> : <ul className="space-y-1">{q.map((s) => <li key={s.id}><button onClick={() => { setCur(s); setNote(""); }} className={`w-full rounded-lg px-3 py-2 text-left text-sm ${cur?.id === s.id ? "bg-brand-50" : "hover:bg-slate-100"}`}><b>{s.patient_name}</b><br /><span className="text-xs text-slate-500">{s.items.length} medicine(s) · {new Date(s.created_at).toLocaleString()}</span></button></li>)}</ul>}
        </Card>
        <div className="md:col-span-2">
          {cur ? (
            <Card title={`Review: ${cur.patient_name}`}>
              {cur.warnings?.length > 0 && <Alert tone="error">{cur.warnings.join(" · ")}</Alert>}
              <ScanImage id={cur.id} />
              <div className="mt-3 space-y-3">{cur.items.map((it, i) => (
                <div key={i} className="grid gap-2 rounded-lg border border-slate-200 p-3 text-sm sm:grid-cols-4">
                  <Field label="Medicine"><input className="input" value={it.name} onChange={(e) => setItem(i, "name", e.target.value)} /></Field>
                  <Field label="Strength"><input className="input" value={it.dose} onChange={(e) => setItem(i, "dose", e.target.value)} /></Field>
                  <Field label="Times"><input className="input" value={it.times.join(", ")} onChange={(e) => setItem(i, "times", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} /></Field>
                  <Field label="Days"><input className="input" type="number" min="1" value={it.duration_days} onChange={(e) => setItem(i, "duration_days", e.target.value)} /></Field>
                  {it.review_flags?.length > 0 && <p className="text-xs text-amber-700 sm:col-span-4">⚠ {it.review_flags.join("; ")}</p>}
                </div>))}</div>
              <div className="mt-3"><Field label="Note to patient (required when asking for changes)"><input className="input" value={note} onChange={(e) => setNote(e.target.value)} /></Field></div>
              <div className="mt-3 flex gap-2"><button className="btn-primary" disabled={busy} onClick={() => decide(true)}>Approve</button><button className="btn-ghost" disabled={busy || !note.trim()} onClick={() => decide(false)}>Ask for changes</button></div>
            </Card>
          ) : <Card><Empty>Select a scan to review.</Empty></Card>}
        </div>
      </div>
    </>
  );
}
