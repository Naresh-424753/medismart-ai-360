import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Alert, Badge, Card, Empty, Field, useAsync } from "../components/ui.jsx";

const BG = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"];
export default function Blood() {
  const [me, setMe] = useState(null);
  const [d, setD] = useState({ blood_group: "O+", city: "", last_donation: "" });
  const [reqs, setReqs] = useState([]);
  const [mine, setMine] = useState([]);
  const [stock, setStock] = useState([]);
  const [camps, setCamps] = useState([]);
  const [r, setR] = useState({ blood_group: "O+", units: 1, city: "", hospital: "", urgency: "urgent", contact_phone: "" });
  const [s, setS] = useState({ blood_group: "", city: "" });
  const [found, setFound] = useState(null);
  const [note, setNote] = useState("");
  const { busy, error, run } = useAsync();
  const load = () => {
    api("/blood/donors/me").then((x) => { setMe(x); if (x) setD({ blood_group: x.blood_group, city: x.city, last_donation: x.last_donation || "" }); }).catch(() => {});
    api("/blood/requests").then(setReqs).catch(() => {}); api("/blood/requests?mine=true").then(setMine).catch(() => {});
    api("/blood/stock").then(setStock).catch(() => {}); api("/blood/camps").then(setCamps).catch(() => {});
  };
  useEffect(() => { load(); }, []);
  const register = (e) => { e.preventDefault(); run(async () => { await api("/blood/donors", { method: "POST", body: { blood_group: d.blood_group, city: d.city, ...(d.last_donation ? { last_donation: d.last_donation } : {}) } }); setNote("Donor profile saved."); load(); }); };
  const request = (e) => { e.preventDefault(); run(async () => { const x = await api("/blood/requests", { method: "POST", body: { ...r, units: +r.units } }); setNote(`Request created. ${x.donors_notified} eligible donor(s) notified.`); load(); }); };
  const respond = (id) => run(async () => { const x = await api(`/blood/requests/${id}/respond`, { method: "POST" }); setNote(`Thank you! Contact the requester: ${x.contact_phone || "see notification"}${x.hospital ? ` · ${x.hospital}` : ""}`); load(); });
  const close = (id) => run(async () => { await api(`/blood/requests/${id}/close`, { method: "PATCH" }); load(); });
  const donated = () => run(async () => { const x = await api(`/blood/donors/me/donated?where=${encodeURIComponent("Blood donation")}`, { method: "POST" }); setNote(`Recorded. Next eligible: ${x.next_eligible}`); load(); });
  const search = () => run(async () => setFound(await api(`/blood/donors/search?blood_group=${encodeURIComponent(s.blood_group)}&city=${encodeURIComponent(s.city)}`)));
  return (
    <>
      <h1 className="text-xl font-bold">Blood bank & donors</h1><Alert tone="error">{error}</Alert><Alert tone="ok">{note}</Alert>
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Become a donor" action={me && <Badge tone={me.eligible_now ? "good" : "warn"}>{me.eligible_now ? "eligible now" : "resting (90-day gap)"}</Badge>}>
          <form onSubmit={register} className="grid grid-cols-2 gap-2"><Field label="Blood group"><select className="input" value={d.blood_group} onChange={(e) => setD({ ...d, blood_group: e.target.value })}>{BG.map((g) => <option key={g}>{g}</option>)}</select></Field><Field label="City"><input className="input" required value={d.city} onChange={(e) => setD({ ...d, city: e.target.value })} /></Field><Field label="Last donation"><input className="input" type="date" value={d.last_donation} onChange={(e) => setD({ ...d, last_donation: e.target.value })} /></Field><div className="flex items-end gap-2"><button className="btn-primary">Save</button>{me && <button type="button" className="btn-ghost" onClick={donated}>I donated today</button>}</div></form>
          {me?.donations?.length > 0 && <p className="mt-2 text-xs text-slate-500">Donations: {me.donations.map((x) => x.date).join(", ")}</p>}
        </Card>
        <Card title="Request blood (emergency)">
          <form onSubmit={request} className="grid grid-cols-2 gap-2"><Field label="Group"><select className="input" value={r.blood_group} onChange={(e) => setR({ ...r, blood_group: e.target.value })}>{BG.map((g) => <option key={g}>{g}</option>)}</select></Field><Field label="Units"><input className="input" type="number" min="1" max="20" value={r.units} onChange={(e) => setR({ ...r, units: e.target.value })} /></Field><Field label="City"><input className="input" required value={r.city} onChange={(e) => setR({ ...r, city: e.target.value })} /></Field><Field label="Hospital"><input className="input" value={r.hospital} onChange={(e) => setR({ ...r, hospital: e.target.value })} /></Field><Field label="Urgency"><select className="input" value={r.urgency} onChange={(e) => setR({ ...r, urgency: e.target.value })}><option value="critical">Critical</option><option value="urgent">Urgent</option><option value="planned">Planned</option></select></Field><Field label="Contact phone"><input className="input" value={r.contact_phone} onChange={(e) => setR({ ...r, contact_phone: e.target.value })} /></Field><div className="col-span-2"><button className="btn-danger" disabled={busy}>Notify donors & blood banks</button></div></form>
        </Card>
      </div>
      <Card title="Open requests near you">{reqs.length === 0 ? <Empty>No open requests.</Empty> : <ul className="divide-y divide-slate-100 text-sm">{reqs.map((q) => <li key={q.id} className="flex flex-wrap items-center justify-between gap-2 py-2"><span><b>{q.blood_group}</b> ×{q.units} · {q.city} {q.hospital && `· ${q.hospital}`} <Badge tone={q.urgency === "critical" ? "bad" : "warn"}>{q.urgency}</Badge></span><button className="btn-primary py-1" onClick={() => respond(q.id)}>I can donate</button></li>)}</ul>}</Card>
      {mine.length > 0 && <Card title="My requests"><ul className="divide-y divide-slate-100 text-sm">{mine.map((q) => <li key={q.id} className="py-2"><b>{q.blood_group}</b> ×{q.units} · {q.city} · <Badge tone={q.status === "open" ? "warn" : "good"}>{q.status}</Badge> · {q.responders.length} donor(s) responded {q.responders.map((x) => `${x.name} ${x.phone}`).join("; ")} {q.status === "open" && <button className="btn-ghost ml-2 py-1" onClick={() => close(q.id)}>Close</button>}</li>)}</ul></Card>}
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Find compatible donors"><div className="flex gap-2"><select className="input" value={s.blood_group} onChange={(e) => setS({ ...s, blood_group: e.target.value })}><option value="">Group</option>{BG.map((g) => <option key={g}>{g}</option>)}</select><input className="input" placeholder="City" value={s.city} onChange={(e) => setS({ ...s, city: e.target.value })} /><button className="btn-ghost" onClick={search} disabled={!s.blood_group || !s.city}>Search</button></div>{found && <p className="mt-2 text-sm">{found.length} eligible donor(s) found{found.length ? `: ${found.map((x) => `${x.name} (${x.blood_group})`).join(", ")}` : ""}. Use “Request blood” so they can opt in to share contact.</p>}</Card>
        <Card title="Blood banks — stock">{stock.length === 0 ? <Empty>No stock listed.</Empty> : <ul className="max-h-60 divide-y divide-slate-100 overflow-y-auto text-sm">{stock.map((x, i) => <li key={i} className="flex justify-between py-1"><span>{x.bank_name} {x.city && `· ${x.city}`}</span><span><b>{x.blood_group}</b> {x.units}u {x.expired && <Badge tone="bad">expired</Badge>}</span></li>)}</ul>}</Card>
      </div>
      <Card title="Donation camps">{camps.length === 0 ? <Empty>No upcoming camps.</Empty> : <ul className="divide-y divide-slate-100 text-sm">{camps.map((c) => <li key={c.id} className="flex items-center justify-between py-2"><span><b>{c.title}</b> · {c.date} · {c.venue}, {c.city} · {c.registrations} registered</span><button className="btn-ghost py-1" onClick={() => run(async () => { await api(`/blood/camps/${c.id}/register`, { method: "POST" }); load(); })}>Register</button></li>)}</ul>}</Card>
    </>
  );
}
