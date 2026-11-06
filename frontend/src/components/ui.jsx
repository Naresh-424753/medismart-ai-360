import { useState } from "react";

export const Card = ({ title, action, children, className = "" }) => (
  <section className={`card ${className}`}>
    {(title || action) && (
      <header className="mb-3 flex items-center justify-between">
        <h2 className="text-base font-semibold text-slate-900">{title}</h2>
        {action}
      </header>
    )}
    {children}
  </section>
);

const TONES = {
  good: "bg-emerald-100 text-emerald-800",
  warn: "bg-amber-100 text-amber-800",
  bad: "bg-red-100 text-red-700",
  info: "bg-sky-100 text-sky-800",
  muted: "bg-slate-100 text-slate-600",
};
export const Badge = ({ tone = "muted", children }) => (
  <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${TONES[tone]}`}>{children}</span>
);
export const toneFor = (v) =>
  ({ low: "good", normal: "good", taken: "good", moderate: "warn", due: "warn", upcoming: "info", high: "bad", missed: "bad", critical: "bad", warning: "warn" }[v] || "muted");

export const Alert = ({ tone = "info", children }) => {
  const c = { info: "border-sky-200 bg-sky-50 text-sky-900", error: "border-red-200 bg-red-50 text-red-800", ok: "border-emerald-200 bg-emerald-50 text-emerald-800", warn: "border-amber-200 bg-amber-50 text-amber-900" }[tone];
  return children ? <div role="alert" className={`rounded-lg border px-3 py-2 text-sm ${c}`}>{children}</div> : null;
};

export const Field = ({ label, children }) => (
  <label className="block">
    <span className="label">{label}</span>
    {children}
  </label>
);

export function useAsync() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = async (fn) => {
    setBusy(true);
    setError("");
    try {
      return await fn();
    } catch (e) {
      setError(e.message);
      return undefined;
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, setError, run };
}

export const Disclaimer = () => (
  <p className="text-xs text-slate-500">Educational screening and information only, not a diagnosis. Consult a doctor for medical advice. Emergency: call 112 / 108.</p>
);

export const listToText = (a) => (a || []).join(", ");
export const textToList = (s) => s.split(",").map((x) => x.trim()).filter(Boolean);

export const Stat = ({ label, value, sub }) => (
  <div className="card">
    <p className="text-3xl font-bold text-brand-700">{value ?? "—"}</p>
    <p className="text-xs text-slate-500">{label}</p>
    {sub && <p className="mt-1 text-xs text-slate-400">{sub}</p>}
  </div>
);

export const Empty = ({ children }) => <p className="text-sm text-slate-500">{children}</p>;
export const isoToday = () => new Date().toISOString().slice(0, 10);
export const sortedEntries = (o) => Object.entries(o || {}).sort(([a], [b]) => (a < b ? -1 : 1));
