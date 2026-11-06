import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { api } from "../api.js";
import { Alert, Badge, useAsync } from "./ui.jsx";

const STEPS = ["placed", "accepted", "packed", "out_for_delivery", "delivered"];
const PAY_LABEL = { pending: "Payment pending", submitted: "Payment being verified", paid: "Paid", failed: "Payment not found", cod: "Cash on delivery", refund_due: "Refund due" };
const PAY_TONE = { pending: "warn", submitted: "info", paid: "good", failed: "bad", cod: "muted", refund_due: "warn" };

export function Timeline({ status }) {
  if (status === "rejected") return <Badge tone="bad">rejected by pharmacy</Badge>;
  const at = STEPS.indexOf(status);
  return (
    <ol className="flex flex-wrap items-center gap-1 text-[11px]">
      {STEPS.map((s, i) => (
        <li key={s} className="flex items-center gap-1">
          <span className={`rounded-full px-2 py-0.5 ${i <= at ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-500"}`}>{s.replace(/_/g, " ")}</span>
          {i < STEPS.length - 1 && <span className="text-slate-300">›</span>}
        </li>
      ))}
    </ol>
  );
}

/** UPI QR + "I have paid" form. The QR is a standard upi:// link, so any UPI app can scan it. */
export function PayPanel({ order, onDone }) {
  const [info, setInfo] = useState(null);
  const [utr, setUtr] = useState("");
  const { busy, error, run } = useAsync();
  const [err2, setErr2] = useState("");
  useEffect(() => { api(`/medicines/orders/${order.id}/pay`).then(setInfo).catch((e) => setErr2(e.message)); }, [order.id]);
  const submit = (e) => { e.preventDefault(); run(async () => { await api(`/medicines/orders/${order.id}/pay`, { method: "POST", body: { utr } }); onDone(); }); };
  if (err2) return <Alert tone="warn">{err2}</Alert>;
  if (!info) return <p className="text-sm text-slate-500">Loading payment…</p>;
  return (
    <div className="mt-2 grid gap-4 rounded-xl border border-brand-100 bg-brand-50 p-4 sm:grid-cols-[auto_1fr]">
      <div className="mx-auto rounded-xl bg-white p-3 shadow-sm"><QRCodeSVG value={info.upi_uri} size={176} /></div>
      <div className="space-y-2 text-sm">
        <p className="text-2xl font-bold">₹{info.amount}</p>
        <p>Pay to <b>{info.payee}</b> <span className="text-xs text-slate-500">({info.vpa})</span></p>
        <ol className="list-decimal space-y-1 pl-5 text-xs text-slate-600">
          <li>Scan this QR with any UPI app (GPay, PhonePe, Paytm, BHIM) or <a className="text-brand-700 underline" href={info.upi_uri}>open in UPI app</a> on your phone.</li>
          <li>After paying, enter the 12-digit UPI reference number (UTR) below.</li>
          <li>The pharmacy checks its account, then packs and delivers your order.</li>
        </ol>
        {info.demo && <Alert tone="warn">DEMO MODE: this pharmacy has no UPI ID, so the QR points to a placeholder that cannot receive money. Enter any 12 digits to continue the demo.</Alert>}
        <form onSubmit={submit} className="flex flex-wrap gap-2">
          <input className="input max-w-[220px]" inputMode="numeric" pattern="\d{12}" maxLength={12} required placeholder="12-digit UTR" value={utr} onChange={(e) => setUtr(e.target.value.replace(/\D/g, ""))} />
          <button className="btn-primary" disabled={busy}>I have paid</button>
        </form>
        <Alert tone="error">{error}</Alert>
      </div>
    </div>
  );
}

/** Live delivery position, refreshed every 10 s, on an OpenStreetMap embed. */
export function Track({ oid }) {
  const [t, setT] = useState(null);
  useEffect(() => { const f = () => api(`/medicines/orders/${oid}/track`).then(setT).catch(() => {}); f(); const i = setInterval(f, 10000); return () => clearInterval(i); }, [oid]);
  if (!t) return null;
  const l = t.location;
  if (!l) return <p className="text-xs text-slate-500">Out for delivery. Waiting for the rider to share location…</p>;
  const d = 0.01, bbox = `${l.lng - d},${l.lat - d},${l.lng + d},${l.lat + d}`;
  return (
    <div className="space-y-1">
      <p className="text-xs">{t.distance_km != null ? <>Rider is <b>{t.distance_km} km</b> away · about <b>{t.eta_minutes} min</b> (rough estimate)</> : "Rider location shared (no destination saved, so no ETA)"} · updated {l.ts.slice(11, 19)} UTC</p>
      <iframe title="Delivery map" className="h-44 w-full rounded-lg border border-slate-200" loading="lazy" src={`https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${l.lat},${l.lng}`} />
    </div>
  );
}

export function PatientOrder({ o, reload }) {
  const [pay, setPay] = useState(false);
  const p = o.payment || {};
  const canPay = p.method === "upi" && ["pending", "failed"].includes(p.status) && p.amount != null && !["rejected", "delivered"].includes(o.status);
  return (
    <li className="space-y-2 py-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span><b>{o.pharmacy_name}</b>: {o.items.map((i) => `${i.name}×${i.qty}`).join(", ")}</span>
        <span className="flex items-center gap-2">{p.amount != null && <b>₹{p.amount}</b>}<Badge tone={PAY_TONE[p.status]}>{PAY_LABEL[p.status] || p.status}</Badge></span>
      </div>
      <Timeline status={o.status} />
      {p.amount == null && <p className="text-xs text-amber-700">Waiting for the pharmacy to confirm the price.</p>}
      {o.status === "out_for_delivery" && <Track oid={o.id} />}
      {o.status === "out_for_delivery" && o.delivery_otp && (
        <p className="rounded-lg bg-emerald-50 px-3 py-2 text-emerald-800">Delivery code: <b className="text-lg tracking-widest">{o.delivery_otp}</b> <span className="text-xs">Tell this to the delivery person only when you receive your medicines.</span></p>
      )}
      {p.status === "failed" && <p className="text-xs text-red-700">The pharmacy could not find this payment. Check the UTR and pay again, or contact them.</p>}
      {canPay && !pay && <button className="btn-primary py-1.5" onClick={() => setPay(true)}>{p.status === "failed" ? "Pay again" : "Pay now (UPI QR)"}</button>}
      {pay && canPay && <PayPanel order={o} onDone={() => { setPay(false); reload(); }} />}
    </li>
  );
}
