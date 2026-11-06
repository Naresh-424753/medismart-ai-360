import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Alert, Badge, Card, Empty, Field, Stat, useAsync } from "../components/ui.jsx";

const TYPES = [["water", "Water (litres)"], ["steps", "Steps"], ["sleep", "Sleep (hours)"], ["weight", "Weight (kg)"], ["mood", "Mood (1 low – 5 great)"], ["journal", "Journal entry"]];

export default function Wellness() {
  const [tab, setTab] = useState("Plan");
  return (
    <>
      <h1 className="text-xl font-bold">Nutrition, fitness & mental wellness</h1>
      <div className="flex gap-1 border-b border-slate-200">{["Plan", "Daily tracker", "Mental health"].map((t) => <button key={t} onClick={() => setTab(t)} className={`px-3 py-2 text-sm ${tab === t ? "border-b-2 border-brand-600 font-medium text-brand-700" : "text-slate-500"}`}>{t}</button>)}</div>
      {tab === "Plan" && <Plan />}{tab === "Daily tracker" && <Tracker />}{tab === "Mental health" && <Mental />}
    </>
  );
}

function Plan() {
  const [f, setF] = useState({ weight_kg: "", height_cm: "", age: "", sex: "male", activity: "light", goal: "maintain", vegetarian: true });
  const [r, setR] = useState(null);
  const { busy, error, run } = useAsync();
  useEffect(() => { api("/patients/me").then((p) => setF((x) => ({ ...x, weight_kg: p.weight_kg || "", height_cm: p.height_cm || "", age: p.age || "", sex: p.sex === "female" ? "female" : "male" }))).catch(() => {}); }, []);
  const go = (e) => { e.preventDefault(); run(async () => setR(await api("/wellness/calculate", { method: "POST", body: { ...f, weight_kg: +f.weight_kg, height_cm: +f.height_cm, age: +f.age } }))); };
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <>
      <Card title="BMI, BMR & calorie calculator">
        <form onSubmit={go} className="grid gap-3 md:grid-cols-4">
          <Field label="Weight (kg)"><input className="input" type="number" step="0.1" required value={f.weight_kg} onChange={set("weight_kg")} /></Field>
          <Field label="Height (cm)"><input className="input" type="number" step="0.1" required value={f.height_cm} onChange={set("height_cm")} /></Field>
          <Field label="Age"><input className="input" type="number" required value={f.age} onChange={set("age")} /></Field>
          <Field label="Sex"><select className="input" value={f.sex} onChange={set("sex")}><option value="male">Male</option><option value="female">Female</option></select></Field>
          <Field label="Activity"><select className="input" value={f.activity} onChange={set("activity")}>{["sedentary", "light", "moderate", "active", "very_active"].map((a) => <option key={a}>{a}</option>)}</select></Field>
          <Field label="Goal"><select className="input" value={f.goal} onChange={set("goal")}><option value="lose">Lose weight</option><option value="maintain">Maintain</option><option value="gain">Gain weight</option></select></Field>
          <label className="flex items-end gap-2 pb-2 text-sm"><input type="checkbox" checked={f.vegetarian} onChange={(e) => setF({ ...f, vegetarian: e.target.checked })} />Vegetarian</label>
          <div className="flex items-end"><button className="btn-primary w-full" disabled={busy}>Calculate</button></div>
        </form>
        <div className="mt-3"><Alert tone="error">{error}</Alert></div>
      </Card>
      {r && (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4"><Stat label={`BMI · ${r.bmi_category}`} value={r.bmi} /><Stat label="BMR (kcal)" value={r.bmr} /><Stat label="Daily calories" value={r.calorie_target} /><Stat label="Water (L) / steps" value={`${r.water_liters} / ${r.step_goal}`} /></div>
          <div className="grid gap-4 md:grid-cols-2">
            <Card title="Diet suggestions"><p className="text-xs text-slate-500">Protein ~{r.protein_g} g/day · healthy weight {r.healthy_weight_range_kg[0]}–{r.healthy_weight_range_kg[1]} kg</p>
              <ul className="mt-2 space-y-1 text-sm">{Object.entries(r.diet.meals).map(([k, v]) => <li key={k}><b className="capitalize">{k}:</b> {Array.isArray(v) ? v.join(", ") : String(v)}</li>)}</ul>
              {r.diet.avoid.length > 0 && <p className="mt-2 text-sm text-amber-800">Limit: {r.diet.avoid.join(", ")}</p>}
              <ul className="mt-2 list-disc pl-5 text-xs text-slate-600">{r.diet.tips.map((t) => <li key={t}>{t}</li>)}</ul></Card>
            <Card title="Exercise plan"><ul className="list-disc space-y-1 pl-5 text-sm">{r.exercise.map((t) => <li key={t}>{t}</li>)}</ul></Card>
          </div>
        </>
      )}
    </>
  );
}

