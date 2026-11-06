import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Alert, Badge, Card, Empty, Field, useAsync } from "../components/ui.jsx";

const bed = (b, k) => `${b[k].available}/${b[k].total}`;
export default function Hospitals() {
  const [f, setF] = useState({ city: "", q: "", speciality: "", min_icu: "" });
  const [list, setList] = useState([]);
  const [cmp, setCmp] = useState([]);
  const [rows, setRows] = useState(null);
  const [queue, setQueue] = useState(null);
  const [token, setToken] = useState(null);
  const { busy, error, run } = useAsync();
  const search = () => run(async () => setList(await api(`/hospitals?${new URLSearchParams(Object.entries(f).filter(([, v]) => v))}`)));
  useEffect(() => { search(); }, []);
  useEffect(() => { if (cmp.length >= 2) api(`/hospitals/compare?ids=${cmp.join(",")}`).then(setRows).catch(() => {}); else setRows(null); }, [cmp]);
  const getToken = (h) => run(async () => { setToken(await api(`/hospitals/${h.id}/tokens`, { method: "POST", body: { department: "OPD" } })); setQueue(await api(`/hospitals/${h.id}/queue?department=OPD`)); });
  const viewQueue = (h) => run(async () => setQueue({ ...(await api(`/hospitals/${h.id}/queue?department=OPD`)), name: h.name }));
  return (
    <>
      <h1 className="text-xl font-bold">Hospitals</h1><Alert tone="error">{error}</Alert>
      <Card title="Search">
        <div className="grid gap-3 md:grid-cols-5">
          <Field label="City"><input className="input" value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} /></Field>
          <Field label="Name"><input className="input" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} /></Field>
          <Field label="Speciality"><input className="input" placeholder="Cardiology" value={f.speciality} onChange={(e) => setF({ ...f, speciality: e.target.value })} /></Field>
          <Field label="Min ICU beds"><input className="input" type="number" min="0" value={f.min_icu} onChange={(e) => setF({ ...f, min_icu: e.target.value })} /></Field>
          <div className="flex items-end"><button className="btn-primary w-full" onClick={search} disabled={busy}>Search</button></div>
        </div>
      </Card>
      {token && <Alert tone="ok">Your OPD token at {token.hospital_name}: <b>#{token.number}</b> · {token.people_ahead} ahead · ~{token.est_wait_min} min wait</Alert>}
      {queue && <Alert tone="info">Queue {queue.name || ""}: now serving <b>{queue.now_serving ?? "—"}</b> · {queue.waiting} waiting</Alert>}
      <Card title={`Results (${list.length}) — tick up to 3 to compare`}>
        {list.length === 0 && <Empty>No verified hospitals match.</Empty>}
        <ul className="divide-y divide-slate-100 text-sm">
          {list.map((h) => (
            <li key={h.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span className="flex items-center gap-2"><input type="checkbox" checked={cmp.includes(h.id)} disabled={!cmp.includes(h.id) && cmp.length >= 3} onChange={(e) => setCmp(e.target.checked ? [...cmp, h.id] : cmp.filter((x) => x !== h.id))} /><span><b>{h.name}</b> · {h.city} · ★ {h.rating || "—"}<br /><span className="text-xs text-slate-500">ICU {bed(h.beds, "icu")} · Emergency {bed(h.beds, "emergency")} · General {bed(h.beds, "general")} · {h.specialities.join(", ")}</span></span></span>
              <span className="flex gap-2"><a className="btn-ghost py-1" href={`tel:${h.phone}`}>Call</a><button className="btn-ghost py-1" onClick={() => viewQueue(h)}>Queue</button><button className="btn-primary py-1" onClick={() => getToken(h)}>Get OPD token</button></span>
            </li>
          ))}
        </ul>
      </Card>
      {rows && <Card title="Comparison"><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-xs uppercase text-slate-500"><tr><th className="py-1">Hospital</th><th>City</th><th>Rating</th><th>ICU</th><th>Emergency</th><th>General</th><th>Ventilator</th></tr></thead><tbody>{rows.map((h) => <tr key={h.id} className="border-t border-slate-100"><td className="py-1 font-medium">{h.name}</td><td>{h.city}</td><td>{h.rating || "—"}</td><td>{bed(h.beds, "icu")}</td><td>{bed(h.beds, "emergency")}</td><td>{bed(h.beds, "general")}</td><td>{bed(h.beds, "ventilator")}</td></tr>)}</tbody></table></div></Card>}
    </>
  );
}
