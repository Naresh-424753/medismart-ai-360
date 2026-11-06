import { useEffect, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Alert, Badge, Card, Empty, Field, useAsync } from "../components/ui.jsx";

export default function Federated() {
  const { user } = useAuth();
  const isAdmin = ["admin", "super_admin"].includes(user.role);
  const [st, setSt] = useState([]);
  const [sim, setSim] = useState(null);
  const [f, setF] = useState({ disease: "diabetes", hospitals: 4, rounds: 12, clip: "", noise_multiplier: 0 });
  const [round, setRound] = useState({ disease: "diabetes", min_participants: 2, clip: 5, noise_multiplier: 0, epochs: 3 });
  const { busy, error, run } = useAsync();
  const load = () => api("/federated/status").then(setSt).catch(() => {});
  useEffect(() => { load(); }, []);
  const simulate = (e) => { e.preventDefault(); run(async () => setSim(await api("/federated/simulate", { method: "POST", body: { ...f, hospitals: +f.hospitals, rounds: +f.rounds, noise_multiplier: +f.noise_multiplier, clip: f.clip ? +f.clip : null } }))); };
  const start = (e) => { e.preventDefault(); run(async () => { await api("/federated/rounds", { method: "POST", body: { ...round, min_participants: +round.min_participants, clip: +round.clip, noise_multiplier: +round.noise_multiplier, epochs: +round.epochs } }); load(); }); };
  const agg = (id) => run(async () => { await api(`/federated/rounds/${id}/aggregate`, { method: "POST" }); load(); });
  const models = st.map((m) => m.disease);
  return (
    <>
      <h1 className="text-xl font-bold">Federated learning</h1>
      <Alert tone="info">Each hospital trains on its own patient data and uploads only a weight update. The server averages the updates (FedAvg). Raw records never move.</Alert>
      <Alert tone="warn">Demo-grade: no secure aggregation and no formal differential-privacy guarantee, so updates can still leak information. Models are simple logistic regressions on synthetic features, not clinical models.</Alert>
      <Alert tone="error">{error}</Alert>
      <Card title="Models">
        <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="text-left text-xs text-slate-500"><th className="py-1">Model</th><th>Global version</th><th>Open round</th><th>Updates received</th><th></th></tr></thead><tbody>
          {st.map((m) => (
            <tr key={m.disease} className="border-t border-slate-100"><td className="py-2 capitalize">{m.title || m.disease}</td><td>v{m.version}</td>
              <td>{m.open_round ? <Badge tone="info">round {m.open_round.round}</Badge> : <span className="text-slate-400">none</span>}</td>
              <td>{m.open_round ? `${m.open_round.received.length}/${m.open_round.min_participants} ${m.open_round.received.map((r) => r.hospital).join(", ")}` : "—"}</td>
              <td>{isAdmin && m.open_round && m.open_round.received.length > 0 && <button className="btn-ghost py-1" onClick={() => agg(m.open_round.id)}>Aggregate now</button>}</td></tr>
          ))}
        </tbody></table></div>
        {st.length === 0 && <Empty>Loading…</Empty>}
      </Card>
      {isAdmin && (
        <Card title="Start a training round">
          <form onSubmit={start} className="grid gap-2 sm:grid-cols-5">
            <Field label="Model"><select className="input" value={round.disease} onChange={(e) => setRound({ ...round, disease: e.target.value })}>{models.map((m) => <option key={m}>{m}</option>)}</select></Field>
            <Field label="Min hospitals"><input className="input" type="number" min="1" value={round.min_participants} onChange={(e) => setRound({ ...round, min_participants: e.target.value })} /></Field>
            <Field label="Clip norm"><input className="input" type="number" step="0.1" value={round.clip} onChange={(e) => setRound({ ...round, clip: e.target.value })} /></Field>
            <Field label="Noise multiplier"><input className="input" type="number" step="0.1" min="0" value={round.noise_multiplier} onChange={(e) => setRound({ ...round, noise_multiplier: e.target.value })} /></Field>
            <div className="flex items-end"><button className="btn-primary" disabled={busy}>Open round</button></div>
          </form>
          <p className="mt-2 text-xs text-slate-500">Hospitals then run <code>python ml/federated_client.py --api … --disease {round.disease} --csv local.csv</code> on their own servers. The round closes automatically once enough hospitals have uploaded.</p>
        </Card>
      )}
      {isAdmin && (
        <Card title="Simulation: do hospitals gain by collaborating?">
          <form onSubmit={simulate} className="grid gap-2 sm:grid-cols-6">
            <Field label="Model"><select className="input" value={f.disease} onChange={(e) => setF({ ...f, disease: e.target.value })}>{models.map((m) => <option key={m}>{m}</option>)}</select></Field>
            <Field label="Hospitals"><input className="input" type="number" min="2" max="10" value={f.hospitals} onChange={(e) => setF({ ...f, hospitals: e.target.value })} /></Field>
            <Field label="Rounds"><input className="input" type="number" min="1" max="40" value={f.rounds} onChange={(e) => setF({ ...f, rounds: e.target.value })} /></Field>
            <Field label="Clip (optional)"><input className="input" type="number" step="0.1" value={f.clip} onChange={(e) => setF({ ...f, clip: e.target.value })} /></Field>
            <Field label="Noise"><input className="input" type="number" step="0.1" min="0" value={f.noise_multiplier} onChange={(e) => setF({ ...f, noise_multiplier: e.target.value })} /></Field>
            <div className="flex items-end"><button className="btn-primary" disabled={busy}>{busy ? "Running…" : "Run"}</button></div>
          </form>
          {sim && (
            <div className="mt-4 space-y-3">
              <div className="h-56"><ResponsiveContainer><LineChart data={sim.curve}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="round" fontSize={11} /><YAxis domain={["auto", "auto"]} fontSize={11} /><Tooltip /><Legend /><Line dataKey="auc" name="Federated AUC" stroke="#2563eb" /></LineChart></ResponsiveContainer></div>
              <div className="grid gap-2 text-sm sm:grid-cols-3">
                <div className="rounded-lg bg-brand-50 p-3"><b>Federated</b><br />AUC {sim.federated.auc}</div>
                <div className="rounded-lg bg-slate-100 p-3"><b>Centralised (needs all raw data in one place)</b><br />AUC {sim.centralised.auc}</div>
                <div className="rounded-lg bg-slate-100 p-3"><b>Each hospital alone</b><br />{sim.local_only.map((l) => `${l.hospital}: ${l.auc}`).join(" · ")}</div>
              </div>
              <p className="text-xs text-slate-500">{sim.note} On this simple synthetic data a single hospital alone can already do about as well; the benefit of federation grows with small, skewed local datasets and richer models. Judge it on your own data.</p>
            </div>
          )}
        </Card>
      )}
      {!isAdmin && <Card title="How your hospital takes part"><ol className="list-decimal space-y-1 pl-5 text-sm"><li>Export a CSV from your own system with the model's feature columns plus <code>label</code>.</li><li>Run <code>backend/ml/federated_client.py</code> on your server while a round is open.</li><li>Only the weight update, sample count and held-out score are uploaded.</li></ol></Card>}
    </>
  );
}
