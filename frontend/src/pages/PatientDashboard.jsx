import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import Icon from "../components/Icon.jsx";
import SosButton from "../components/SosButton.jsx";
import { Badge, Card, Empty, toneFor } from "../components/ui.jsx";
import { initials } from "../components/Layout.jsx";

const TILE = { blue: "bg-blue-50 text-blue-600", green: "bg-emerald-50 text-emerald-600", amber: "bg-amber-50 text-amber-600", red: "bg-red-50 text-red-600", purple: "bg-violet-50 text-violet-600", teal: "bg-cyan-50 text-cyan-600" };

function StatCard({ icon, tone, label, value, sub, to }) {
  const body = (
    <div className="card flex h-full flex-col gap-2 p-4 transition hover:shadow-md">
      <span className={`flex h-10 w-10 items-center justify-center rounded-full ${TILE[tone]}`}><Icon name={icon} /></span>
      <p className="text-sm text-slate-600">{label}</p>
      <p className="text-3xl font-bold text-slate-900">{value ?? "—"}</p>
      <p className="text-xs text-slate-500">{sub}</p>
    </div>
  );
  return to ? <Link to={to}>{body}</Link> : body;
}

function Ring({ value, min, max, safeLo, safeHi, unit, label, color, display }) {
  const has = value != null;
  const pct = has ? Math.max(0.04, Math.min(1, (value - min) / (max - min))) : 0;
  const R = 42, C = 2 * Math.PI * R;
  const out = has && (value < safeLo || value > safeHi);
  return (
    <div className="flex flex-col items-center text-center">
      <div className="relative h-24 w-24">
        <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
          <circle cx="50" cy="50" r={R} fill="none" stroke="#e2e8f0" strokeWidth="8" />
          {has && <circle cx="50" cy="50" r={R} fill="none" stroke={out ? "#dc2626" : color} strokeWidth="8" strokeLinecap="round" strokeDasharray={`${pct * C} ${C}`} />}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center"><span className="text-lg font-bold leading-none">{has ? display ?? value : "—"}</span><span className="text-[10px] text-slate-500">{unit}</span></div>
      </div>
      <p className="mt-1 text-sm font-medium">{label}</p>
      <p className="text-[11px] text-slate-500">({safeLo} - {safeHi})</p>
    </div>
  );
}

// Transparent, non-clinical score computed only from this user's own data.
function healthScore({ latest, alerts, risks, sched }) {
  if (!latest && risks.length === 0 && sched.length === 0 && alerts.length === 0) return null;
  let s = 100;
  s -= Math.min(30, alerts.length * 10);
  s -= Math.min(30, risks.filter((r) => r.level === "high").length * 10 + risks.filter((r) => r.level === "moderate").length * 5);
  s -= Math.min(20, sched.filter((d) => d.status === "missed").length * 5);
  if (latest?.status === "critical") s -= 20; else if (latest?.status === "warning") s -= 10;
  return Math.max(0, s);
}

const TIPS = [["Maintain a balanced diet with more vegetables", "apple", "bg-emerald-100 text-emerald-600"], ["Daily walk for at least 30 minutes", "walk", "bg-sky-100 text-sky-600"], ["Stay hydrated (2-3 litres water daily)", "drop", "bg-blue-100 text-blue-600"], ["Get 7-8 hours of quality sleep", "moon", "bg-indigo-100 text-indigo-600"]];
const QUICK = [["/risk", "AI Diagnosis", "brain", "bg-violet-50 text-violet-700"], ["/reports", "Upload Report", "file", "bg-blue-50 text-blue-700"], ["/appointments", "Book Appointment", "calendar", "bg-emerald-50 text-emerald-700"], ["/medicines", "Order Medicine", "pill", "bg-orange-50 text-orange-700"], ["/emergency", "Emergency SOS", "alert", "bg-red-50 text-red-700"], ["/hospitals", "Find Hospital", "building", "bg-cyan-50 text-cyan-700"]];
const FEATURES = [["AI Disease Prediction", "Check disease risk based on your symptoms", "Try Now", "/risk", "brain", "bg-violet-50 text-violet-600"], ["Medical Report Analyzer", "Upload and analyze your medical reports", "Upload Report", "/reports", "file", "bg-blue-50 text-blue-600"], ["AI Healthcare Chatbot", "24/7 support in your language", "Chat Now", "/chat", "chat", "bg-indigo-50 text-indigo-600"], ["Nearby Hospitals", "Find hospitals near you", "Search Now", "/hospitals", "pulse", "bg-emerald-50 text-emerald-600"], ["Medicine Reminder", "Never miss your medicine", "Set Reminder", "/medicines", "bell", "bg-orange-50 text-orange-600"]];

