import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { Alert, Badge, Card, Disclaimer, Empty, Field, useAsync } from "../components/ui.jsx";

const TABS = ["Scan report explainer", "Meditation", "Sleep schedule", "Counselors"];
export default function Extras() {
  const [tab, setTab] = useState(TABS[0]);
  return (
    <>
      <h1 className="text-xl font-bold">More health tools</h1>
      <div className="flex gap-1 overflow-x-auto border-b border-slate-200">{TABS.map((t) => <button key={t} onClick={() => setTab(t)} className={`whitespace-nowrap px-3 py-2 text-sm ${tab === t ? "border-b-2 border-brand-600 font-medium text-brand-700" : "text-slate-500"}`}>{t}</button>)}</div>
      {tab === TABS[0] && <Explainer />}{tab === TABS[1] && <Meditation />}{tab === TABS[2] && <Sleep />}{tab === TABS[3] && <Counselors />}
    </>
  );
}

const SEV = { urgent: "bad", attention: "warn", info: "good" };
function Explainer() {
  const [text, setText] = useState("");
  const [modality, setModality] = useState("");
  const [r, setR] = useState(null);
  const { busy, error, run } = useAsync();
  const go = (e) => { e.preventDefault(); run(async () => setR(await api("/extras/explain-report", { method: "POST", body: { text, modality: modality || null } }))); };
  return (
    <>
      <Card title="ECG, X-ray, MRI & CT report explainer">
        <form onSubmit={go} className="space-y-3">
          <Field label="Report type"><select className="input" value={modality} onChange={(e) => setModality(e.target.value)}><option value="">Detect automatically</option><option value="ecg">ECG</option><option value="xray">X-ray</option><option value="ct">CT scan</option><option value="mri">MRI</option></select></Field>
          <Field label="Paste the report text (the doctor's findings / impression)"><textarea className="input min-h-[140px]" required minLength={10} value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. Chest X-ray: right lower zone consolidation with mild pleural effusion. No pneumothorax." /></Field>
          <button className="btn-primary" disabled={busy}>{busy ? "Explaining…" : "Explain in simple words"}</button>
        </form>
        <div className="mt-3"><Alert tone="error">{error}</Alert></div>
      </Card>
      {r && (
        <Card title={`Explanation (${r.modality.toUpperCase()})`}>
          <Alert tone={r.urgent_count ? "error" : "info"}>{r.summary}</Alert>
          <ul className="mt-3 space-y-2">{r.findings.map((f) => <li key={f.term} className="rounded-lg border border-slate-200 p-3 text-sm"><Badge tone={SEV[f.severity]}>{f.severity}</Badge> <b className="ml-1 capitalize">{f.term}</b><p className="mt-1 text-slate-600">{f.meaning}</p></li>)}</ul>
          {r.findings.length === 0 && <Empty>No familiar phrases recognised.</Empty>}
          <p className="mt-3 text-xs text-slate-500">{r.disclaimer}</p>
        </Card>
      )}
    </>
  );
}

function Meditation() {
  const [items, setItems] = useState([]);
  const [need, setNeed] = useState("");
  const [open, setOpen] = useState(null);
  const [left, setLeft] = useState(0);
  useEffect(() => { api(`/wellness/meditations${need ? `?need=${need}` : ""}`).then(setItems).catch(() => {}); }, [need]);
  useEffect(() => { if (left <= 0) return; const t = setTimeout(() => setLeft(left - 1), 1000); return () => clearTimeout(t); }, [left]);
  return (
    <Card title="Guided meditation">
      <div className="mb-3 flex flex-wrap gap-2">{["", "stress", "anxiety", "sleep", "focus", "low mood"].map((n) => <button key={n} onClick={() => setNeed(n)} className={`rounded-full border px-3 py-1 text-xs ${need === n ? "border-brand-600 bg-brand-50 text-brand-700" : "border-slate-300"}`}>{n || "All"}</button>)}</div>
      <div className="grid gap-3 sm:grid-cols-2">
        {items.map((m) => (
          <div key={m.id} className="rounded-xl border border-slate-200 p-4 text-sm">
            <div className="flex items-center justify-between"><b>{m.title}</b><Badge tone="info">{m.minutes} min</Badge></div>
            <p className="text-xs text-slate-500">{m.title_hi} · good for {m.good_for.join(", ")}</p>
            <button className="btn-ghost mt-2" onClick={() => { setOpen(open === m.id ? null : m.id); setLeft(m.minutes * 60); }}>{open === m.id ? "Close" : "Start"}</button>
            {open === m.id && (
              <div className="mt-2 space-y-1">
                <p className="text-2xl font-bold text-brand-700">{String(Math.floor(left / 60)).padStart(2, "0")}:{String(left % 60).padStart(2, "0")}</p>
                <ol className="list-decimal pl-5 text-slate-700">{m.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

function Sleep() {
  const [wake, setWake] = useState("06:30");
  const [age, setAge] = useState(30);
  const [r, setR] = useState(null);
  const { error, run } = useAsync();
  const go = (e) => { e?.preventDefault(); run(async () => setR(await api(`/wellness/sleep-schedule?wake_time=${wake}&age=${age}`))); };
  useEffect(() => { go(); }, []); // eslint-disable-line
  return (
    <Card title="Sleep schedule planner">
      <form onSubmit={go} className="flex flex-wrap items-end gap-3">
        <Field label="Wake-up time"><input className="input" type="time" value={wake} onChange={(e) => setWake(e.target.value)} /></Field>
        <Field label="Age"><input className="input w-24" type="number" min="5" max="110" value={age} onChange={(e) => setAge(e.target.value)} /></Field>
        <button className="btn-primary">Plan</button>
      </form>
      <div className="mt-3"><Alert tone="error">{error}</Alert></div>
      {r && (
        <div className="mt-4 space-y-3 text-sm">
          <p>Recommended sleep: <b>{r.recommended_hours} h</b>{r.avg_last_7_days != null && <> · your 7-day average: <b>{r.avg_last_7_days} h</b></>}</p>
          <div className="grid gap-2 sm:grid-cols-3">{r.options.map((o) => <div key={o.cycles} className="rounded-lg border border-slate-200 p-3 text-center"><p className="text-2xl font-bold text-brand-700">{o.bedtime}</p><p className="text-xs text-slate-500">go to bed · {o.hours} h ({o.cycles} cycles)</p></div>)}</div>
          <ul className="list-disc pl-5 text-slate-700">{r.tips.map((t) => <li key={t}>{t}</li>)}</ul>
        </div>
      )}
    </Card>
  );
}

function Counselors() {
  const [list, setList] = useState(null);
  useEffect(() => { api("/wellness/counselors").then(setList).catch(() => setList([])); }, []);
  return (
    <Card title="Professional counselors & psychiatrists">
      {list === null ? <Empty>Loading…</Empty> : list.length === 0 ? <Empty>No verified counselors are listed yet.</Empty> : (
        <ul className="divide-y divide-slate-100">{list.map((d) => <li key={d.id} className="flex items-center justify-between py-3 text-sm"><span><b>{d.name}</b> · {d.specialization}<br /><span className="text-xs text-slate-500">{d.city} · ₹{d.fee} · ★ {d.rating}</span></span><Link className="btn-primary" to="/appointments">Book</Link></li>)}</ul>
      )}
      <p className="mt-3 text-xs text-slate-500">If you are in distress or thinking of harming yourself, call Tele-MANAS 14416 or emergency 112 right away.</p>
      <Disclaimer />
    </Card>
  );
}
