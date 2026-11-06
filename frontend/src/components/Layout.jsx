import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import Icon from "./Icon.jsx";
import VoiceCommander from "./VoiceCommander.jsx";
import { saveLang, savedLang, useVoiceLangs } from "./voice.js";

const ICON = { "/": "home", "/risk": "brain", "/reports": "file", "/images": "scan", "/chat": "chat", "/medicines": "pill", "/rx-scan": "scan", "/rx-verify": "shield", "/appointments": "calendar", "/vitals": "heart", "/wearables": "watch", "/early-warning": "alert", "/federated": "grid", "/second-opinion": "brain", "/analytics": "chart", "/wellness": "smile", "/labs": "flask", "/hospitals": "building", "/blood": "drop", "/messages": "mail", "/extras": "tools", "/security": "lock", "/emergency": "ambulance", "/profile": "user", "/prescribe": "file", "/ops": "building" };

const NAV = {
  patient: [["/", "Dashboard"], ["/risk", "Risk Check"], ["/reports", "Reports"], ["/images", "Image AI"], ["/chat", "Assistant"], ["/medicines", "Medicines"], ["/rx-scan", "Rx Scanner"], ["/appointments", "Appointments"], ["/vitals", "Vitals"], ["/wearables", "Wearables"], ["/early-warning", "Early Warning"], ["/analytics", "Insights"], ["/wellness", "Wellness"], ["/labs", "Lab Tests"], ["/hospitals", "Hospitals"], ["/blood", "Blood"], ["/messages", "Messages"], ["/extras", "More Tools"], ["/second-opinion", "Second Opinion"], ["/security", "Record Security"], ["/emergency", "Emergency"], ["/profile", "My Health"]],
  doctor: [["/", "Dashboard"], ["/appointments", "Schedule & Profile"], ["/prescribe", "Prescriptions"], ["/rx-verify", "Verify Rx Scans"], ["/early-warning", "Early Warning"], ["/second-opinion", "Board Review"], ["/messages", "Messages"], ["/chat", "Assistant"]],
  family: [["/", "Patients"], ["/emergency", "Emergency"], ["/blood", "Blood"], ["/chat", "Assistant"]],
  pharmacist: [["/", "Pharmacy"], ["/rx-verify", "Verify Rx Scans"]],
  ambulance: [["/", "Emergencies"]],
  hospital: [["/", "Hospital"], ["/ops", "Operations"], ["/early-warning", "Early Warning"], ["/federated", "Federated Learning"]],
  lab: [["/", "Laboratory"]],
  blood_bank: [["/", "Blood Bank"], ["/blood", "Requests & Donors"]],
  admin: [["/", "Admin"], ["/analytics", "Population"], ["/federated", "Federated Learning"]],
  super_admin: [["/", "Admin"], ["/analytics", "Population"], ["/federated", "Federated Learning"]],
};

