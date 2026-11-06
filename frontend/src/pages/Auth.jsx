import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Alert, Field, useAsync } from "../components/ui.jsx";

const ROLES = [
  ["patient", "Patient"], ["doctor", "Doctor"], ["family", "Family member"], ["pharmacist", "Pharmacist"],
  ["hospital", "Hospital"], ["ambulance", "Ambulance"], ["lab", "Lab"], ["blood_bank", "Blood bank"],
];

function Shell({ title, children }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-brand-50 to-white p-4">
      <div className="w-full max-w-md space-y-4">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-brand-700">MediSmart AI 360</h1>
          <p className="text-sm text-slate-500">Diagnose early. Treat precisely. Heal faster.</p>
        </div>
        <div className="card space-y-4">
          <h2 className="text-lg font-semibold">{title}</h2>
          {children}
        </div>
      </div>
    </div>
  );
}

export function Login() {
  const { user, login, verifyLoginOtp } = useAuth();
  const nav = useNavigate();
  const [f, setF] = useState({ email: "", password: "", otp: "" });
  const [needOtp, setNeedOtp] = useState(false);
  const { busy, error, run } = useAsync();
  if (user) return <Navigate to="/" replace />;

  const submit = (e) => {
    e.preventDefault();
    run(async () => {
      if (needOtp) {
        await verifyLoginOtp(f.email, f.otp);
        return nav("/");
      }
      const r = await login(f.email, f.password);
      if (r.requires_otp) {
        setNeedOtp(true);
      } else nav("/");
    });
  };
  return (
    <Shell title="Log in">
      <form onSubmit={submit} className="space-y-3">
        <Field label="Email"><input className="input" type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="Password"><input className="input" type="password" required value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
        {needOtp && (
          <Field label="2FA code"><input className="input" inputMode="numeric" maxLength={6} required value={f.otp} onChange={(e) => setF({ ...f, otp: e.target.value })} /></Field>
        )}
        <Alert tone="error">{error}</Alert>
        <button className="btn-primary w-full" disabled={busy}>{busy ? "Please wait…" : needOtp ? "Verify & log in" : "Log in"}</button>
      </form>
      <div className="flex justify-between text-sm">
        <Link className="text-brand-700 hover:underline" to="/forgot">Forgot password?</Link>
        <Link className="text-brand-700 hover:underline" to="/kiosk">Health kiosk</Link>
        <Link className="text-brand-700 hover:underline" to="/register">Create account</Link>
      </div>
    </Shell>
  );
}

export function Register() {
  const nav = useNavigate();
  const [f, setF] = useState({ name: "", email: "", phone: "", password: "", role: "patient" });
  const [step, setStep] = useState("form");
  const [otp, setOtp] = useState("");
  const [info, setInfo] = useState("");
  const { busy, error, run } = useAsync();
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = (e) => {
    e.preventDefault();
    run(async () => {
      const r = await api("/auth/register", { method: "POST", body: { ...f } });
      setInfo(r.message);
      setStep("otp");
    });
  };
  const verify = (e) => {
    e.preventDefault();
    run(async () => {
      await api("/auth/verify-otp", { method: "POST", body: { email: f.email, otp } });
      nav("/login");
    });
  };
  const resend = () => run(async () => { await api("/auth/resend-otp", { method: "POST", body: { email: f.email, purpose: "register" } }); setInfo("A new code was sent to your email."); });
  return (
    <Shell title={step === "form" ? "Create your account" : "Verify your email"}>
      {step === "form" ? (
        <form onSubmit={submit} className="space-y-3">
          <Field label="Full name"><input className="input" required minLength={2} value={f.name} onChange={set("name")} /></Field>
          <Field label="Email"><input className="input" type="email" required value={f.email} onChange={set("email")} /></Field>
          <Field label="Mobile (optional, with country code)"><input className="input" placeholder="+919876543210" value={f.phone} onChange={set("phone")} /></Field>
          <Field label="Password (8+ chars, letters and digits)"><input className="input" type="password" required minLength={8} value={f.password} onChange={set("password")} /></Field>
          <Field label="I am a">
            <select className="input" value={f.role} onChange={set("role")}>{ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          </Field>
          <Alert tone="error">{error}</Alert>
          <button className="btn-primary w-full" disabled={busy}>{busy ? "Creating…" : "Register"}</button>
        </form>
      ) : (
        <form onSubmit={verify} className="space-y-3">
          <Alert tone="info">{info}</Alert>
          <p className="text-sm text-slate-600">We sent a 6-digit code to <b>{f.email}</b>. Enter it to verify that this email is yours. Your account stays locked until you do.</p>
          <Field label="6-digit code"><input className="input" inputMode="numeric" maxLength={6} required value={otp} onChange={(e) => setOtp(e.target.value)} /></Field>
          <Alert tone="error">{error}</Alert>
          <button className="btn-primary w-full" disabled={busy}>Verify</button>
          <div className="flex justify-between text-sm">
            <button type="button" className="text-brand-700 hover:underline" disabled={busy} onClick={resend}>Resend code</button>
            <button type="button" className="text-slate-500 hover:underline" onClick={() => { setStep("form"); setOtp(""); }}>Wrong email? Change it</button>
          </div>
        </form>
      )}
      <p className="text-sm">Already registered? <Link className="text-brand-700 hover:underline" to="/login">Log in</Link></p>
    </Shell>
  );
}

export function ForgotPassword() {
  const nav = useNavigate();
  const [f, setF] = useState({ email: "", otp: "", new_password: "" });
  const [sent, setSent] = useState(false);
  const [info, setInfo] = useState("");
  const { busy, error, run } = useAsync();

  const send = (e) => {
    e.preventDefault();
    run(async () => {
      const r = await api("/auth/forgot-password", { method: "POST", body: { email: f.email } });
      setInfo(r.message);
      setSent(true);
    });
  };
  const reset = (e) => {
    e.preventDefault();
    run(async () => {
      await api("/auth/reset-password", { method: "POST", body: f });
      nav("/login");
    });
  };
  return (
    <Shell title="Reset password">
      <form onSubmit={sent ? reset : send} className="space-y-3">
        <Field label="Email"><input className="input" type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        {sent && (
          <>
            <Alert tone="info">{info}</Alert>
            <Field label="6-digit code"><input className="input" inputMode="numeric" maxLength={6} required value={f.otp} onChange={(e) => setF({ ...f, otp: e.target.value })} /></Field>
            <Field label="New password"><input className="input" type="password" required minLength={8} value={f.new_password} onChange={(e) => setF({ ...f, new_password: e.target.value })} /></Field>
          </>
        )}
        <Alert tone="error">{error}</Alert>
        <button className="btn-primary w-full" disabled={busy}>{sent ? "Set new password" : "Send code"}</button>
      </form>
      <Link className="text-sm text-brand-700 hover:underline" to="/login">Back to log in</Link>
    </Shell>
  );
}
