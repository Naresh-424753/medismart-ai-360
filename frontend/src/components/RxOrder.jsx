import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Alert, Badge, useAsync } from "./ui.jsx";

/** Pick a partner pharmacy for a list of medicines (ranked by live stock, price, same city) and place the order. */
export default function RxOrder({ names, rxId, onClose, onPlaced }) {
  const [list, setList] = useState(null);
  const [pick, setPick] = useState("");
  const [pay, setPay] = useState("upi");
  const [addr, setAddr] = useState("");
  const [dest, setDest] = useState(null);
  const { busy, error, run } = useAsync();
  const [err0, setErr0] = useState("");
  useEffect(() => {
    api(`/medicines/orders/suggest?items=${encodeURIComponent(names.join(","))}`).then(setList).catch((e) => setErr0(e.message));
    api("/patients/me").then((p) => setAddr((a) => a || [p.address, p.city].filter(Boolean).join(", "))).catch(() => {});
  }, []); // eslint-disable-line
  const here = () => navigator.geolocation?.getCurrentPosition((p) => setDest({ lat: p.coords.latitude, lng: p.coords.longitude }), () => setErr0("Location permission denied."));
  const place = () => run(async () => {
    const body = { pharmacy_id: pick, address: addr, payment_method: pay, rx_id: rxId || null, items: names.map((n) => ({ name: n, qty: 1 })), ...(dest ? { dest_lat: dest.lat, dest_lng: dest.lng } : {}) };
    onPlaced(await api("/medicines/orders", { method: "POST", body }));
  });
  const chosen = list?.find((p) => p.pharmacy_id === pick);
  return (
    <div className="space-y-3 rounded-xl border border-brand-100 bg-brand-50 p-4 text-sm">
      <div className="flex items-center justify-between"><b>Order: {names.join(", ")}</b><button className="text-xs text-slate-500 underline" onClick={onClose}>Close</button></div>
      <Alert tone="error">{err0 || error}</Alert>
      {!list && !err0 && <p className="text-slate-500">Finding pharmacies…</p>}
      <ul className="space-y-2">
        {list?.map((p) => {
          const ok = p.live_inventory && p.missing.length === 0;
          return (
            <li key={p.pharmacy_id}>
              <label className={`flex cursor-pointer items-start gap-3 rounded-lg border bg-white p-3 ${pick === p.pharmacy_id ? "border-brand-600 ring-1 ring-brand-600" : "border-slate-200"} ${p.live_inventory && !ok ? "opacity-60" : ""}`}>
                <input type="radio" name="ph" className="mt-1" disabled={p.live_inventory && !ok} checked={pick === p.pharmacy_id} onChange={() => setPick(p.pharmacy_id)} />
                <span className="flex-1">
                  <b>{p.name}</b> <span className="text-xs text-slate-500">{p.city}{p.address && `, ${p.address}`}{p.open_24h && " · open 24h"}</span>
                  <span className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                    {p.same_city && <Badge tone="info">your city</Badge>}
                    {p.live_inventory ? (ok ? <Badge tone="good">all in stock</Badge> : <Badge tone="warn">missing: {p.missing.map((m) => m.name).join(", ")}</Badge>) : <Badge tone="muted">stock not synced - pharmacy confirms</Badge>}
                    {p.total != null && <b>₹{p.total}</b>}
                    {!p.has_upi && <span className="text-slate-400">no UPI</span>}
                  </span>
                </span>
              </label>
            </li>
          );
        })}
      </ul>
      {pick && (
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="block sm:col-span-2"><span className="label">Delivery address</span><input className="input" required value={addr} onChange={(e) => setAddr(e.target.value)} /></label>
          <label className="block"><span className="label">Payment</span><select className="input" value={pay} onChange={(e) => setPay(e.target.value)}><option value="upi">Pay online with UPI QR</option><option value="cod">Cash on delivery</option></select></label>
          <div className="flex items-end gap-2"><button type="button" className="btn-ghost" onClick={here}>{dest ? "✔ Location saved" : "Use my location for live tracking"}</button></div>
          <div className="sm:col-span-2"><button className="btn-primary" disabled={busy || !addr.trim()} onClick={place}>{busy ? "Placing…" : `Place order${chosen?.total != null ? ` (₹${chosen.total})` : ""}`}</button></div>
        </div>
      )}
    </div>
  );
}
