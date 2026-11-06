import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Alert, Badge, Card, Empty, useAsync } from "../components/ui.jsx";

const TONE = { stable: "good", watch: "warn", high: "bad", critical: "bad", insufficient_data: "muted" };
const LABEL = { stable: "Stable", watch: "Watch", high: "High risk", critical: "Critical", insufficient_data: "Not enough data" };
const NOTE = "Screening aid. NEWS2 is a validated score; the 2-4 hour projection and anomaly flag are not clinically validated predictions. Use clinical judgement.";

function Assessment({ a }) {
  const p = a.projected || {};
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        <Badge tone={TONE[a.level]}>{LABEL[a.level]}</Badge>
        {a.score_now != null && <span>NEWS2 now <b>{a.score_now}</b></span>}
        {p["2h"] && <span>in 2 h <b>{p["2h"].score}</b></span>}
        {p["4h"] && <span>in 4 h <b>{p["4h"].score}</b></span>}
        {a.eta_to_urgent_hours != null && a.score_now < 5 && <span className="text-red-700">urgent threshold (5) in ~{a.eta_to_urgent_hours} h</span>}
        <span className="text-xs text-slate-500">confidence: {a.confidence} · {a.readings_used} readings</span>
      </div>
      {a.current && Object.keys(a.current).length > 0 && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {Object.entries(a.current).map(([k, v]) => (
            <div key={k} className="rounded-lg bg-slate-50 p-2"><p className="text-[11px] capitalize text-slate-500">{k.replace("_", " ")}</p><p className="font-semibold">{v}{p["4h"]?.values?.[k] != null && <span className="ml-1 text-xs font-normal text-slate-500">→ {p["4h"].values[k]} (4h)</span>}</p></div>
          ))}
        </div>
      )}
      {a.reasons?.length > 0 && <ul className="list-disc space-y-1 pl-5 text-slate-700">{a.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>}
      <p className="text-xs text-slate-400">{NOTE}</p>
    </div>
  );
}

function PatientView() {
  const [d, setD] = useState(null);
  const { busy, error, run } = useAsync();
  const [info, setInfo] = useState("");
  const load = () => api("/ews/me").then(setD).catch(() => {});
  useEffect(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t); }, []);
  const toggle = (v) => run(async () => { await api("/ews/me/settings", { method: "PUT", body: { share_with_care_team: v } }); load(); });
  const demo = () => run(async () => { await api("/ews/demo/deteriorating", { method: "POST" }); setInfo("Demo readings added (6 hours of slowly worsening vitals)."); load(); });
  const clear = () => run(async () => { await api("/ews/demo", { method: "DELETE" }); setInfo("Demo readings removed."); load(); });
  return (
    <>
      <h1 className="text-xl font-bold">Early Warning</h1>
      <Alert tone="error">{error}</Alert><Alert tone="ok">{info}</Alert>
      <Card title="Deterioration outlook">{!d ? <Empty>Loading…</Empty> : <Assessment a={d.assessment} />}</Card>
      <Card title="Care-team alerts">
        <p className="text-sm text-slate-600">When your risk becomes high, your doctors (with an appointment in the last 30 days) and the hospital you are admitted to get an alert by app notification and SMS (SMS needs a Twilio account configured on the server). Off by default.</p>
        <label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={!!d?.settings?.share_with_care_team} disabled={busy} onChange={(e) => toggle(e.target.checked)} />Share my early-warning status with my care team</label>
      </Card>
      <Card title="Recent alerts">
        {!d || d.events.length === 0 ? <Empty>No alerts yet.</Empty> : <ul className="divide-y divide-slate-100 text-sm">{d.events.map((e) => <li key={e.id} className="flex justify-between py-1.5"><span><Badge tone={TONE[e.level]}>{LABEL[e.level]}</Badge> NEWS2 {e.score_now}{e.projected_4h != null && ` → ${e.projected_4h} (4h)`} · {e.notified.length} clinician(s) notified</span><span className="text-xs text-slate-500">{e.ts.replace("T", " ").slice(0, 16)}</span></li>)}</ul>}
      </Card>
      <Card title="Try it (demo mode only)">
        <p className="mb-2 text-sm text-slate-600">Adds 6 hours of synthetic, slowly worsening readings so you can see a forecast and an alert. Disabled when DEV_MODE=0.</p>
        <div className="flex gap-2"><button className="btn-primary" onClick={demo} disabled={busy}>Add deteriorating demo data</button><button className="btn-ghost" onClick={clear} disabled={busy}>Remove demo data</button></div>
      </Card>
    </>
  );
}

function StaffView() {
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(null);
  const [perm, setPerm] = useState(typeof Notification !== "undefined" ? Notification.permission : "denied");
  const seen = useRef({});
  const load = () => api("/ews/watchlist").then((r) => {
    r.forEach((p) => {
      const prev = seen.current[p.patient_id];
      if (prev !== undefined && prev !== p.level && ["high", "critical"].includes(p.level) && typeof Notification !== "undefined" && Notification.permission === "granted")
        new Notification("MediSmart early warning", { body: `${p.name}: ${LABEL[p.level]} (NEWS2 ${p.score_now})` });
      seen.current[p.patient_id] = p.level;
    });
    setRows(r);
  }).catch(() => {});
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, []);
  return (
    <>
      <h1 className="text-xl font-bold">Early-warning watchlist</h1>
      <Alert tone="info">Only patients who enabled care-team sharing appear here. Each view is recorded on the patient's access ledger. Refreshes every 30 s.</Alert>
      {perm === "default" && <button className="btn-ghost" onClick={() => Notification.requestPermission().then(setPerm)}>Enable desktop notifications while this page is open</button>}
      <Card>
        {rows.length === 0 ? <Empty>No monitored patients.</Empty> : (
          <ul className="divide-y divide-slate-100">{rows.map((r) => (
            <li key={r.patient_id} className="py-3 text-sm">
              <button className="flex w-full flex-wrap items-center justify-between gap-2 text-left" onClick={() => setOpen(open === r.patient_id ? null : r.patient_id)}>
                <span className="font-semibold">{r.name}</span>
                <span className="flex items-center gap-3"><span>NEWS2 {r.score_now ?? "—"} → {r.projected_4h ?? "—"}</span>{r.eta_to_urgent_hours != null && r.score_now < 5 && <span className="text-xs text-red-700">~{r.eta_to_urgent_hours} h</span>}<Badge tone={TONE[r.level]}>{LABEL[r.level]}</Badge></span>
              </button>
              {open === r.patient_id && <div className="mt-2 rounded-lg bg-slate-50 p-3"><ul className="list-disc pl-5">{r.reasons.map((x, i) => <li key={i}>{x}</li>)}</ul><p className="mt-1 text-xs text-slate-400">{NOTE}</p></div>}
            </li>))}</ul>
        )}
      </Card>
    </>
  );
}

export default function EarlyWarning() {
  const { user } = useAuth();
  return user.role === "patient" ? <PatientView /> : <StaffView />;
}