function Tracker() {
  const [prog, setProg] = useState(null);
  const [type, setType] = useState("water");
  const [val, setVal] = useState("");
  const [note, setNote] = useState("");
  const [logs, setLogs] = useState([]);
  const { error, run } = useAsync();
  const load = () => { api("/wellness/progress").then(setProg).catch(() => {}); api(`/wellness/logs?type=${type}&days=30`).then(setLogs).catch(() => {}); };
  useEffect(() => { load(); }, [type]);
  const add = (e) => { e.preventDefault(); run(async () => { await api("/wellness/log", { method: "POST", body: { type, ...(val !== "" ? { value: +val } : {}), note } }); setVal(""); setNote(""); load(); }); };
  return (
    <>
      {prog?.tips.map((t) => <Alert key={t} tone="warn">{t}</Alert>)}
      {prog && <div className="grid grid-cols-2 gap-4 md:grid-cols-5">{Object.entries(prog.weekly).map(([k, v]) => <Stat key={k} label={`${k} (7-day avg)`} value={v.average} sub={v.average != null ? v.trend : ""} />)}</div>}
      <Card title="Log today">
        <form onSubmit={add} className="grid gap-3 md:grid-cols-4">
          <Field label="What"><select className="input" value={type} onChange={(e) => setType(e.target.value)}>{TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
          {type !== "journal" && <Field label="Value"><input className="input" type="number" step="any" required value={val} onChange={(e) => setVal(e.target.value)} /></Field>}
          <div className={type === "journal" ? "md:col-span-2" : ""}><Field label="Note"><input className="input" value={note} onChange={(e) => setNote(e.target.value)} required={type === "journal"} /></Field></div>
          <div className="flex items-end"><button className="btn-primary w-full">Save</button></div>
        </form>
        <div className="mt-2"><Alert tone="error">{error}</Alert></div>
        {logs.length === 0 ? <div className="mt-3"><Empty>No {type} logs in the last 30 days.</Empty></div> : <ul className="mt-3 divide-y divide-slate-100 text-sm">{logs.slice(-10).reverse().map((l) => <li key={l.id} className="flex justify-between py-1.5"><span>{l.date} · {l.value ?? ""} {l.note && <span className="text-slate-500">{l.note}</span>}</span><button className="text-xs text-red-600 hover:underline" onClick={() => run(async () => { await api(`/wellness/logs/${l.id}`, { method: "DELETE" }); load(); })}>Delete</button></li>)}</ul>}
      </Card>
    </>
  );
}

function Mental() {
  const [qs, setQs] = useState(null);
  const [ans, setAns] = useState({ depression: [null, null], anxiety: [null, null] });
  const [res, setRes] = useState({});
  const [breath, setBreath] = useState([]);
  const { error, run } = useAsync();
  useEffect(() => { api("/wellness/screening-questions").then(setQs).catch(() => {}); api("/wellness/breathing").then(setBreath).catch(() => {}); }, []);
  const submit = (kind) => run(async () => { const r = await api("/wellness/screen", { method: "POST", body: { kind, answers: ans[kind] } }); setRes((x) => ({ ...x, [kind]: r })); });
  return (
    <>
      <Alert tone="info">These are brief screening questions, not a diagnosis. If you are in crisis call 112 or Tele-MANAS 14416 (India).</Alert><Alert tone="error">{error}</Alert>
      {qs && ["depression", "anxiety"].map((kind) => (
        <Card key={kind} title={`${kind === "depression" ? "Mood (PHQ-2)" : "Anxiety (GAD-2)"} screening`}>
          <p className="mb-2 text-sm text-slate-500">{qs.note}</p>
          {qs[kind].map((q, i) => (
            <div key={q} className="mb-2"><p className="text-sm font-medium">{q}</p>
              <div className="flex flex-wrap gap-3 text-sm">{qs.scale.map((s, v) => <label key={s} className="flex items-center gap-1"><input type="radio" name={`${kind}${i}`} checked={ans[kind][i] === v} onChange={() => setAns({ ...ans, [kind]: ans[kind].map((a, j) => (j === i ? v : a)) })} />{s}</label>)}</div></div>
          ))}
          <button className="btn-primary" disabled={ans[kind].some((a) => a === null)} onClick={() => submit(kind)}>See result</button>
          {res[kind] && <div className="mt-3 space-y-1 text-sm"><Badge tone={res[kind].positive_screen ? "warn" : "good"}>score {res[kind].score}/6</Badge><p>{res[kind].message}</p><p className="text-xs text-slate-500">{res[kind].support}</p>{res[kind].positive_screen && <a className="text-brand-700 underline" href="/appointments">Book a counselor / doctor</a>}</div>}
        </Card>
      ))}
      <Card title="Breathing & relaxation">{breath.map((b) => <p key={b.name} className="text-sm"><b>{b.name}:</b> {b.steps}</p>)}</Card>
    </>
  );
}
