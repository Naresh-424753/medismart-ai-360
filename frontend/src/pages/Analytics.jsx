import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Alert, Badge, Card, Empty, Field, Stat, sortedEntries, useAsync } from "../components/ui.jsx";

const arrow = (t) => (t === "rising" ? "↗ rising" : t === "falling" ? "↘ falling" : "→ stable");

export default function Analytics() {
  const { user } = useAuth();
  return user.role === "patient" ? <PatientInsights /> : <Population />;
}

function PatientInsights() {
  const [d, setD] = useState(null);
  const [m, setM] = useState(null);
  const [days, setDays] = useState(14);
  const { error, run } = useAsync();
  useEffect(() => { run(async () => { setD(await api(`/analytics/my-health?days=${days}`)); }); }, [days]);
  useEffect(() => { run(async () => setM(await api("/analytics/monthly-report"))); }, []);
  const LABEL = { heart_rate: "Heart rate", spo2: "SpO₂", temperature: "Temperature", systolic: "Systolic BP", diastolic: "Diastolic BP", glucose: "Glucose" };
  return (
    <>
      <div className="flex items-center justify-between"><h1 className="text-xl font-bold">Health insights</h1><select className="input w-auto py-1" value={days} onChange={(e) => setDays(+e.target.value)}><option value={7}>7 days</option><option value={14}>14 days</option><option value={30}>30 days</option><option value={90}>90 days</option></select></div>
      <Alert tone="error">{error}</Alert>
      {d?.preventive_alerts.map((a, i) => <Alert key={i} tone="warn">{a}</Alert>)}
      {d && (
        <div className="grid gap-4 md:grid-cols-2">
          {Object.entries(d.vitals).map(([k, v]) => {
            const data = sortedEntries(v.daily_avg).map(([date, val]) => ({ date: date.slice(5), val }));
            return (
              <Card key={k} title={LABEL[k] || k} action={<Badge tone={v.anomaly_count ? "warn" : "muted"}>{data.length ? arrow(v.trend) : "no data"}</Badge>}>
                {data.length < 2 ? <Empty>Not enough readings yet.</Empty> : <div className="h-36"><ResponsiveContainer><LineChart data={data}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="date" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} domain={["auto", "auto"]} width={36} /><Tooltip /><Line dataKey="val" stroke="#047857" strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer></div>}
                <p className="text-xs text-slate-500">{v.n} readings{v.anomaly_count ? ` · ${v.anomaly_count} unusual` : ""}</p>
              </Card>
            );
          })}
        </div>
      )}
      {d && <Card title="Risk score history">{Object.keys(d.risk_history).length === 0 ? <Empty>Run risk checks over time to see trends.</Empty> : <ul className="text-sm">{Object.entries(d.risk_history).map(([k, s]) => <li key={k} className="capitalize">{k}: {s.map((x) => Math.round(x.p * 100) + "%").join(" → ")}</li>)}</ul>}</Card>}
      {m && (
        <Card title={`Monthly report (${m.period})`}>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-5"><Stat label="Reports analysed" value={m.reports_analyzed} /><Stat label="Abnormal values" value={m.abnormal_values} /><Stat label="Doses logged" value={m.doses_logged} /><Stat label="Vital alerts" value={m.vital_alerts} /><Stat label="Appointments" value={m.appointments} /></div>
          <p className="mt-3 text-xs text-slate-500">Activity: {Object.entries(m.activity).map(([k, v]) => `${k} ${v}`).join(" · ") || "none"}</p>
          <button className="btn-ghost mt-3" onClick={() => window.print()}>Print / save as PDF</button>
        </Card>
      )}
    </>
  );
}

function Population() {
  const { user } = useAuth();
  const [pop, setPop] = useState(null);
  const [f, setF] = useState({ age: 65, admissions_last_year: 1, chronic_conditions: 2, length_of_stay: 4, emergency_admission: false });
  const [res, setRes] = useState(null);
  const { error, run } = useAsync();
  useEffect(() => { run(async () => setPop(await api("/analytics/population"))); }, []);
  const calc = (e) => { e.preventDefault(); run(async () => setRes(await api("/analytics/readmission-risk", { method: "POST", body: { ...f, age: +f.age, admissions_last_year: +f.admissions_last_year, chronic_conditions: +f.chronic_conditions, length_of_stay: +f.length_of_stay } }))); };
  return (
    <>
      <h1 className="text-xl font-bold">Population health analytics</h1><Alert tone="error">{error}</Alert>
      {pop && (
        <div className="grid gap-4 md:grid-cols-2">
          <Card title="AI risk distribution (all patients, de-identified)">{Object.keys(pop.risk_distribution).length === 0 ? <Empty>No assessments yet.</Empty> : <table className="w-full text-sm"><thead className="text-left text-xs uppercase text-slate-500"><tr><th>Disease</th><th>Low</th><th>Mod</th><th>High</th></tr></thead><tbody>{Object.entries(pop.risk_distribution).map(([k, v]) => <tr key={k}><td className="capitalize">{k}</td><td>{v.low}</td><td>{v.moderate}</td><td className="font-semibold text-red-700">{v.high}</td></tr>)}</tbody></table>}</Card>
          <Card title="Appointments"><p className="text-sm">Trend: <b>{arrow(pop.appointment_trend)}</b></p><ul className="mt-2 text-sm">{Object.entries(pop.appointments_by_specialization).map(([k, v]) => <li key={k}>{k}: {v}</li>)}</ul><p className="mt-2 text-xs text-slate-500">7-day forecast: {pop.appointments_forecast_7d.join(", ") || "n/a"}</p></Card>
        </div>
      )}
      {["admin", "super_admin", "hospital", "doctor"].includes(user.role) && (
        <Card title="30-day readmission risk">
          <form onSubmit={calc} className="grid gap-3 md:grid-cols-5">
            <Field label="Age"><input className="input" type="number" value={f.age} onChange={(e) => setF({ ...f, age: e.target.value })} /></Field>
            <Field label="Admissions last year"><input className="input" type="number" value={f.admissions_last_year} onChange={(e) => setF({ ...f, admissions_last_year: e.target.value })} /></Field>
            <Field label="Chronic conditions"><input className="input" type="number" value={f.chronic_conditions} onChange={(e) => setF({ ...f, chronic_conditions: e.target.value })} /></Field>
            <Field label="Length of stay (days)"><input className="input" type="number" value={f.length_of_stay} onChange={(e) => setF({ ...f, length_of_stay: e.target.value })} /></Field>
            <label className="flex items-end gap-2 pb-2 text-sm"><input type="checkbox" checked={f.emergency_admission} onChange={(e) => setF({ ...f, emergency_admission: e.target.checked })} />Emergency admission</label>
            <div className="md:col-span-5"><button className="btn-primary">Calculate</button></div>
          </form>
          {res && <p className="mt-3 text-sm">Score <b>{res.score}</b> · <Badge tone={res.level === "high" ? "bad" : res.level === "moderate" ? "warn" : "good"}>{res.level}</Badge> <span className="text-xs text-slate-500">{res.scale}</span></p>}
        </Card>
      )}
    </>
  );
}
