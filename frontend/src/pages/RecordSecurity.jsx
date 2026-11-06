import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Alert, Badge, Card, Empty, useAsync } from "../components/ui.jsx";

const LABEL = { document: "Document fingerprinted", access_grant: "Access granted", access_revoke: "Access revoked", access_event: "Record viewed by someone else", prescription: "Prescription issued", prescription_scan_verified: "Scanned prescription verified" };

export default function RecordSecurity() {
  const [c, setC] = useState(null);
  const [docs, setDocs] = useState([]);
  const [res, setRes] = useState({});
  const { error, run } = useAsync();
  const load = () => { api("/ledger/me").then(setC).catch(() => {}); api("/patients/me/documents").then(setDocs).catch(() => {}); };
  useEffect(load, []);
  const check = (id) => run(async () => setRes({ ...res, [id]: await api(`/ledger/me/documents/${id}/verify`) }));
  const revoke = (email) => run(async () => { await api(`/ledger/me/access/${encodeURIComponent(email)}/revoke`, { method: "POST" }); load(); });
  const v = c?.verification;
  return (
    <>
      <h1 className="text-xl font-bold">Record security (tamper-proof ledger)</h1>
      <Alert tone="info">Every upload, consent change and third-party access to your records is fingerprinted on a hash-chained ledger. Changing or deleting any old entry breaks the chain, and you can check that here. The ledger stores fingerprints only, never your medical data.</Alert>
      <Alert tone="error">{error}</Alert>
      {v && <Card title="Chain integrity" action={<button className="btn-ghost" onClick={load}>Re-check</button>}><p className="text-sm">{v.valid ? <Badge tone="good">Valid</Badge> : <Badge tone="bad">Broken at block {v.broken_at}</Badge>} <span className="ml-2 text-slate-600">{v.valid ? `${v.blocks} blocks verified.` : v.reason}</span></p>{v.head && <p className="mt-2 break-all font-mono text-xs text-slate-500">head {v.head}</p>}</Card>}
      <Card title="Who currently has access (from the ledger)">
        {!c || Object.keys(c.access_list).length === 0 ? <Empty>Nobody besides you and doctors you have appointments with.</Empty> : (
          <ul className="divide-y divide-slate-100 text-sm">{Object.entries(c.access_list).map(([email, g]) => <li key={email} className="flex items-center justify-between py-2"><span><b>{email}</b> · {g.scopes.join(", ")} · since {new Date(g.since).toLocaleDateString()}{g.expires && ` · until ${g.expires}`}</span><button className="btn-ghost py-1" onClick={() => revoke(email)}>Revoke</button></li>)}</ul>
        )}
      </Card>
      <Card title="Verify my documents">
        {docs.length === 0 ? <Empty>No documents uploaded.</Empty> : (
          <ul className="divide-y divide-slate-100 text-sm">{docs.map((d) => (
            <li key={d.id} className="py-2"><div className="flex items-center justify-between"><span>{d.title}</span><button className="btn-ghost py-1" onClick={() => check(d.id)}>Verify integrity</button></div>
              {res[d.id] && <p className="mt-1 text-xs"><Badge tone={res[d.id].status === "verified" ? "good" : res[d.id].status === "not_anchored" ? "muted" : "bad"}>{res[d.id].status}</Badge> {res[d.id].message || (res[d.id].file_matches_ledger ? "File matches the fingerprint recorded at upload." : "File differs from the fingerprint recorded at upload!")}</p>}</li>))}</ul>
        )}
      </Card>
      <Card title="Ledger activity">
        {!c || c.blocks.length === 0 ? <Empty>No events yet.</Empty> : (
          <ul className="space-y-1 text-sm">{c.blocks.slice(0, 50).map((b) => <li key={b.id} className="flex justify-between gap-2 border-b border-slate-100 py-1"><span>#{b.index} {LABEL[b.type] || b.type}{b.payload.scope ? ` (${b.payload.scope}${b.payload.viewer_role ? ", " + b.payload.viewer_role : ""})` : ""}{b.payload.grantee ? ` · ${b.payload.grantee}` : ""}</span><span className="text-xs text-slate-500">{new Date(b.ts).toLocaleString()} · <span className="font-mono">{b.hash.slice(0, 10)}…</span></span></li>)}</ul>
        )}
      </Card>
    </>
  );
}
