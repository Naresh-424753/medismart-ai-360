import { useEffect, useRef, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, tokenStore, wsUrl } from "../api.js";
import { Alert, Badge, Card, Empty, Field, toneFor, useAsync } from "../components/ui.jsx";

const METRICS = [["heart_rate", "Heart rate", "bpm"], ["spo2", "SpO₂", "%"], ["temperature", "Temperature", "°C"], ["systolic", "Systolic BP", "mmHg"], ["diastolic", "Diastolic BP", "mmHg"], ["respiratory_rate", "Resp. rate", "/min"], ["glucose", "Glucose", "mg/dL"]];

export default function Vitals() {
  const [live, setLive] = useState(null);
  const [hist, setHist] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [devices, setDevices] = useState([]);
  const [newKey, setNewKey] = useState(null);
  const [label, setLabel] = useState("ESP32 wearable");
  const [metric, setMetric] = useState("heart_rate");
  const [hours, setHours] = useState(24);
  const [form, setForm] = useState({});
  const [conn, setConn] = useState("connecting");
  const [ecg, setEcg] = useState(null);
  const ws = useRef(null);
  const { busy, error, run } = useAsync();

  const loadHist = () => api(`/vitals/history?hours=${hours}&limit=500`).then((r) => setHist(r.map((x) => ({ ...x, t: x.ts.slice(5, 16).replace("T", " ") })))).catch(() => {});
  const loadAll = () => { api("/vitals/latest").then(setLive).catch(() => {}); api("/vitals/alerts").then(setAlerts).catch(() => {}); api("/vitals/devices").then(setDevices).catch(() => {}); };
  useEffect(() => { loadAll(); }, []);
  useEffect(() => { loadHist(); }, [hours]);

  useEffect(() => {
    let closed = false, timer;
    const open = () => {
      const s = new WebSocket(wsUrl(`/vitals/ws?token=${encodeURIComponent(tokenStore.get())}`));
      ws.current = s;
      s.onopen = () => setConn("live");
      s.onmessage = (ev) => {
        const m = JSON.parse(ev.data);
        if (m.type !== "vitals") return;
        setLive(m.reading); if (m.ecg) setEcg(m.ecg.map((v, i) => ({ i, v })));
        setHist((h) => [...h.slice(-499), { ...m.reading, t: m.reading.ts.slice(5, 16).replace("T", " ") }]);
        if (m.alerts?.length) api("/vitals/alerts").then(setAlerts).catch(() => {});
      };
      s.onclose = () => { setConn("reconnecting"); if (!closed) timer = setTimeout(open, 3000); };
    };
    open();
    const ping = setInterval(() => ws.current?.readyState === 1 && ws.current.send("ping"), 25000);
    return () => { closed = true; clearTimeout(timer); clearInterval(ping); ws.current?.close(); };
  }, []);

  const submit = (e) => {
    e.preventDefault();
    const body = {};
    Object.entries(form).forEach(([k, v]) => { if (v !== "") body[k] = k === "fall_detected" ? !!v : Number(v); });
    run(async () => { await api("/vitals/manual", { method: "POST", body }); setForm({}); loadAll(); });
  };
  const addDevice = () => run(async () => { setNewKey(await api("/vitals/devices", { method: "POST", body: { label } })); loadAll(); });
  const rmDevice = (id) => run(async () => { await api(`/vitals/devices/${id}`, { method: "DELETE" }); loadAll(); });
  const api_base = import.meta.env.VITE_API_URL || "http://localhost:8000";

  return (
    <>
      <div className="flex items-center justify-between"><h1 className="text-xl font-bold">Live vitals</h1><Badge tone={conn === "live" ? "good" : "warn"}>{conn}</Badge></div>
      <Alert tone="error">{error}</Alert>
      {live && live.status !== "normal" && <Alert tone={live.status === "critical" ? "error" : "warn"}>Your latest reading is {live.status}. If you feel unwell, call 112 / 108.</Alert>}
      <Card title="Right now">
        {!live ? <Empty>No readings yet. Add one below or connect a device.</Empty> : (
          <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {METRICS.map(([k, l, u]) => <div key={k}><p className="text-xs text-slate-500">{l}</p><p className="text-xl font-semibold">{live[k] ?? "—"} <span className="text-xs font-normal text-slate-400">{live[k] != null ? u : ""}</span></p></div>)}
              <div><p className="text-xs text-slate-500">Steps / sleep</p><p className="text-xl font-semibold">{live.steps ?? "—"} / {live.sleep_hours ?? "—"}h</p></div>
            </div>
            <p className="mt-2 text-xs text-slate-400"><Badge tone={toneFor(live.status)}>{live.status}</Badge> {live.ts?.replace("T", " ").slice(0, 19)} UTC · source: {live.source}</p>
          </>
        )}
      </Card>
      {ecg && <Card title="ECG (latest samples)"><div className="h-32"><ResponsiveContainer><LineChart data={ecg}><Line type="monotone" dataKey="v" stroke="#047857" dot={false} strokeWidth={1.5} isAnimationActive={false} /><YAxis hide domain={["auto", "auto"]} /></LineChart></ResponsiveContainer></div><p className="text-xs text-slate-500">Educational display only, not a diagnostic ECG.</p></Card>}
      <Card title="Trend" action={<span className="flex gap-2"><select className="input w-auto py-1" value={metric} onChange={(e) => setMetric(e.target.value)}>{METRICS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select><select className="input w-auto py-1" value={hours} onChange={(e) => setHours(+e.target.value)}><option value={6}>6 h</option><option value={24}>24 h</option><option value={168}>7 days</option><option value={720}>30 days</option></select></span>}>
        <div className="h-56" role="img" aria-label="Vitals trend chart">
          <ResponsiveContainer><LineChart data={hist.filter((h) => h[metric] != null)}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="t" tick={{ fontSize: 11 }} minTickGap={40} /><YAxis tick={{ fontSize: 11 }} domain={["auto", "auto"]} /><Tooltip /><Line type="monotone" dataKey={metric} stroke="#047857" strokeWidth={2} dot={false} isAnimationActive={false} /></LineChart></ResponsiveContainer>
        </div>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Add a manual reading">
          <form onSubmit={submit} className="grid grid-cols-2 gap-2">
            {METRICS.map(([k, l, u]) => <Field key={k} label={`${l} (${u})`}><input className="input" type="number" step="any" value={form[k] ?? ""} onChange={(e) => setForm({ ...form, [k]: e.target.value })} /></Field>)}
            <Field label="Steps"><input className="input" type="number" min="0" value={form.steps ?? ""} onChange={(e) => setForm({ ...form, steps: e.target.value })} /></Field>
            <Field label="Sleep (h)"><input className="input" type="number" step="0.1" min="0" max="24" value={form.sleep_hours ?? ""} onChange={(e) => setForm({ ...form, sleep_hours: e.target.value })} /></Field>
            <label className="col-span-2 flex items-center gap-2 text-sm"><input type="checkbox" checked={!!form.fall_detected} onChange={(e) => setForm({ ...form, fall_detected: e.target.checked })} /> Simulate a fall</label>
            <div className="col-span-2"><button className="btn-primary" disabled={busy || !Object.values(form).some((v) => v !== "" && v !== false)}>Save reading</button></div>
          </form>
        </Card>
        <Card title="Alerts">
          {alerts.length === 0 && <Empty>No alerts.</Empty>}
          <ul className="max-h-72 space-y-1 overflow-y-auto text-sm">{alerts.slice(0, 30).map((a) => <li key={a.id}><Badge tone={toneFor(a.severity)}>{a.severity}</Badge> {a.message} <span className="text-xs text-slate-400">{a.ts.slice(5, 16).replace("T", " ")}</span></li>)}</ul>
        </Card>
      </div>
      <Card title="Wearable / ESP32 devices">
        <div className="flex flex-wrap items-end gap-2"><Field label="Device name"><input className="input" value={label} onChange={(e) => setLabel(e.target.value)} /></Field><button className="btn-primary" onClick={addDevice} disabled={busy}>Pair new device</button></div>
        {newKey && (
          <div className="mt-3 space-y-1 rounded-lg bg-amber-50 p-3 text-sm"><p className="font-semibold">Copy this key now — it is shown only once.</p><code className="block break-all rounded bg-white p-2">{newKey.api_key}</code>
            <p className="text-xs text-slate-600">Test it: <code>curl -X POST {api_base}/vitals/ingest -H "X-Device-Key: {newKey.api_key}" -H "Content-Type: application/json" -d '{`{"heart_rate":78,"spo2":97}`}'</code></p></div>
        )}
        <ul className="mt-3 divide-y divide-slate-100 text-sm">{devices.map((d) => <li key={d.id} className="flex items-center justify-between py-1.5"><span>{d.label} <span className="text-xs text-slate-400">last seen {d.last_seen ? d.last_seen.slice(0, 16).replace("T", " ") : "never"}</span></span><button className="btn-ghost py-1" onClick={() => rmDevice(d.id)}>Remove</button></li>)}</ul>
        <p className="mt-2 text-xs text-slate-500">Firmware and a simulator script are in the <code>hardware/</code> folder.</p>
      </Card>
    </>
  );
}
