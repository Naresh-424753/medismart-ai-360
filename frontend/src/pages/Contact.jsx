import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Alert, Field, useAsync } from "../components/ui.jsx";

const CATS = [["problem", "Problem using the app"], ["account", "Account / login / OTP"], ["payment", "Order or payment"], ["feedback", "Feedback"], ["other", "Other"]];

export default function Contact() {
  const { user } = useAuth();
  const [info, setInfo] = useState({});
  const [f, setF] = useState({ name: user?.name || "", email: user?.email || "", category: "problem", subject: "", message: "" });
  const [done, setDone] = useState("");
  const { error, run, busy } = useAsync();
  useEffect(() => { api("/contact/info").then(setInfo).catch(() => {}); }, []);
  const submit = (e) => {
    e.preventDefault();
    run(async () => { const r = await api("/contact", { method: "POST", body: f }); setDone(r.message); setF({ ...f, subject: "", message: "" }); });
  };
  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-brand-50 to-white p-4">
      <div className="w-full max-w-lg space-y-4">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-brand-700">Contact us</h1>
          <p className="text-sm text-slate-500">Having a problem? Tell us and the admin team will get back to you by email.</p>
        </div>
        <form onSubmit={submit} className="card space-y-3">
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="Your name"><input className="input" required minLength={2} maxLength={80} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
            <Field label="Your email"><input className="input" type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
          </div>
          <Field label="Topic"><select className="input" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>{CATS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
          <Field label="Subject"><input className="input" required minLength={3} maxLength={120} value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} /></Field>
          <Field label="Message"><textarea className="input min-h-[120px]" required minLength={10} maxLength={2000} value={f.message} onChange={(e) => setF({ ...f, message: e.target.value })} /></Field>
          <Alert tone="error">{error}</Alert><Alert tone="ok">{done}</Alert>
          <button className="btn-primary w-full" disabled={busy}>{busy ? "Sending…" : "Send message"}</button>
          <p className="text-xs text-slate-500">Never include passwords or OTP codes in your message. In a medical emergency call <a className="font-semibold underline" href="tel:112">112</a> or <a className="font-semibold underline" href="tel:108">108</a>.</p>
        </form>
        {info.support_whatsapp && (
          <a className="flex items-center justify-center gap-2 rounded-xl bg-[#25D366] px-4 py-2.5 font-semibold text-white shadow hover:opacity-90" target="_blank" rel="noreferrer"
            href={`https://wa.me/${info.support_whatsapp}?text=${encodeURIComponent(`Hello MediSmart support, ${f.name ? "I am " + f.name + ". " : ""}${f.subject ? f.subject + ". " : ""}${f.message || "I need help."}`.slice(0, 900))}`}>
            <svg viewBox="0 0 24 24" className="h-5 w-5 fill-current" aria-hidden="true"><path d="M12.04 2a9.9 9.9 0 0 0-8.5 14.9L2 22l5.27-1.38A9.9 9.9 0 1 0 12.04 2Zm5.8 14.07c-.25.7-1.45 1.34-2 1.4-.52.06-1.17.09-1.9-.12a12.5 12.5 0 0 1-5.5-4.1c-1.05-1.4-1.72-2.9-1.78-3.1-.06-.2-.43-1.1-.43-2.1s.53-1.5.72-1.7c.18-.2.4-.25.53-.25h.38c.12 0 .29-.05.45.35.17.4.58 1.4.63 1.5.05.1.08.22.02.35-.06.13-.1.2-.2.32l-.3.35c-.1.1-.2.21-.09.42.12.2.53.87 1.15 1.4.8.7 1.47.92 1.68 1.02.2.1.32.08.44-.05.12-.14.5-.6.64-.8.13-.2.27-.17.45-.1.18.07 1.17.55 1.37.65.2.1.33.15.38.23.05.08.05.48-.2 1.18Z" /></svg>
            Chat on WhatsApp
          </a>
        )}
        {(info.support_email || info.support_phone) && (
          <p className="text-center text-sm text-slate-600">{info.support_email && <>Email: <a className="underline" href={`mailto:${info.support_email}`}>{info.support_email}</a></>}{info.support_email && info.support_phone && " · "}{info.support_phone && <>Phone: <a className="underline" href={`tel:${info.support_phone}`}>{info.support_phone}</a></>}</p>
        )}
        <p className="text-center text-sm"><Link className="text-brand-700 hover:underline" to="/">← Back</Link></p>
      </div>
    </div>
  );
}

/** Small "Contact us" pill shown on every page (hidden on the contact page itself). */
export function ContactFab() {
  const { pathname } = useLocation();
  if (pathname === "/contact") return null;
  return <Link to="/contact" className="fixed bottom-4 left-1/2 z-30 -translate-x-1/2 rounded-full border border-slate-200 bg-white/95 px-4 py-1.5 text-xs font-medium text-brand-700 shadow-md hover:bg-brand-50">Need help? Contact us</Link>;
}
