import { useEffect, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Alert, Badge, Card, Empty, Field, textToList, useAsync } from "../components/ui.jsx";

const STATUS = { awaiting_consent: ["Your consent needed", "warn"], panel_review: ["With specialist panel", "info"], completed: ["Report ready", "good"], cancelled: ["Cancelled", "muted"] };

function Ensemble({ e, providers }) {
  return (
    <div className="space-y-2 text-sm">
      <p className="text-xs text-slate-500">{e.methods_run} of {e.methods_total} methods ran · confidence <b>{e.confidence}</b>{e.methods_disagree_on_top && " · methods disagree on the top condition"}. {e.note}</p>
      {e.top.length === 0 ? <Empty>No condition stood out.</Empty> : (
        <ul className="space-y-1">{e.top.map((t) => (
          <li key={t.key} className="rounded-lg border border-slate-200 p-2">
            <div className="flex items-center justify-between"><b>{t.condition}</b><span className="flex items-center gap-2"><Badge tone="info">agreement {t.agreement}</Badge><span className="text-xs text-slate-500">score {Math.round(t.consensus * 100)}%</span></span></div>
            <p className="text-xs text-slate-500">Specialist: {t.specialist}</p>
            {Object.entries(t.evidence).filter(([, v]) => v).map(([k, v]) => <p key={k} className="text-xs text-slate-600"><b>{k.replace("_", " ")}:</b> {v}</p>)}
          </li>))}</ul>
      )}
      {providers && <ul className="text-xs text-slate-500">{providers.map((p) => <li key={p.provider}>{p.available ? "✔" : "✖"} {p.label}{!p.available && p.reason ? ` - ${p.reason}` : ""}</li>)}</ul>}
    </div>
  );
}

function Report({ r }) {
  return (
    <div className="space-y-3 text-sm" id="so-report">
      <h3 className="text-lg font-bold">Second Opinion Report</h3>
      <p>{r.summary}</p>
      <div><b>Why it was opened:</b> {r.triggers.join("; ")}</div>
      <div><b>AI ensemble</b><Ensemble e={r.ai_ensemble} /></div>
      <div><b>Doctor opinions</b>
        <ul className="mt-1 space-y-2">{r.doctor_opinions.map((o, i) => <li key={i} className="rounded-lg border border-slate-200 p-2"><b>{o.doctor}</b> ({o.specialization}) · <Badge tone={o.verdict === "agree" ? "good" : o.verdict === "disagree" ? "bad" : "warn"}>{o.verdict.replace("_", " ")}</Badge>
          {o.suggested_diagnosis && <p>Suggested: {o.suggested_diagnosis}</p>}{o.recommended_tests?.length > 0 && <p>Tests: {o.recommended_tests.join(", ")}</p>}{o.comments && <p className="text-slate-600">{o.comments}</p>}</li>)}</ul></div>
      {r.recommended_tests.length > 0 && <p><b>Tests suggested (most-mentioned first):</b> {r.recommended_tests.join(", ")}</p>}
      {r.recommended_specialists.length > 0 && <p><b>Specialists suggested:</b> {r.recommended_specialists.join(", ")}</p>}
      <p className="text-xs text-slate-500">Report fingerprint (also on your record-security ledger): <span className="font-mono break-all">{r.sha256}</span></p>
      <Alert tone="warn">{r.disclaimer}</Alert>
      <button className="btn-ghost print:hidden" onClick={() => window.print()}>Print / save as PDF</button>
    </div>
  );
}

