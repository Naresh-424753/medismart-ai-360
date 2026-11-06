import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Alert, Badge, Card, Empty, useAsync } from "../components/ui.jsx";

export default function Messages() {
  const { user } = useAuth();
  const [threads, setThreads] = useState([]);
  const [open, setOpen] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState("");
  const { error, run } = useAsync();
  const end = useRef();

  const loadThreads = () => api("/messages/threads").then(setThreads).catch(() => {});
  const loadMsgs = (id) => api(`/messages/${id}`).then(setMsgs).catch(() => {});
  useEffect(() => { loadThreads(); }, []);
  useEffect(() => {
    if (!open) return;
    loadMsgs(open.user_id);
    const t = setInterval(() => { loadMsgs(open.user_id); loadThreads(); }, 5000); // simple polling
    return () => clearInterval(t);
  }, [open]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  const send = (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    run(async () => { await api(`/messages/${open.user_id}`, { method: "POST", body: { text } }); setText(""); loadMsgs(open.user_id); loadThreads(); });
  };

  return (
    <>
      <h1 className="text-xl font-bold">{user.role === "doctor" ? "Patient messages" : "Chat with my doctor"}</h1>
      <div className="grid gap-4 md:grid-cols-3">
        <Card title="Conversations">
          {threads.length === 0 ? <Empty>You can chat with {user.role === "doctor" ? "patients" : "doctors"} once you have an appointment together.</Empty> : (
            <ul className="space-y-1">
              {threads.map((t) => (
                <li key={t.user_id}>
                  <button onClick={() => setOpen(t)} className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm ${open?.user_id === t.user_id ? "bg-brand-50" : "hover:bg-slate-100"}`}>
                    <span><span className="font-medium">{t.name}</span><br /><span className="text-xs text-slate-500">{t.last?.text?.slice(0, 40) || "No messages yet"}</span></span>
                    {t.unread > 0 && <Badge tone="bad">{t.unread}</Badge>}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title={open ? open.name : "Select a conversation"} className="md:col-span-2">
          {open && (
            <>
              <div className="mb-3 h-80 space-y-2 overflow-y-auto rounded-lg bg-slate-50 p-3">
                {msgs.length === 0 && <Empty>Say hello 👋</Empty>}
                {msgs.map((m) => (
                  <div key={m.id} className={`flex ${m.from === user.id ? "justify-end" : "justify-start"}`}>
                    <div className={`max-w-[75%] rounded-2xl px-3 py-2 text-sm ${m.from === user.id ? "bg-brand-600 text-white" : "bg-white text-slate-800 shadow-sm"}`}>
                      {m.text}<div className={`mt-0.5 text-[10px] ${m.from === user.id ? "text-brand-100" : "text-slate-400"}`}>{new Date(m.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</div>
                    </div>
                  </div>
                ))}
                <div ref={end} />
              </div>
              <form onSubmit={send} className="flex gap-2">
                <input className="input" value={text} maxLength={2000} onChange={(e) => setText(e.target.value)} placeholder="Type a message…" />
                <button className="btn-primary">Send</button>
              </form>
              <p className="mt-2 text-xs text-slate-500">Not for emergencies. Call 112 / 108 if someone is in danger.</p>
              <Alert tone="error">{error}</Alert>
            </>
          )}
        </Card>
      </div>
    </>
  );
}
