import { useEffect, useState } from "react";
import { api } from "../api.js";
import VoiceSymptoms from "../components/VoiceSymptoms.jsx";
import { Alert, Badge, Card, Disclaimer, Field, Stat, toneFor, useAsync } from "../components/ui.jsx";

const NAMES = { diabetes: "Diabetes", heart: "Heart disease", kidney: "Kidney disease", liver: "Liver disease", stroke: "Stroke", anemia: "Anemia", thyroid: "Thyroid", hypertension: "Blood pressure", cancer: "Cancer (lifestyle)" };

export default function Risk() {
  const [specs, setSpecs] = useState([]);
  const [vals, setVals] = useState({});
  const [out, setOut] = useState(null);
  const [hist, setHist] = useState([]);
  const [twin, setTwin] = useState(null);
  const [sim, setSim] = useState(null);
  const [change, setChange] = useState({ key: "bmi", value: "" });
  const [opinion, setOpinion] = useState(null);
  const { busy, error, run } = useAsync();

  useEffect(() => {
    run(async () => {
      setSpecs(await api("/ai/diseases"));
      setVals(await api("/ai/autofill"));
      setHist(await api("/ai/risk-history"));
    });
  }, []);

  const features = (() => {
    const m = {};
    specs.forEach((d) => d.features.forEach((f) => { m[f.name] = f; }));
    return Object.values(m);
  })();

  const assess = (e) => {
    e.preventDefault();
    const values = {};
    Object.entries(vals).forEach(([k, v]) => { if (v !== "" && v !== null && v !== undefined) values[k] = Number(v); });
    run(async () => { setOut(await api("/ai/risk-score", { method: "POST", body: { values, use_profile: true } })); setHist(await api("/ai/risk-history")); });
  };
  const loadTwin = () => run(async () => setTwin(await api("/ai/digital-twin")));
  const simulate = () => run(async () => setSim(await api("/ai/digital-twin/simulate", { method: "POST", body: { changes: { [change.key]: Number(change.value) } } })));
  const second = () => run(async () => setOpinion(await api("/ai/second-opinion")));

  return (
    <>
      <h1 className="text-xl font-bold">AI health risk check</h1>
      <Alert tone="error">{error}</Alert>
      <VoiceSymptoms />
      <Card title="Your numbers">
        <p className="mb-3 text-sm text-slate-500">Pre-filled from your profile, vitals and latest lab reports. Edit anything, then run the assessment. Fields left empty use typical defaults.</p>
        <form onSubmit={assess} className="grid gap-3 md:grid-cols-3">
          {features.map((f) => (
            <Field key={f.name} label={f.label}>
              <input className="input" type="number" step="any" min={f.min} max={f.max} value={vals[f.name] ?? ""} onChange={(e) => setVals({ ...vals, [f.name]: e.target.value })} />
            </Field>
          ))}
          <div className="md:col-span-3"><button className="btn-primary" disabled={busy}>{busy ? "Working…" : "Run all risk assessments"}</button></div>
        </form>
      </Card>

      {out && (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <Stat label="Overall health score" value={out.overall.score} sub={out.overall.label} />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {out.results.map((r) => (
              <Card key={r.disease} title={r.title} action={<Badge tone={toneFor(r.level)}>{r.level} · {r.score}%</Badge>}>
                <p className="text-sm text-slate-700">{r.advice}</p>
                <ul className="mt-2 space-y-1 text-xs text-slate-600">
                  {r.factors.slice(0, 3).map((f) => <li key={f.feature}>• {f.label}: {f.value} ({f.direction})</li>)}
                </ul>
                <p className="mt-2 text-xs text-slate-400">{r.inputs_provided}/{r.inputs_total} inputs provided</p>
              </Card>
            ))}
          </div>
          <Card title="Preventive recommendations">
            <ul className="list-disc space-y-1 pl-5 text-sm">{out.preventive_recommendations.map((t) => <li key={t}>{t}</li>)}</ul>
          </Card>
          <Disclaimer />
        </>
      )}

      <Card title="Digital twin (what-if)" action={<button className="btn-ghost py-1" onClick={loadTwin}>Load my twin</button>}>
        {twin && (
          <>
            <p className="text-sm">Overall score <b>{twin.overall.score}</b> ({twin.overall.label}). Conditions: {twin.conditions.join(", ") || "none recorded"}. Medicines: {twin.active_medicines.join(", ") || "none"}.</p>
            <div className="mt-3 flex flex-wrap items-end gap-2">
              <Field label="Change input"><select className="input" value={change.key} onChange={(e) => setChange({ ...change, key: e.target.value })}>{features.map((f) => <option key={f.name} value={f.name}>{f.label}</option>)}</select></Field>
              <Field label="New value"><input className="input" type="number" step="any" value={change.value} onChange={(e) => setChange({ ...change, value: e.target.value })} /></Field>
              <button className="btn-primary" disabled={change.value === ""} onClick={simulate}>Simulate</button>
            </div>
            {sim && (
              <ul className="mt-3 space-y-1 text-sm">
                {sim.results.map((r) => <li key={r.disease}>{r.title}: {r.before}% → <b>{r.after}%</b> <Badge tone={r.delta < 0 ? "good" : r.delta > 0 ? "bad" : "muted"}>{r.delta > 0 ? "+" : ""}{r.delta}</Badge></li>)}
              </ul>
            )}
          </>
        )}
      </Card>

      <Card title="AI second-opinion summary" action={<button className="btn-ghost py-1" onClick={second}>Prepare for my doctor</button>}>
        {opinion && (
          <div className="space-y-2 text-sm">
            <p><b>Suggested specialists:</b> {opinion.suggested_specialists.join(", ") || "General physician"}</p>
            <ul className="list-disc space-y-1 pl-5">{opinion.questions_for_doctor.map((q, i) => <li key={i}>{q}</li>)}</ul>
            <p className="text-xs text-slate-500">{opinion.disclaimer}</p>
          </div>
        )}
      </Card>

      <Card title="Assessment history">
        {hist.length === 0 && <p className="text-sm text-slate-500">No assessments yet.</p>}
        <ul className="divide-y divide-slate-100 text-sm">{hist.slice(0, 15).map((h) => <li key={h.id} className="flex justify-between py-1.5"><span>{NAMES[h.disease] || h.disease}</span><span><Badge tone={toneFor(h.level)}>{h.level}</Badge> <span className="text-xs text-slate-400">{h.ts.slice(0, 10)}</span></span></li>)}</ul>
      </Card>
    </>
  );
}