function PatientView() {
  const [cases, setCases] = useState([]);
  const [f, setF] = useState({ symptoms: "", note: "" });
  const [open, setOpen] = useState(null);
  const { busy, error, run } = useAsync();
  const load = () => api("/board/cases").then(setCases).catch(() => {});
  useEffect(() => { load(); }, []);
  const create = (e) => { e.preventDefault(); run(async () => { const c = await api("/board/cases", { method: "POST", body: { symptoms: textToList(f.symptoms), note: f.note } }); setF({ symptoms: "", note: "" }); await load(); setOpen(c.id); }); };
  const consent = (id, allow) => run(async () => { await api(`/board/cases/${id}/consent`, { method: "POST", body: { allow } }); load(); });
  const finalize = (id) => run(async () => { await api(`/board/cases/${id}/finalize`, { method: "POST" }); load(); });
  return (
    <>
      <h1 className="text-xl font-bold">Second opinion & medical board</h1>
      <Alert tone="info">Complex or unusual results automatically trigger an AI review. Specialists see your case only if you agree, and only as an anonymised summary (no name, phone, email or address).</Alert>
      <Alert tone="error">{error}</Alert>
      <Card title="Ask for a second opinion">
        <form onSubmit={create} className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
          <Field label="Symptoms (comma separated)"><input className="input" value={f.symptoms} onChange={(e) => setF({ ...f, symptoms: e.target.value })} /></Field>
          <Field label="Anything the doctors should know (no names or phone numbers)"><input className="input" maxLength={600} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field>
          <div className="flex items-end"><button className="btn-primary" disabled={busy}>{busy ? "Reviewing…" : "Start AI review"}</button></div>
        </form>
      </Card>
      {cases.length === 0 && <Card><Empty>No cases yet.</Empty></Card>}
      {cases.map((c) => { const [lab, tone] = STATUS[c.status] || [c.status, "muted"]; return (
        <Card key={c.id} title={`Case · ${new Date(c.created_at).toLocaleDateString()} · ${c.origin}`} action={<Badge tone={tone}>{lab}</Badge>}>
          <p className="mb-2 text-xs text-slate-500">Why: {c.triggers.join("; ")}</p>
          <button className="text-sm text-brand-700 underline" onClick={() => setOpen(open === c.id ? null : c.id)}>{open === c.id ? "Hide details" : "Show AI review"}</button>
          {open === c.id && <div className="mt-2"><Ensemble e={c.ensemble} providers={c.providers} /><details className="mt-2 text-xs"><summary className="cursor-pointer text-slate-500">Exactly what specialists would see</summary><pre className="mt-1 whitespace-pre-wrap rounded bg-slate-50 p-2">{JSON.stringify(c.packet, null, 2)}</pre></details></div>}
          {c.status === "awaiting_consent" && <div className="mt-3 flex flex-wrap gap-2"><button className="btn-primary" disabled={busy} onClick={() => consent(c.id, true)}>Share anonymised summary with 3 specialists</button><button className="btn-ghost" disabled={busy} onClick={() => consent(c.id, false)}>No thanks</button></div>}
          {c.status === "panel_review" && <div className="mt-3 text-sm"><ul>{c.panel.map((p) => <li key={p.name}>{p.name} ({p.specialization}) · <Badge tone={p.status === "submitted" ? "good" : "muted"}>{p.status}</Badge></li>)}</ul>
            {c.panel.filter((p) => p.status === "submitted").length >= 2 && <button className="btn-ghost mt-2" disabled={busy} onClick={() => finalize(c.id)}>Generate report now</button>}</div>}
          {c.status === "completed" && c.report && <div className="mt-3 border-t pt-3"><Report r={c.report} /></div>}
        </Card>); })}
    </>
  );
}

function DoctorView() {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({});
  const { busy, error, run } = useAsync();
  const load = () => api("/board/panel").then(setRows).catch(() => {});
  useEffect(() => { load(); }, []);
  const f = (id) => form[id] || { verdict: "agree", suggested_diagnosis: "", tests: "", specialist: "", comments: "" };
  const set = (id, k, v) => setForm({ ...form, [id]: { ...f(id), [k]: v } });
  const send = (id) => run(async () => { const x = f(id); await api(`/board/panel/${id}/opinion`, { method: "POST", body: { verdict: x.verdict, suggested_diagnosis: x.suggested_diagnosis, recommended_tests: textToList(x.tests), recommended_specialist: x.specialist, comments: x.comments } }); load(); });
  return (
    <>
      <h1 className="text-xl font-bold">Medical board review</h1>
      <Alert tone="info">Cases are anonymised. The AI ensemble is decision support from demo-grade models: use your own clinical judgement.</Alert>
      <Alert tone="error">{error}</Alert>
      {rows.length === 0 && <Card><Empty>No cases assigned to you.</Empty></Card>}
      {rows.map((c) => (
        <Card key={c.id} title={`Case ${c.id.slice(0, 8)} · ${new Date(c.created_at).toLocaleDateString()}`} action={<Badge tone={c.my_status === "submitted" ? "good" : "warn"}>{c.my_status === "submitted" ? "responded" : "awaiting you"}</Badge>}>
          <p className="text-xs text-slate-500">Why flagged: {c.triggers.join("; ")}</p>
          <pre className="my-2 whitespace-pre-wrap rounded bg-slate-50 p-2 text-xs">{JSON.stringify(c.packet, null, 2)}</pre>
          <Ensemble e={c.ensemble} />
          {c.my_status !== "submitted" && c.status === "panel_review" && (
            <div className="mt-3 grid gap-2 border-t pt-3 sm:grid-cols-2">
              <Field label="Your verdict on the AI assessment"><select className="input" value={f(c.id).verdict} onChange={(e) => set(c.id, "verdict", e.target.value)}><option value="agree">Agree</option><option value="modify">Agree with changes</option><option value="disagree">Disagree</option><option value="need_more_info">Need more information</option></select></Field>
              <Field label="Suggested diagnosis / working impression"><input className="input" value={f(c.id).suggested_diagnosis} onChange={(e) => set(c.id, "suggested_diagnosis", e.target.value)} /></Field>
              <Field label="Recommended tests (comma separated)"><input className="input" value={f(c.id).tests} onChange={(e) => set(c.id, "tests", e.target.value)} /></Field>
              <Field label="Refer to specialist"><input className="input" value={f(c.id).specialist} onChange={(e) => set(c.id, "specialist", e.target.value)} /></Field>
              <div className="sm:col-span-2"><Field label="Comments"><textarea className="input" rows={3} value={f(c.id).comments} onChange={(e) => set(c.id, "comments", e.target.value)} /></Field></div>
              <div><button className="btn-primary" disabled={busy} onClick={() => send(c.id)}>Submit opinion</button></div>
            </div>)}
          {c.report && <div className="mt-3 border-t pt-3"><Report r={c.report} /></div>}
        </Card>))}
    </>
  );
}

export default function SecondOpinion() {
  const { user } = useAuth();
  return user.role === "doctor" ? <DoctorView /> : <PatientView />;
}