function Bell() {
  const [notes, setNotes] = useState([]);
  const [open, setOpen] = useState(false);
  const ref = useRef();
  const load = () => api("/patients/me/notifications").then(setNotes).catch(() => {});
  useEffect(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t); }, []);
  useEffect(() => { const h = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false); document.addEventListener("mousedown", h); return () => document.removeEventListener("mousedown", h); }, []);
  const unread = notes.filter((n) => !n.read).length;
  const markRead = async () => { await api("/patients/me/notifications/read", { method: "POST" }).catch(() => {}); load(); };
  return (
    <div className="relative" ref={ref}>
      <button aria-label="Notifications" onClick={() => setOpen(!open)} className="relative rounded-full p-2 text-slate-600 hover:bg-slate-100">
        <Icon name="bell" />
        {unread > 0 && <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">{unread > 9 ? "9+" : unread}</span>}
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-2 w-80 rounded-xl border border-slate-200 bg-white p-2 shadow-lg">
          <div className="flex items-center justify-between px-2 py-1"><b className="text-sm">Notifications</b>{unread > 0 && <button className="text-xs text-brand-700" onClick={markRead}>Mark all read</button>}</div>
          <ul className="max-h-80 divide-y divide-slate-100 overflow-y-auto">
            {notes.length === 0 && <li className="p-3 text-sm text-slate-500">Nothing yet.</li>}
            {notes.slice(0, 8).map((n) => <li key={n.id} className={`p-2 text-sm ${n.read ? "" : "bg-brand-50"}`}><p className="font-medium">{n.title}</p><p className="text-xs text-slate-600">{n.body}</p><p className="text-[10px] text-slate-400">{n.ts?.replace("T", " ").slice(0, 16)} UTC</p></li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

function QuickSearch({ links }) {
  const [q, setQ] = useState("");
  const nav = useNavigate();
  const hits = useMemo(() => (q.trim() ? links.filter(([, l]) => l.toLowerCase().includes(q.trim().toLowerCase())).slice(0, 6) : []), [q, links]);
  const go = (to) => { setQ(""); nav(to); };
  return (
    <div className="relative hidden w-full max-w-md md:block">
      <Icon name="search" className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
      <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && hits[0] && go(hits[0][0])} placeholder="Jump to a page: medicines, reports, vitals…" className="w-full rounded-full border border-transparent bg-slate-100 py-2 pl-9 pr-4 text-sm placeholder:text-slate-400 focus:border-brand-500 focus:bg-white focus:outline-none" />
      {hits.length > 0 && <ul className="absolute z-40 mt-1 w-full rounded-xl border border-slate-200 bg-white p-1 shadow-lg">{hits.map(([to, l]) => <li key={to}><button onClick={() => go(to)} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-100"><Icon name={ICON[to]} className="h-4 w-4 text-slate-500" />{l}</button></li>)}</ul>}
    </div>
  );
}

export const initials = (n = "") => n.split(" ").map((x) => x[0]).slice(0, 2).join("").toUpperCase();

export default function Layout() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const langs = useVoiceLangs();
  const [lang, setLang] = useState(savedLang());
  const [open, setOpen] = useState(false);
  const links = NAV[user.role] || [["/", "Home"]];
  const out = async () => { await logout(); nav("/login"); };
  return (
    <div className="min-h-screen bg-slate-50 md:flex">
      {open && <div className="fixed inset-0 z-30 bg-black/40 md:hidden" onClick={() => setOpen(false)} />}
      <aside className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col bg-navy-900 text-slate-200 transition-transform md:sticky md:top-0 md:h-screen md:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex items-center gap-3 px-5 py-5">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600 text-white"><Icon name="pulse" /></span>
          <div><p className="text-lg font-bold leading-tight text-white">MediSmart AI 360</p><p className="text-xs text-sky-300">Smart Healthcare Solutions</p></div>
        </div>
        <nav className="flex-1 space-y-1 overflow-y-auto px-3 pb-3">
          {links.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"} onClick={() => setOpen(false)}
              className={({ isActive }) => `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium ${isActive ? "bg-brand-600 text-white shadow" : "text-slate-300 hover:bg-white/10 hover:text-white"}`}>
              <Icon name={ICON[to]} className="h-5 w-5 shrink-0" />{label}
            </NavLink>
          ))}
        </nav>
        <div className="m-3 rounded-xl bg-gradient-to-br from-navy-800 to-navy-950 p-4 text-center ring-1 ring-white/10">
          <Icon name="heart" className="mx-auto h-8 w-8 text-sky-400" />
          <p className="mt-1 text-sm font-semibold text-white">Your Health, Our Priority</p>
          <p className="text-[11px] text-slate-400">AI Powered · Personalised · Secure</p>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-2.5 md:px-6">
          <button className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 md:hidden" aria-label="Menu" onClick={() => setOpen(true)}><Icon name="menu" /></button>
          <QuickSearch links={links} />
          <div className="ml-auto flex items-center gap-2">
            <label className="hidden items-center gap-1 rounded-full border border-slate-200 px-2 py-1 text-sm sm:flex">
              <Icon name="globe" className="h-4 w-4 text-slate-500" />
              <select aria-label="Voice and assistant language" value={lang} onChange={(e) => { setLang(e.target.value); saveLang(e.target.value); }} className="bg-transparent text-sm focus:outline-none">
                {(langs.length ? langs : [{ code: "en", name: "English" }]).map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
              </select>
            </label>
            <Bell />
            <div className="flex items-center gap-2 pl-1">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-100 text-sm font-bold text-brand-700">{initials(user.name)}</span>
              <div className="hidden leading-tight sm:block"><p className="text-sm font-semibold">{user.name}</p><p className="text-xs capitalize text-slate-500">{user.role.replace("_", " ")}{user.approved === false && " (pending)"}</p></div>
              <button onClick={out} aria-label="Log out" title="Log out" className="rounded-full p-2 text-slate-500 hover:bg-slate-100"><Icon name="logout" className="h-5 w-5" /></button>
            </div>
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1400px] flex-1 space-y-4 p-4 md:p-6">
          <Outlet />
        </main>
        <footer className="flex items-center justify-between border-t border-slate-200 bg-white px-6 py-2 text-xs text-slate-500"><span className="flex items-center gap-1"><Icon name="shield" className="h-4 w-4 text-brand-600" />Your data is secure with us</span><span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-emerald-500" />System online</span></footer>
      </div>
      <VoiceCommander />
    </div>
  );
}
