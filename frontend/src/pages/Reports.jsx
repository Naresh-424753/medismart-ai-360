import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api.js";
import { Alert, Badge, Card, Disclaimer, Field, useAsync } from "../components/ui.jsx";

const fmt = (n) => (n >= 1000 ? n.toLocaleString("en-IN") : n);
const tone = (f) => (f.status === "normal" ? "good" : f.severity === "critical" ? "bad" : "warn");

export default function Reports() {
  const [file, setFile] = useState(null);
  const [text, setText] = useState("");
  const [title, setTitle] = useState("Lab report");
  const [out, setOut] = useState(null);
  const [past, setPast] = useState([]);
  const [trend, setTrend] = useState(null);
  const { busy, error, run } = useAsync();

  const loadPast = () => api("/reports").then(setPast).catch(() => {});
  useEffect(() => { loadPast(); }, []);

  const submit = (e) => {
    e.preventDefault();
    run(async () => {
      let r;
      if (file) {
        const form = new FormData();
        form.append("file", file);
        form.append("title", title);
        r = await api("/reports/upload", { method: "POST", form });
      } else {
        r = await api("/reports/analyze", { method: "POST", body: { text, title } });
      }
      setOut(r); setTrend(null); loadPast();
    });
  };
  const showTrend = (key) => run(async () => setTrend(await api(`/reports/trend/${key}`)));

  return (
    <>
      <h1 className="text-xl font-bold">AI medical report analyzer</h1>
      <Card title="Analyze a report">
        <form onSubmit={submit} className="space-y-3">
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="Title"><input className="input" value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
            <Field label="PDF, photo (OCR) or .txt — CBC, LFT, KFT, lipid, thyroid, sugar, vitamins, urine">
              <input className="input" type="file" accept=".pdf,.png,.jpg,.jpeg,.txt" onChange={(e) => setFile(e.target.files[0] || null)} />
            </Field>
          </div>
          <Field label="…or paste report text (e.g. “Hemoglobin 11.2 g/dL”)">
            <textarea className="input h-24" value={text} onChange={(e) => setText(e.target.value)} disabled={!!file} />
          </Field>
          <Alert tone="error">{error}</Alert>
          <button className="btn-primary" disabled={busy || (!file && !text.trim())}>{busy ? "Reading…" : "Analyze"}</button>
        </form>
      </Card>

      {out && (
        <Card title={out.title}>
          <Alert tone={out.abnormal_count ? "warn" : "ok"}>{out.summary}</Alert>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-500"><tr><th className="py-2">Test</th><th>Value</th><th>Range</th><th>Status</th><th /></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {out.findings.map((f) => (
                  <tr key={f.key} className={f.status !== "normal" ? "bg-amber-50/60" : ""}>
                    <td className="py-2 font-medium">{f.test}</td>
                    <td>{fmt(f.value)} {f.unit}</td>
                    <td className="text-slate-500">{fmt(f.low)} – {fmt(f.high)}</td>
                    <td><Badge tone={tone(f)}>{f.status}{f.status !== "normal" ? ` · ${f.severity}` : ""}</Badge></td>
                    <td><button className="text-xs text-brand-700 underline" onClick={() => showTrend(f.key)}>trend</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ul className="mt-3 space-y-1 text-sm text-slate-700">
              {out.findings.filter((f) => f.status !== "normal").map((f) => <li key={f.key}><b>{f.test}:</b> {f.note}</li>)}
            </ul>
          </div>
          {out.comparison?.length > 0 && (
            <div className="mt-4 border-t pt-3">
              <p className="label">Compared with your previous values</p>
              <ul className="text-sm">{out.comparison.map((c) => <li key={c.test}>{c.test}: {fmt(c.previous)} → {fmt(c.current)} <Badge tone={c.trend === "improved" ? "good" : c.trend === "worsened" ? "bad" : "muted"}>{c.trend}{c.percent != null ? ` ${c.percent}%` : ""}</Badge></li>)}</ul>
            </div>
          )}
          <div className="mt-3"><Disclaimer /></div>
        </Card>
      )}

      {trend && (
        <Card title={`Trend: ${trend.test} (${trend.unit})`} action={<button className="btn-ghost py-1" onClick={() => setTrend(null)}>Close</button>}>
          {trend.points.length < 2 ? <p className="text-sm text-slate-500">Analyze at least two reports containing this test to see a trend.</p> : (
            <div className="h-60" role="img" aria-label="Trend chart">
              <ResponsiveContainer>
                <LineChart data={trend.points}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <ReferenceArea y1={trend.low} y2={trend.high} fill="#10b981" fillOpacity={0.08} />
                  <XAxis dataKey="date" tick={{ fontSize: 12 }} /><YAxis tick={{ fontSize: 12 }} domain={["auto", "auto"]} />
                  <Tooltip /><Line type="monotone" dataKey="value" stroke="#047857" strokeWidth={2} dot />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      )}

      <Card title="Previous reports">
        {past.length === 0 && <p className="text-sm text-slate-500">None yet.</p>}
        <ul className="divide-y divide-slate-100 text-sm">
          {past.map((p) => <li key={p.id} className="py-2"><b>{p.report_date}</b> · {p.title} {p.lab_verified && <Badge tone="good">lab verified</Badge>} <span className="text-slate-500">— {p.summary}</span></li>)}
        </ul>
      </Card>
    </>
  );
}
