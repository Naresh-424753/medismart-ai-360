import { useEffect, useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api.js";
import { Alert, Badge, Card, Empty, Stat, useAsync } from "../components/ui.jsx";

const STATUS = { supported: "good", needs_setup: "warn", retired: "muted" };

export default function Wearables() {
  const [sum, setSum] = useState(null);
  const [prov, setProv] = useState([]);
  const [days, setDays] = useState(7);
  const [info, setInfo] = useState("");
  const [key, setKey] = useState(null);
  const file = useRef();
  const { busy, error, run } = useAsync();
  const load = () => api(`/wearables/summary?days=${days}`).then(setSum).catch(() => {});
  useEffect(() => { load(); }, [days]); // eslint-disable-line
  useEffect(() => { api("/wearables/providers").then(setProv).catch(() => {}); }, []);

  const importApple = (e) => {
    e.preventDefault();
    const f = file.current.files[0];
    if (!f) return;
    run(async () => {
      const form = new FormData(); form.append("file", f);
      const r = await api("/wearables/import/apple-health?days=30", { method: "POST", form });
      setInfo(`Imported ${r.new} new readings (${r.duplicates} already present, ${r.skipped_invalid} invalid skipped${r.truncated ? ", older data truncated" : ""}).`);
      file.current.value = ""; load();
    });
  };
  const newKey = () => run(async () => setKey(await api("/vitals/devices", { method: "POST", body: { label: "Phone bridge" } })));
  const wipe = () => window.confirm("Delete all wearable data stored in MediSmart?") && run(async () => { await api("/wearables/data", { method: "DELETE" }); setInfo("Wearable data deleted."); load(); });

  const d = sum?.daily || [];
  return (
    <>
      <h1 className="text-xl font-bold">Wearables & activity</h1>
      <Alert tone="info">Fitbit's old cloud API shut down on 30 Oct 2026 and Google Fit is being retired, so data now arrives through your phone's health store (Health Connect on Android, Apple Health on iPhone).</Alert>
      {sum && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Latest heart rate" value={sum.latest_heart_rate ? `${sum.latest_heart_rate.bpm} bpm` : "—"} sub={sum.latest_heart_rate && new Date(sum.latest_heart_rate.ts).toLocaleString()} />
          <Stat label="Avg steps / day" value={sum.averages.steps?.toLocaleString()} />
          <Stat label="Avg sleep (h)" value={sum.averages.sleep_hours} />
          <Stat label="Sources" value={sum.sources.length || "—"} sub={sum.sources.join(", ")} />
        </div>
      )}
      <div className="flex items-center gap-2 text-sm"><span>Show</span>{[7, 14, 30].map((n) => <button key={n} onClick={() => setDays(n)} className={`rounded-full border px-3 py-1 ${days === n ? "border-brand-600 bg-brand-50 text-brand-700" : "border-slate-300"}`}>{n} days</button>)}</div>
      {sum && !sum.has_data && <Card><Empty>No wearable data yet. Connect a source below.</Empty></Card>}
      {sum?.has_data && (
        <div className="grid gap-4 md:grid-cols-2">
          <Card title="Steps"><div className="h-48"><ResponsiveContainer><BarChart data={d}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="date" tickFormatter={(x) => x.slice(5)} fontSize={11} /><YAxis fontSize={11} /><Tooltip /><Bar dataKey="steps" fill="#059669" /></BarChart></ResponsiveContainer></div></Card>
          <Card title="Sleep (hours)"><div className="h-48"><ResponsiveContainer><BarChart data={d}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="date" tickFormatter={(x) => x.slice(5)} fontSize={11} /><YAxis fontSize={11} /><Tooltip /><Bar dataKey="sleep_hours" fill="#6366f1" /></BarChart></ResponsiveContainer></div></Card>
          <Card title="Heart rate (daily avg / min / max)"><div className="h-48"><ResponsiveContainer><LineChart data={d}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="date" tickFormatter={(x) => x.slice(5)} fontSize={11} /><YAxis domain={["auto", "auto"]} fontSize={11} /><Tooltip /><Line dataKey="hr_avg" stroke="#dc2626" /><Line dataKey="hr_min" stroke="#94a3b8" dot={false} /><Line dataKey="hr_max" stroke="#f59e0b" dot={false} /></LineChart></ResponsiveContainer></div></Card>
          <Card title="Activity"><div className="h-48"><ResponsiveContainer><BarChart data={d}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="date" tickFormatter={(x) => x.slice(5)} fontSize={11} /><YAxis fontSize={11} /><Tooltip /><Bar dataKey="active_minutes" name="active minutes" fill="#0ea5e9" /><Bar dataKey="calories" name="kcal" fill="#f97316" /></BarChart></ResponsiveContainer></div></Card>
        </div>
      )}
      <Alert tone="ok">{info}</Alert><Alert tone="error">{error}</Alert>
      <Card title="Connect a data source">
        <ul className="mb-4 space-y-2 text-sm">{prov.map((p) => <li key={p.id} className="flex flex-wrap items-start justify-between gap-2"><span><b>{p.name}</b><br /><span className="text-xs text-slate-500">{p.how}</span></span><Badge tone={STATUS[p.status]}>{p.status.replace("_", " ")}</Badge></li>)}</ul>
        <div className="grid gap-4 md:grid-cols-2">
          <form onSubmit={importApple} className="space-y-2 rounded-lg border border-slate-200 p-3 text-sm">
            <p className="font-semibold">Apple Health / Apple Watch</p>
            <p className="text-xs text-slate-500">iPhone: Health app → profile picture → Export All Health Data → upload the .zip here (up to 100 MB; last 30 days are imported).</p>
            <input ref={file} type="file" accept=".zip,.xml" className="text-sm" />
            <button className="btn-primary" disabled={busy}>{busy ? "Importing…" : "Import"}</button>
          </form>
          <div className="space-y-2 rounded-lg border border-slate-200 p-3 text-sm">
            <p className="font-semibold">Android Health Connect / other apps</p>
            <p className="text-xs text-slate-500">A small bridge app on your phone sends readings with this key. It works with any watch that writes to Health Connect.</p>
            <button className="btn-ghost" onClick={newKey} disabled={busy}>Create device key</button>
            {key && <div className="space-y-1"><p className="break-all rounded bg-amber-50 p-2 font-mono text-xs">{key.api_key}</p><p className="text-xs text-slate-500">Shown once. Send <code>POST /wearables/ingest</code> with header <code>X-Device-Key</code> and body <code>{'{"source":"health_connect","samples":[{"type":"heart_rate","value":72,"ts":"2026-11-03T10:00:00Z"}]}'}</code>. Types: heart_rate, resting_heart_rate, spo2, temperature, respiratory_rate, steps, sleep_minutes, active_minutes, calories, distance_m.</p></div>}
          </div>
        </div>
        <button className="mt-4 text-xs text-red-600 underline" onClick={wipe}>Delete all my wearable data</button>
      </Card>
    </>
  );
}
