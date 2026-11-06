import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Alert, Badge, Card, Empty, Field, isoToday, useAsync } from "../components/ui.jsx";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const tone = (s) => ({ booked: "info", confirmed: "good", completed: "good", cancelled: "muted" }[s] || "muted");

export default function Appointments() {
  const { user } = useAuth();
  return (
    <>
      <h1 className="text-xl font-bold">{user.role === "doctor" ? "Schedule & profile" : "Appointments"}</h1>
      {user.role === "doctor" ? <DoctorSide /> : <PatientSide />}
    </>
  );
}

function List({ list, reload, doctor }) {
  const { busy, error, run } = useAsync();
  const [done, setDone] = useState(null); // appointment being completed
  const [note, setNote] = useState({ notes: "", follow_up_date: "" });
  const [fb, setFb] = useState(null);
  const [rating, setRating] = useState({ rating: 5, comment: "" });
  const act = (id, action, extra = {}) => run(async () => { await api(`/appointments/${id}`, { method: "PATCH", body: { action, ...extra } }); setDone(null); reload(); });
  const resched = (a) => {
    const date = prompt("New date (YYYY-MM-DD)", a.date); const time = date && prompt("New time (HH:MM)", a.time);
    if (date && time) act(a.id, "reschedule", { date, time });
  };
  return (
    <Card title="Appointments">
      <Alert tone="error">{error}</Alert>
      {list.length === 0 && <Empty>No appointments yet.</Empty>}
      <ul className="divide-y divide-slate-100 text-sm">
        {list.map((a) => (
          <li key={a.id} className="space-y-2 py-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span>
                <b>{a.date} {a.time}</b> · {doctor ? a.patient_name : `Dr. ${a.doctor_name} (${a.specialization})`} · {a.mode === "video" ? "video" : "in person"}
                {a.mode === "video" && ["booked", "confirmed"].includes(a.status) && <> · <Link className="font-semibold text-brand-700 underline" to={`/call/${a.id}`}>Join call</Link>{a.video_url && <> <a className="text-xs text-slate-500 underline" href={a.video_url} target="_blank" rel="noreferrer">(backup link)</a></>}</>}
                {a.reason && <span className="text-slate-500"> · {a.reason}</span>}
              </span>
              <span className="flex flex-wrap items-center gap-2">
                <Badge tone={tone(a.status)}>{a.status}</Badge>
                {doctor && a.status === "booked" && <button className="btn-ghost py-1" disabled={busy} onClick={() => act(a.id, "confirm")}>Confirm</button>}
                {doctor && ["booked", "confirmed"].includes(a.status) && <button className="btn-primary py-1" onClick={() => { setDone(a.id); setNote({ notes: "", follow_up_date: "" }); }}>Complete</button>}
                {["booked", "confirmed"].includes(a.status) && <button className="btn-ghost py-1" onClick={() => resched(a)}>Reschedule</button>}
                {["booked", "confirmed"].includes(a.status) && <button className="btn-ghost py-1" onClick={() => confirm("Cancel this appointment?") && act(a.id, "cancel")}>Cancel</button>}
                {!doctor && a.status === "completed" && !a.feedback && <button className="btn-ghost py-1" onClick={() => setFb(a.id)}>Rate</button>}
              </span>
            </div>
            {a.notes && a.status === "completed" && <p className="text-slate-600">Notes: {a.notes}{a.follow_up_date && ` · follow-up ${a.follow_up_date}`}</p>}
            {done === a.id && (
              <div className="grid gap-2 rounded-lg bg-slate-50 p-3 md:grid-cols-3">
                <div className="md:col-span-2"><Field label="Treatment notes"><textarea className="input h-20" value={note.notes} onChange={(e) => setNote({ ...note, notes: e.target.value })} /></Field></div>
                <Field label="Follow-up date"><input className="input" type="date" min={isoToday()} value={note.follow_up_date} onChange={(e) => setNote({ ...note, follow_up_date: e.target.value })} /></Field>
                <button className="btn-primary" onClick={() => act(a.id, "complete", { notes: note.notes, follow_up_date: note.follow_up_date || null })}>Save & complete</button>
              </div>
            )}
            {fb === a.id && (
              <div className="flex flex-wrap items-end gap-2 rounded-lg bg-slate-50 p-3">
                <Field label="Rating (1-5)"><input className="input w-24" type="number" min="1" max="5" value={rating.rating} onChange={(e) => setRating({ ...rating, rating: +e.target.value })} /></Field>
                <div className="flex-1"><Field label="Comment"><input className="input" value={rating.comment} onChange={(e) => setRating({ ...rating, comment: e.target.value })} /></Field></div>
                <button className="btn-primary" onClick={() => run(async () => { await api(`/appointments/${a.id}/feedback`, { method: "POST", body: rating }); setFb(null); reload(); })}>Submit</button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function PatientSide() {
  const [list, setList] = useState([]);
  const [docs, setDocs] = useState([]);
  const [filter, setFilter] = useState({ specialization: "", city: "", q: "" });
  const [doc, setDoc] = useState(null);
  const [date, setDate] = useState(isoToday());
  const [slots, setSlots] = useState([]);
  const [slot, setSlot] = useState("");
  const [reason, setReason] = useState("");
  const [mode, setMode] = useState("in_person");
  const [ok, setOk] = useState("");
  const { busy, error, run } = useAsync();
  const load = () => api("/appointments").then(setList).catch(() => {});
  const search = () => run(async () => setDocs(await api(`/doctors?${new URLSearchParams(Object.entries(filter).filter(([, v]) => v))}`)));
  useEffect(() => { load(); search(); }, []);
  useEffect(() => { if (doc) api(`/doctors/${doc.id}/slots?date=${date}`).then((r) => { setSlots(r.slots); setSlot(""); }).catch(() => setSlots([])); }, [doc, date]);
  const book = (e) => {
    e.preventDefault();
    run(async () => { await api("/appointments", { method: "POST", body: { doctor_id: doc.id, date, time: slot, reason, mode } }); setOk("Appointment booked. A confirmation was sent."); setDoc(null); setReason(""); load(); });
  };
  return (
    <>
      <Alert tone="ok">{ok}</Alert><Alert tone="error">{error}</Alert>
      <Card title="Find a doctor">
        <div className="grid gap-3 md:grid-cols-4">
          <Field label="Specialization"><input className="input" placeholder="Cardiologist" value={filter.specialization} onChange={(e) => setFilter({ ...filter, specialization: e.target.value })} /></Field>
          <Field label="City"><input className="input" value={filter.city} onChange={(e) => setFilter({ ...filter, city: e.target.value })} /></Field>
          <Field label="Name / hospital"><input className="input" value={filter.q} onChange={(e) => setFilter({ ...filter, q: e.target.value })} /></Field>
          <div className="flex items-end"><button className="btn-primary w-full" onClick={search} disabled={busy}>Search</button></div>
        </div>
        {docs.length === 0 && <div className="mt-3"><Empty>No doctors found (doctor accounts appear after admin approval).</Empty></div>}
        <ul className="mt-3 divide-y divide-slate-100 text-sm">
          {docs.map((d) => (
            <li key={d.id} className="flex items-center justify-between py-2">
              <span><b>Dr. {d.name}</b> · {d.specialization} · {d.experience_years ?? "?"} yrs · ₹{d.fee} {d.hospital && `· ${d.hospital}`} {d.city && `· ${d.city}`} <Badge tone="info">★ {d.rating || "new"}</Badge></span>
              <button className="btn-ghost py-1" onClick={() => { setDoc(d); setOk(""); }}>Book</button>
            </li>
          ))}
        </ul>
      </Card>
      {doc && (
        <Card title={`Book Dr. ${doc.name}`} action={<button className="btn-ghost py-1" onClick={() => setDoc(null)}>Close</button>}>
          <form onSubmit={book} className="grid gap-3 md:grid-cols-4">
            <Field label="Date"><input className="input" type="date" min={isoToday()} value={date} onChange={(e) => setDate(e.target.value)} /></Field>
            <Field label="Time slot"><select className="input" required value={slot} onChange={(e) => setSlot(e.target.value)}><option value="">{slots.length ? "Choose…" : "No slots"}</option>{slots.map((s) => <option key={s}>{s}</option>)}</select></Field>
            <Field label="Type"><select className="input" value={mode} onChange={(e) => setMode(e.target.value)}><option value="in_person">In person</option><option value="video">Video consultation</option></select></Field>
            <Field label="Reason"><input className="input" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
            <div className="md:col-span-4"><button className="btn-primary" disabled={busy || !slot}>Confirm booking</button></div>
          </form>
        </Card>
      )}
      <List list={list} reload={load} doctor={false} />
    </>
  );
}

function DoctorSide() {
  const [list, setList] = useState([]);
  const [dash, setDash] = useState(null);
  const [p, setP] = useState(null);
  const [days, setDays] = useState([]);
  const [slots, setSlots] = useState("");
  const [msg, setMsg] = useState("");
  const { busy, error, run } = useAsync();
  const load = () => { api("/appointments").then(setList).catch(() => {}); api("/doctor/dashboard").then(setDash).catch(() => {}); };
  useEffect(() => {
    load();
    api("/doctors/me").then((d) => { setP(d); setDays(d.availability?.days || []); setSlots((d.availability?.slots || []).join(", ")); }).catch(() => {});
  }, []);
  const save = (e) => {
    e.preventDefault();
    run(async () => {
      const body = { specialization: p.specialization, experience_years: +p.experience_years || 0, fee: +p.fee || 0, bio: p.bio || "", hospital: p.hospital || "", city: p.city || "", availability: { days, slots: slots.split(",").map((s) => s.trim()).filter(Boolean) } };
      setP(await api("/doctors/me", { method: "PUT", body })); setMsg("Profile saved.");
    });
  };
  return (
    <>
      {dash && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {[["Today", dash.today.length], ["Patients", dash.stats.total_patients], ["Completed", dash.stats.completed], ["Avg rating", dash.stats.avg_rating]].map(([l, v]) => <Card key={l}><p className="text-3xl font-bold text-brand-700">{v ?? "—"}</p><p className="text-xs text-slate-500">{l}</p></Card>)}
        </div>
      )}
      {dash && !dash.approved && <Alert tone="warn">Your account is awaiting admin verification. Patients cannot see or book you yet.</Alert>}
      <List list={list} reload={load} doctor />
      {p && (
        <Card title="My profile & availability">
          <form onSubmit={save} className="grid gap-3 md:grid-cols-3">
            <Field label="Specialization"><input className="input" required value={p.specialization || ""} onChange={(e) => setP({ ...p, specialization: e.target.value })} /></Field>
            <Field label="Experience (years)"><input className="input" type="number" min="0" value={p.experience_years ?? ""} onChange={(e) => setP({ ...p, experience_years: e.target.value })} /></Field>
            <Field label="Fee (₹)"><input className="input" type="number" min="0" value={p.fee ?? ""} onChange={(e) => setP({ ...p, fee: e.target.value })} /></Field>
            <Field label="Hospital / clinic"><input className="input" value={p.hospital || ""} onChange={(e) => setP({ ...p, hospital: e.target.value })} /></Field>
            <Field label="City"><input className="input" value={p.city || ""} onChange={(e) => setP({ ...p, city: e.target.value })} /></Field>
            <Field label="Bio"><input className="input" value={p.bio || ""} onChange={(e) => setP({ ...p, bio: e.target.value })} /></Field>
            <div className="md:col-span-3">
              <span className="label">Working days</span>
              <div className="flex flex-wrap gap-3 text-sm">{DAYS.map((d, i) => <label key={d} className="flex items-center gap-1"><input type="checkbox" checked={days.includes(i)} onChange={(e) => setDays(e.target.checked ? [...days, i].sort() : days.filter((x) => x !== i))} />{d}</label>)}</div>
            </div>
            <div className="md:col-span-3"><Field label="Slots (HH:MM, comma separated)"><input className="input" value={slots} onChange={(e) => setSlots(e.target.value)} placeholder="10:00, 10:30, 11:00" /></Field></div>
            <Alert tone="ok">{msg}</Alert><Alert tone="error">{error}</Alert>
            <div className="md:col-span-3"><button className="btn-primary" disabled={busy}>Save profile</button></div>
          </form>
        </Card>
      )}
    </>
  );
}