export default function PatientDashboard() {
  const { user } = useAuth();
  const [profile, setProfile] = useState(null);
  const [sched, setSched] = useState([]);
  const [appts, setAppts] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [notes, setNotes] = useState([]);
  const [risks, setRisks] = useState([]);
  const [latest, setLatest] = useState(null);
  const [reports, setReports] = useState([]);
  const [meds, setMeds] = useState([]);
  const [hist, setHist] = useState([]);
  const [hours, setHours] = useState(168);
  const [prevent, setPrevent] = useState([]);
  const [rxNew, setRxNew] = useState(null);

  const load = () => {
    api("/patients/me").then(setProfile).catch(() => {});
    api("/medicines/today").then((r) => setSched(r.schedule || [])).catch(() => {});
    api("/appointments").then((a) => setAppts(a.filter((x) => ["booked", "confirmed"].includes(x.status)))).catch(() => {});
    api("/vitals/alerts").then(setAlerts).catch(() => {});
    api("/patients/me/notifications").then(setNotes).catch(() => {});
    api("/ai/risk-history").then(setRisks).catch(() => {});
    api("/vitals/latest").then(setLatest).catch(() => {});
    api("/reports").then(setReports).catch(() => {});
    api("/medicines").then(setMeds).catch(() => {});
    api("/prescriptions").then((r) => setRxNew(r.find((x) => !x.ordered && Date.now() - new Date(x.created_at).getTime() < 14 * 864e5) || null)).catch(() => {});
    api("/analytics/my-health?days=14").then((r) => setPrevent(r.preventive_alerts || [])).catch(() => {});
  };
  useEffect(load, []);
  useEffect(() => { api(`/vitals/history?hours=${hours}&limit=2000`).then(setHist).catch(() => setHist([])); }, [hours]);
  const take = async (d) => { await api(`/medicines/${d.med_id}/taken`, { method: "POST", body: { time: d.time } }); load(); };

  const lastRisk = Object.values(risks.reduce((m, r) => (m[r.disease] ? m : { ...m, [r.disease]: r }), {}));
  const recentAlerts = alerts.filter((a) => Date.now() - new Date(a.ts).getTime() < 7 * 864e5);
  const score = healthScore({ latest, alerts: recentAlerts, risks: lastRisk, sched });
  const dueToday = sched.filter((d) => d.status !== "taken").length;
  const unread = notes.filter((n) => !n.read);

  const chart = useMemo(() => {
    const by = {};
    const fmt = hours <= 24 ? (t) => t.slice(11, 16) : (t) => t.slice(5, 10);
    hist.forEach((r) => {
      const k = fmt(r.ts);
      const b = (by[k] ||= { k, hr: [], sp: [], tp: [] });
      if (r.heart_rate != null) b.hr.push(r.heart_rate);
      if (r.spo2 != null) b.sp.push(r.spo2);
      if (r.temperature != null) b.tp.push(r.temperature);
    });
    const avg = (a) => (a.length ? Math.round((a.reduce((x, y) => x + y, 0) / a.length) * 10) / 10 : null);
    return Object.values(by).map((b) => ({ k: b.k, "Heart rate": avg(b.hr), SpO2: avg(b.sp), "Temperature ×3": avg(b.tp) != null ? Math.round(avg(b.tp) * 3 * 10) / 10 : null }));
  }, [hist, hours]);

  const insights = [
    ...prevent,
    ...lastRisk.filter((r) => r.level !== "low").map((r) => `Your ${r.disease} screening is ${r.level} risk - consider discussing it with a doctor.`),
    ...(latest && latest.status !== "normal" ? [`Latest vitals are flagged "${latest.status}". Re-check or consult a doctor.`] : []),
  ].slice(0, 4);
  const good = insights.length === 0;

  return (
    <>
      <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
        <div className="min-w-0 space-y-4">
          <section className="card flex flex-wrap items-center gap-4 bg-gradient-to-r from-white to-blue-50 p-5">
            <span className="flex h-20 w-20 items-center justify-center rounded-full bg-brand-100 text-2xl font-bold text-brand-700 ring-4 ring-white">{initials(user.name)}</span>
            <div className="min-w-0 flex-1">
              <h1 className="text-2xl font-bold text-slate-900">Welcome Back, {user.name}</h1>
              <p className="text-sm text-slate-600">Take control of your health with AI-powered insights and personalized care.</p>
              <p className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-600">
                <span>Patient ID: <b>{profile?.health_id || "—"}</b></span>
                <span>Age: <b>{profile?.age ?? "—"}</b></span>
                <span>Blood Group: <b>{profile?.blood_group || "—"}</b></span>
                {user.email_verified !== false && <Badge tone="good">✔ Verified</Badge>}
              </p>
            </div>
            <div className="flex items-center gap-3"><SosButton /></div>
          </section>

          {rxNew && <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-brand-100 bg-brand-50 px-4 py-3 text-sm"><span><b>New prescription from Dr. {rxNew.doctor_name}.</b> Order {rxNew.items.map((i) => i.name).join(", ")} from a nearby partner pharmacy.</span><Link className="btn-primary" to={`/medicines?rx=${rxNew.id}`}>Order medicines</Link></div>}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <StatCard icon="calendar" tone="blue" label="Upcoming Appointments" value={appts.length} sub={appts[0] ? `Next: ${appts[0].date} ${appts[0].time}` : "None booked"} to="/appointments" />
            <StatCard icon="file" tone="blue" label="Medical Reports" value={reports.length} sub="uploaded & analysed" to="/reports" />
            <StatCard icon="pill" tone="amber" label="Medicines" value={meds.length} sub={sched.length ? `${dueToday} dose(s) left today` : "no doses today"} to="/medicines" />
            <StatCard icon="heart" tone="red" label="Health Alerts" value={recentAlerts.length} sub={recentAlerts.length ? "in the last 7 days" : "All normal"} to="/vitals" />
            <div title="Computed from your recent vital alerts, risk checks, missed doses and latest vitals. It is not a clinical score.">
              <StatCard icon="shield" tone="green" label="Health Score" value={score != null ? `${score}%` : "—"} sub={score != null ? "from your own data" : "add vitals / checks"} to="/analytics" />
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Health Vitals" action={latest && <Badge tone={toneFor(latest.status)}>{latest.status === "normal" ? "All vitals normal" : latest.status}</Badge>}>
              <p className="-mt-2 mb-3 text-xs text-slate-500">{latest ? `Last updated ${new Date(latest.ts).toLocaleString()}` : "No readings yet"}</p>
              {!latest ? <Empty>Add a manual reading or pair a device on the <Link to="/vitals" className="text-brand-700 underline">Vitals</Link> page.</Empty> : (
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <Ring label="Heart Rate" value={latest.heart_rate} min={40} max={160} safeLo={60} safeHi={100} unit="bpm" color="#ef4444" />
                  <Ring label="SpO2" value={latest.spo2} min={80} max={100} safeLo={95} safeHi={100} unit="%" color="#2563eb" />
                  <Ring label="Temperature" value={latest.temperature} min={34} max={41} safeLo={36.1} safeHi={37.2} unit="°C" color="#f59e0b" />
                  <Ring label="Blood Pressure" value={latest.systolic} min={80} max={180} safeLo={90} safeHi={120} unit="mmHg" color="#7c3aed" display={latest.systolic ? `${latest.systolic}/${latest.diastolic ?? "–"}` : null} />
                </div>
              )}
            </Card>
            <Card title="Health Analytics" action={<select aria-label="Period" value={hours} onChange={(e) => setHours(+e.target.value)} className="rounded-lg border border-slate-300 px-2 py-1 text-sm"><option value={24}>Last 24 hours</option><option value={168}>Last 7 days</option><option value={720}>Last 30 days</option></select>}>
              {chart.length === 0 ? <Empty>No readings in this period.</Empty> : (
                <div className="h-52"><ResponsiveContainer><LineChart data={chart}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="k" fontSize={11} /><YAxis fontSize={11} domain={["auto", "auto"]} /><Tooltip /><Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line dataKey="Heart rate" stroke="#ef4444" dot={false} connectNulls /><Line dataKey="SpO2" stroke="#2563eb" dot={false} connectNulls /><Line dataKey="Temperature ×3" stroke="#f59e0b" dot={false} connectNulls /></LineChart></ResponsiveContainer></div>
              )}
              <p className="mt-1 text-[10px] text-slate-400">Temperature is multiplied by 3 so it fits the same axis.</p>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
            <Card title="AI Health Insights" action={<span className="text-xs text-slate-400">Based on your recent data</span>}>
              <div className="grid gap-3 md:grid-cols-2">
                <div className={`rounded-xl p-4 ${good ? "bg-emerald-50" : "bg-amber-50"}`}>
                  <p className={`flex items-center gap-2 font-semibold ${good ? "text-emerald-700" : "text-amber-700"}`}><span className={`flex h-6 w-6 items-center justify-center rounded-full text-white ${good ? "bg-emerald-500" : "bg-amber-500"}`}><Icon name={good ? "check" : "alert"} className="h-4 w-4" /></span>{good ? "Good Health Status" : "Needs Attention"}</p>
                  <p className="mt-2 text-sm text-slate-600">{good ? "Nothing flagged in your recent data. Keep maintaining your healthy lifestyle!" : "Some of your recent data was flagged:"}</p>
                  {!good && <ul className="mt-1 list-disc space-y-1 pl-5 text-xs text-slate-700">{insights.map((t, i) => <li key={i}>{t}</li>)}</ul>}
                  <Link to="/analytics" className="btn-primary mt-3">View Detailed Report</Link>
                </div>
                <div><p className="mb-2 text-sm font-semibold text-brand-700">General wellness reminders</p>
                  <ul className="space-y-2">{TIPS.map(([t, ic, c]) => <li key={t} className="flex items-center gap-2 text-xs text-slate-600"><span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${c}`}><Icon name={ic} className="h-4 w-4" /></span>{t}</li>)}</ul></div>
              </div>
            </Card>
            <Card title="Upcoming Appointments" action={<Link to="/appointments" className="text-sm text-brand-700">View All</Link>}>
              {appts.length === 0 && <Empty>Nothing booked.</Empty>}
              <ul className="space-y-2">{appts.slice(0, 2).map((a) => (
                <li key={a.id} className="flex items-center gap-3 rounded-xl border border-slate-200 p-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-100 text-sm font-bold text-brand-700">{initials(a.doctor_name)}</span>
                  <div className="min-w-0 flex-1 text-sm"><p className="truncate font-semibold">Dr. {a.doctor_name}</p><p className="text-xs text-slate-500">{a.specialization || "Doctor"}</p><p className="text-xs text-slate-500">{a.date} | {a.time}</p></div>
                  <div className="flex flex-col items-end gap-1"><Badge tone={a.status === "confirmed" ? "good" : "info"}>{a.status}</Badge><Link className="text-xs text-brand-700 underline" to={`/call/${a.id}`}>Join call</Link></div>
                </li>))}</ul>
              <Link to="/appointments" className="btn-primary mt-3 w-full"><Icon name="calendar" className="h-4 w-4" />Book New Appointment</Link>
            </Card>
          </div>

          <Card title="Today's medicines" action={<Link to="/medicines" className="text-sm text-brand-700">All</Link>}>
            {sched.length === 0 && <Empty>No doses scheduled today.</Empty>}
            <ul className="divide-y divide-slate-100">{sched.slice(0, 6).map((d) => (
              <li key={`${d.med_id}${d.time}`} className="flex items-center justify-between py-2 text-sm"><span><b>{d.time}</b> · {d.name} {d.dose}</span>
                {d.status === "taken" ? <Badge tone="good">taken</Badge> : <span className="flex items-center gap-2"><Badge tone={toneFor(d.status)}>{d.status}</Badge><button className="btn-ghost py-1" onClick={() => take(d)}>Mark taken</button></span>}</li>))}</ul>
          </Card>
        </div>

        <aside className="space-y-4">
          <Card title="Recent Notifications" action={<span className="text-xs text-slate-400">{unread.length} unread</span>}>
            {notes.length === 0 && <Empty>No notifications.</Empty>}
            <ul className="divide-y divide-slate-100">{notes.slice(0, 4).map((n) => {
              const bad = ["vital_alert", "emergency"].includes(n.kind);
              return <li key={n.id} className="flex gap-3 py-2.5"><span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${bad ? "bg-red-50 text-red-600" : "bg-blue-50 text-blue-600"}`}><Icon name={bad ? "alert" : "bell"} className="h-4 w-4" /></span><div className="min-w-0 text-sm"><p className="font-medium">{n.title}</p><p className="text-xs text-slate-600">{n.body}</p><p className="text-[10px] text-slate-400">{n.ts?.replace("T", " ").slice(0, 16)} UTC</p></div></li>;
            })}</ul>
          </Card>
          <Card title="Quick Actions">
            <div className="grid grid-cols-2 gap-3">{QUICK.map(([to, l, ic, c]) => <Link key={to} to={to} className={`flex h-24 flex-col items-center justify-center gap-2 rounded-xl text-center text-sm font-medium transition hover:shadow-md ${c}`}><Icon name={ic} className="h-6 w-6" />{l}</Link>)}</div>
          </Card>
          {lastRisk.length > 0 && <Card title="Risk overview" action={<Link to="/risk" className="text-sm text-brand-700">Check</Link>}><ul className="space-y-1 text-sm">{lastRisk.map((r) => <li key={r.disease} className="flex justify-between capitalize"><span>{r.disease}</span><Badge tone={toneFor(r.level)}>{r.level}</Badge></li>)}</ul></Card>}
        </aside>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {FEATURES.map(([t, d, b, to, ic, c]) => (
          <div key={t} className="card flex items-start gap-3 p-4">
            <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${c}`}><Icon name={ic} /></span>
            <div className="min-w-0"><p className="text-sm font-semibold">{t}</p><p className="mb-2 text-xs text-slate-500">{d}</p><Link to={to} className="inline-block rounded-md bg-brand-600 px-3 py-1 text-xs font-medium text-white hover:bg-brand-700">{b}</Link></div>
          </div>
        ))}
      </div>
    </>
  );
}
