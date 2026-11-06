import { useEffect, useState } from "react";
import { api } from "../api.js";
import RxOrder from "../components/RxOrder.jsx";
import { Alert, Badge, Card, Empty, Field, useAsync } from "../components/ui.jsx";

const TONE = { draft: "muted", pending_verification: "warn", verified: "good", rejected: "bad", activated: "info" };
const LABEL = { draft: "Draft - not verified", pending_verification: "Waiting for doctor/pharmacist", verified: "Verified", rejected: "Needs changes", activated: "Reminders active" };

export default function RxScan() {
  const [list, setList] = useState([]);
  const [cur, setCur] = useState(null);
  const [file, setFile] = useState(null);
  const [ordering, setOrdering] = useState(false);
  const { busy, error, run } = useAsync();
  const load = () => api("/rx-scan").then(setList).catch(() => {});
  useEffect(() => { load(); }, []);
  const open = (id) => run(async () => setCur(await api(`/rx-scan/${id}`)));
  const upload = (e) => { e.preventDefault(); if (!file) return; run(async () => { const form = new FormData(); form.append("file", file); const r = await api("/rx-scan/upload", { method: "POST", form }); setCur(r); load(); }); };
  const setItem = (i, k, v) => setCur({ ...cur, items: cur.items.map((it, j) => (j === i ? { ...it, [k]: v } : it)) });
  const clean = (it) => ({ name: it.name, dose: it.dose || "", times: it.times, duration_days: Number(it.duration_days) || 1, instructions: it.instructions || "" });
  const save = () => run(async () => { const r = await api(`/rx-scan/${cur.id}`, { method: "PUT", body: { items: cur.items.map(clean) } }); setCur({ ...cur, ...r }); load(); });
  const ask = () => run(async () => { await api(`/rx-scan/${cur.id}`, { method: "PUT", body: { items: cur.items.map(clean) } }); await api(`/rx-scan/${cur.id}/request-verification`, { method: "POST" }); await open(cur.id); load(); });
  const activate = () => run(async () => { await api(`/rx-scan/${cur.id}/activate`, { method: "POST" }); await open(cur.id); load(); });
  const editable = cur && ["draft", "rejected"].includes(cur.status);

  return (
    <>
      <h1 className="text-xl font-bold">Prescription scanner</h1>
      <Alert tone="warn">Reads printed prescriptions best; handwriting is often misread. Nothing becomes a medicine reminder until a doctor or pharmacist verifies it.</Alert>
      <Card title="1. Scan a prescription">
        <form onSubmit={upload} className="flex flex-wrap items-end gap-3">
          <Field label="Photo (JPEG / PNG, max 10 MB)"><input className="input" type="file" accept="image/*" capture="environment" onChange={(e) => setFile(e.target.files[0])} /></Field>
          <button className="btn-primary" disabled={busy || !file}>{busy ? "Reading…" : "Scan"}</button>
        </form>
        <div className="mt-3"><Alert tone="error">{error}</Alert></div>
      </Card>
      {cur && (
        <Card title={`2. Check and verify`} action={<Badge tone={TONE[cur.status]}>{LABEL[cur.status]}</Badge>}>
          {cur.warnings?.length > 0 && <Alert tone="error">{cur.warnings.join(" · ")}</Alert>}
          {cur.review_note && <Alert tone="info">Reviewer ({cur.reviewed_by?.name}): {cur.review_note}</Alert>}
          {cur.items.length === 0 && <Empty>No medicines were recognised. Retake the photo in good light, or add them manually after verification support is available.</Empty>}
          <div className="space-y-3">
            {cur.items.map((it, i) => (
              <div key={i} className="rounded-lg border border-slate-200 p-3 text-sm">
                <div className="grid gap-2 sm:grid-cols-4">
                  <Field label="Medicine"><input className="input" disabled={!editable} value={it.name} onChange={(e) => setItem(i, "name", e.target.value)} /></Field>
                  <Field label="Strength"><input className="input" disabled={!editable} value={it.dose} onChange={(e) => setItem(i, "dose", e.target.value)} /></Field>
                  <Field label="Times (HH:MM, comma separated)"><input className="input" disabled={!editable} value={it.times.join(", ")} onChange={(e) => setItem(i, "times", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} /></Field>
                  <Field label="Days"><input className="input" type="number" min="1" disabled={!editable} value={it.duration_days} onChange={(e) => setItem(i, "duration_days", e.target.value)} /></Field>
                </div>
                <p className="mt-1 text-xs text-slate-500">{it.instructions} {it.confidence != null && <>· confidence {Math.round(it.confidence * 100)}%</>}</p>
                {it.review_flags?.length > 0 && <p className="mt-1 text-xs text-amber-700">⚠ {it.review_flags.join("; ")}</p>}
              </div>
            ))}
          </div>
          {ordering && <div className="mt-3"><RxOrder names={cur.items.map((i) => i.name)} onClose={() => setOrdering(false)} onPlaced={() => setOrdering(false)} /></div>}
          {cur.id && <details className="mt-3 text-xs"><summary className="cursor-pointer text-slate-500">Show original image and OCR text</summary><ScanImage id={cur.id} /><pre className="mt-2 whitespace-pre-wrap rounded bg-slate-50 p-2">{cur.text}</pre></details>}
          <div className="mt-4 flex flex-wrap gap-2">
            {editable && <button className="btn-ghost" onClick={save} disabled={busy}>Save changes</button>}
            {editable && cur.items.length > 0 && <button className="btn-primary" onClick={ask} disabled={busy}>Send for verification</button>}
            {cur.status === "verified" && <button className="btn-primary" onClick={activate} disabled={busy}>Create medicine reminders</button>}
            {["verified", "activated"].includes(cur.status) && cur.items.length > 0 && <button className="btn-ghost" onClick={() => setOrdering(true)}>Order these medicines</button>}
          </div>
        </Card>
      )}
      <Card title="My scans">
        {list.length === 0 ? <Empty>No scans yet.</Empty> : <ul className="divide-y divide-slate-100 text-sm">{list.map((s) => <li key={s.id} className="flex items-center justify-between py-2"><span>{new Date(s.created_at).toLocaleString()} · {s.items.length} medicine(s)</span><span className="flex items-center gap-2"><Badge tone={TONE[s.status]}>{LABEL[s.status]}</Badge><button className="btn-ghost py-1" onClick={() => open(s.id)}>Open</button></span></li>)}</ul>}
      </Card>
    </>
  );
}

export function ScanImage({ id }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    let u;
    fetch(`${import.meta.env.VITE_API_URL || "http://localhost:8000"}/rx-scan/${id}/image`, { headers: { Authorization: `Bearer ${localStorage.getItem("ms_token")}` } })
      .then((r) => (r.ok ? r.blob() : Promise.reject())).then((b) => { u = URL.createObjectURL(b); setUrl(u); }).catch(() => {});
    return () => u && URL.revokeObjectURL(u);
  }, [id]);
  return url ? <img src={url} alt="Scanned prescription" className="mt-2 max-h-80 rounded border border-slate-200" /> : null;
}
