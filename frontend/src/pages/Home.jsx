import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Alert, Badge, Card, Empty, Stat, toneFor, useAsync } from "../components/ui.jsx";
import SosButton from "../components/SosButton.jsx";
import PatientDashboard from "./PatientDashboard.jsx";
import { AdminHome, AmbulanceHome, BloodBankHome, HospitalHome, LabHome, PharmacistHome } from "./Portals.jsx";

export default function Home() {
  const { user } = useAuth();
  switch (user.role) {
    case "patient": return <PatientDashboard />;
    case "doctor": return <DoctorHome />;
    case "family": return <FamilyHome />;
    case "pharmacist": return <PharmacistHome />;
    case "ambulance": return <AmbulanceHome />;
    case "hospital": return <HospitalHome />;
    case "lab": return <LabHome />;
    case "blood_bank": return <BloodBankHome />;
    case "admin":
    case "super_admin": return <AdminHome />;
    default: return <Card title={`Welcome, ${user.name}`}><Empty>No workspace for role “{user.role}”.</Empty></Card>;
  }
}

function DoctorHome() {
  const [dash, setDash] = useState(null);
  const [patients, setPatients] = useState([]);
  const [open, setOpen] = useState(null);
  const { error, run } = useAsync();
  useEffect(() => { run(async () => { setDash(await api("/doctor/dashboard")); setPatients(await api("/doctor/patients")); }); }, []);
  const view = (p) => run(async () => {
    const s = await api(`/patients/${p.user_id}/summary`);
    const reports = await api(`/patients/${p.user_id}/reports`).catch(() => []);
    const vit = await api(`/vitals/latest?patient_id=${p.user_id}`).catch(() => null);
    setOpen({ p, s, reports, vit });
  });
  return (
    <>
      <h1 className="text-xl font-bold">Doctor dashboard</h1>
      <Alert tone="error">{error}</Alert>
      {dash && !dash.approved && <Alert tone="warn">Your account is awaiting admin verification.</Alert>}
      {dash && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Stat label="Today" value={dash.today.length} />
          <Stat label="Patients" value={dash.stats.total_patients} />
          <Stat label="Completed" value={dash.stats.completed} />
          <Stat label="Avg rating" value={dash.stats.avg_rating} />
        </div>
      )}
      <Card title="Today's schedule" action={<Link to="/appointments" className="text-sm text-brand-700">Manage</Link>}>
        {dash?.today.length ? dash.today.map((a) => <p key={a.id} className="py-1 text-sm"><b>{a.time}</b> · {a.patient_name} · {a.reason || "—"} · <Badge tone="info">{a.status}</Badge>{a.video_url && <> · <a className="text-brand-700 underline" href={a.video_url} target="_blank" rel="noreferrer">video</a></>}</p>) : <Empty>No appointments today.</Empty>}
      </Card>
      <Card title="My patients">
        {patients.length === 0 && <Empty>Patients appear after they book with you.</Empty>}
        <ul className="divide-y divide-slate-100 text-sm">
          {patients.map((p) => <li key={p.user_id} className="flex items-center justify-between py-2"><span><b>{p.name}</b> · {p.visits} visit(s) · last {p.last_visit}</span><button className="btn-ghost py-1" onClick={() => view(p)}>Open record</button></li>)}
        </ul>
      </Card>
      {open && (
        <Card title={open.p.name} action={<button className="btn-ghost py-1" onClick={() => setOpen(null)}>Close</button>}>
          <div className="grid gap-2 text-sm md:grid-cols-2">
            <p><b>Health ID:</b> {open.s.patient.health_id}</p><p><b>Age / sex:</b> {open.s.patient.age ?? "—"} / {open.s.patient.sex || "—"}</p>
            <p><b>Blood group:</b> {open.s.patient.blood_group || "—"}</p>
            <p><b>Allergies:</b> {open.s.patient.allergies?.map((a) => a.name).join(", ") || "none recorded"}</p>
            <p><b>Conditions:</b> {open.s.patient.diseases?.map((d) => d.name).join(", ") || "none recorded"}</p>
            <p><b>Medicines:</b> {open.s.medicines.map((m) => m.name).join(", ") || "none / not shared"}</p>
            {open.vit && <p className="md:col-span-2"><b>Latest vitals:</b> HR {open.vit.heart_rate ?? "—"} · SpO₂ {open.vit.spo2 ?? "—"} · BP {open.vit.systolic ?? "—"}/{open.vit.diastolic ?? "—"} <Badge tone={toneFor(open.vit.status)}>{open.vit.status}</Badge></p>}
          </div>
          {open.s.recent_risks.length > 0 && <p className="mt-2 text-sm"><b>Recent AI screening:</b> {open.s.recent_risks.slice(0, 5).map((r) => `${r.disease} ${r.level}`).join(" · ")}</p>}
          {open.reports.length > 0 && <ul className="mt-2 border-t pt-2 text-sm">{open.reports.slice(0, 5).map((r) => <li key={r.id}>{r.report_date} · {r.title} — {r.summary}</li>)}</ul>}
          <p className="mt-3"><Link className="btn-primary" to={`/prescribe?patient=${open.p.user_id}`}>Write prescription</Link></p>
        </Card>
      )}
    </>
  );
}

function FamilyHome() {
  const [patients, setPatients] = useState([]);
  const [open, setOpen] = useState(null);
  const { error, run } = useAsync();
  useEffect(() => { api("/family/patients").then(setPatients).catch(() => {}); }, []);
  const view = (p) => run(async () => {
    const vit = p.scopes.includes("vitals") ? await api(`/vitals/latest?patient_id=${p.patient_user_id}`).catch(() => null) : null;
    const alerts = p.scopes.includes("vitals") ? await api(`/vitals/alerts?patient_id=${p.patient_user_id}`).catch(() => []) : [];
    const s = await api(`/patients/${p.patient_user_id}/summary`).catch(() => null);
    setOpen({ p, vit, alerts, s });
  });
  return (
    <>
      <h1 className="text-xl font-bold">Family dashboard</h1>
      <Alert tone="error">{error}</Alert>
      <Card title="People who shared their health with you">
        {patients.length === 0 && <Empty>Ask your family member to add your email under My Health → Sharing & consent.</Empty>}
        <ul className="divide-y divide-slate-100 text-sm">{patients.map((p) => <li key={p.patient_user_id} className="flex items-center justify-between py-2"><span><b>{p.name}</b> · {p.scopes.join(", ")}{p.expires && ` · until ${p.expires}`}</span><button className="btn-ghost py-1" onClick={() => view(p)}>View</button></li>)}</ul>
      </Card>
      {open && (
        <Card title={open.p.name} action={<button className="btn-ghost py-1" onClick={() => setOpen(null)}>Close</button>}>
          {open.s && <p className="text-sm">Blood group {open.s.patient.blood_group || "—"} · Conditions: {open.s.patient.diseases?.map((d) => d.name).join(", ") || "none recorded"}</p>}
          {open.vit ? <p className="mt-2 text-sm">Latest vitals: HR {open.vit.heart_rate ?? "—"} · SpO₂ {open.vit.spo2 ?? "—"} · BP {open.vit.systolic ?? "—"}/{open.vit.diastolic ?? "—"} <Badge tone={toneFor(open.vit.status)}>{open.vit.status}</Badge></p> : <Empty>No vitals shared.</Empty>}
          {open.alerts.slice(0, 5).map((a) => <p key={a.id} className="text-sm"><Badge tone={toneFor(a.severity)}>{a.severity}</Badge> {a.message}</p>)}
        </Card>
      )}
    </>
  );
}
