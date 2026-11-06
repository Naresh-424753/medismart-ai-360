import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, tokenStore, wsUrl } from "../api.js";
import { Alert, Badge, Card } from "../components/ui.jsx";

/** In-app WebRTC consultation. Signalling goes through our server; audio/video is peer-to-peer (DTLS-SRTP encrypted). */
export default function Call() {
  const { aid } = useParams();
  const nav = useNavigate();
  const [cfg, setCfg] = useState(null);
  const [error, setError] = useState("");
  const [phase, setPhase] = useState("lobby"); // lobby | waiting | connecting | live | ended
  const [audioOnly, setAudioOnly] = useState(false);
  const [muted, setMuted] = useState(false);
  const [camOff, setCamOff] = useState(false);
  const [conn, setConn] = useState("");
  const [chat, setChat] = useState([]);
  const [text, setText] = useState("");
  const localV = useRef(); const remoteV = useRef();
  const pc = useRef(null); const ws = useRef(null); const stream = useRef(null); const pending = useRef([]);

  useEffect(() => { api(`/telemedicine/${aid}/config`).then(setCfg).catch((e) => setError(e.message)); return () => hangup(false); }, [aid]); // eslint-disable-line

  const send = (m) => ws.current?.readyState === 1 && ws.current.send(JSON.stringify(m));

  const makePc = () => {
    pc.current?.close();
    const p = new RTCPeerConnection({ iceServers: cfg.ice_servers });
    stream.current.getTracks().forEach((t) => p.addTrack(t, stream.current));
    p.onicecandidate = (e) => e.candidate && send({ type: "candidate", candidate: e.candidate });
    p.ontrack = (e) => { if (remoteV.current) remoteV.current.srcObject = e.streams[0]; };
    p.onconnectionstatechange = () => { setConn(p.connectionState); if (p.connectionState === "connected") setPhase("live"); if (p.connectionState === "failed") setError("Could not connect directly. Ask your hospital to enable a TURN server, or use the backup video link."); };
    pending.current = [];
    pc.current = p;
    return p;
  };

  const onMsg = async (ev) => {
    const m = JSON.parse(ev.data);
    if (m.type === "error") { setError(m.message); setPhase("lobby"); return; }
    if (m.type === "joined") { setPhase(m.peers ? "connecting" : "waiting"); return; }
    if (m.type === "ready") {
      setPhase("connecting");
      const p = makePc();
      if (cfg.me === m.initiator) { const o = await p.createOffer(); await p.setLocalDescription(o); send({ type: "offer", sdp: o }); }
      return;
    }
    if (m.type === "offer") {
      const p = pc.current || makePc();
      await p.setRemoteDescription(m.sdp);
      for (const c of pending.current) await p.addIceCandidate(c);
      pending.current = [];
      const a = await p.createAnswer(); await p.setLocalDescription(a); send({ type: "answer", sdp: a });
    } else if (m.type === "answer") {
      await pc.current?.setRemoteDescription(m.sdp);
      for (const c of pending.current) await pc.current.addIceCandidate(c);
      pending.current = [];
    } else if (m.type === "candidate") {
      if (pc.current?.remoteDescription) await pc.current.addIceCandidate(m.candidate).catch(() => {}); else pending.current.push(m.candidate);
    } else if (m.type === "chat") setChat((c) => [...c, { mine: false, text: m.text }]);
    else if (m.type === "peer-left") { pc.current?.close(); setPhase("waiting"); setConn(""); if (remoteV.current) remoteV.current.srcObject = null; }
  };

  const join = async () => {
    setError("");
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: true, video: !audioOnly });
    } catch { setError("Camera/microphone permission is needed. Allow access in your browser and try again."); return; }
    if (localV.current) localV.current.srcObject = stream.current;
    const s = new WebSocket(wsUrl(`/telemedicine/ws/${aid}`));
    ws.current = s;
    s.onopen = () => s.send(JSON.stringify({ type: "auth", token: tokenStore.get() }));
    s.onmessage = onMsg;
    s.onclose = () => setPhase((p) => (p === "ended" ? p : "lobby"));
    setPhase("waiting");
  };

  function hangup(go = true) {
    send({ type: "hangup" });
    ws.current?.close(); ws.current = null;
    pc.current?.close(); pc.current = null;
    stream.current?.getTracks().forEach((t) => t.stop()); stream.current = null;
    if (go) { setPhase("ended"); nav("/appointments"); }
  }
  const toggle = (kind) => {
    const tracks = kind === "audio" ? stream.current?.getAudioTracks() : stream.current?.getVideoTracks();
    tracks?.forEach((t) => (t.enabled = !t.enabled));
    kind === "audio" ? setMuted((v) => !v) : setCamOff((v) => !v);
  };
  const sendChat = (e) => { e.preventDefault(); if (!text.trim()) return; send({ type: "chat", text }); setChat((c) => [...c, { mine: true, text }]); setText(""); };

  if (error && !cfg) return <Card title="Video consultation"><Alert tone="error">{error}</Alert></Card>;
  if (!cfg) return <p className="text-slate-500">Loading…</p>;
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-bold">Consultation with {cfg.other_name}</h1>
        <Badge tone={phase === "live" ? "good" : "info"}>{phase === "live" ? "connected" : phase}{conn && phase !== "live" ? ` · ${conn}` : ""}</Badge>
      </div>
      <Alert tone="error">{error}</Alert>
      {phase === "lobby" ? (
        <Card title="Before you join">
          <p className="mb-3 text-sm text-slate-600">{cfg.date} {cfg.time}. Use headphones in a quiet place. Audio and video go directly between you and {cfg.other_name}.</p>
          <label className="mb-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={audioOnly} onChange={(e) => setAudioOnly(e.target.checked)} /> Audio only (saves data on a weak network)</label>
          <button className="btn-primary" onClick={join}>Join consultation</button>
          {cfg.fallback_url && <p className="mt-3 text-xs text-slate-500">Problems? <a className="underline" href={cfg.fallback_url} target="_blank" rel="noreferrer">Use the backup video link</a>.</p>}
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-3">
          <div className="relative md:col-span-2">
            <video ref={remoteV} autoPlay playsInline className="aspect-video w-full rounded-xl bg-slate-900" />
            {phase !== "live" && <p className="absolute inset-0 flex items-center justify-center text-white">{phase === "waiting" ? `Waiting for ${cfg.other_name} to join…` : "Connecting…"}</p>}
            <video ref={localV} autoPlay playsInline muted className="absolute bottom-3 right-3 w-32 rounded-lg border-2 border-white bg-slate-700 shadow" />
            <div className="mt-3 flex justify-center gap-2">
              <button className="btn-ghost" onClick={() => toggle("audio")}>{muted ? "🔇 Unmute" : "🎤 Mute"}</button>
              {!audioOnly && <button className="btn-ghost" onClick={() => toggle("video")}>{camOff ? "📷 Camera on" : "📷 Camera off"}</button>}
              <button className="btn-danger" onClick={() => hangup(true)}>End call</button>
            </div>
          </div>
          <Card title="Chat">
            <div className="mb-2 h-64 space-y-1 overflow-y-auto text-sm">{chat.map((c, i) => <p key={i} className={c.mine ? "text-right" : ""}><span className={`inline-block rounded-2xl px-3 py-1 ${c.mine ? "bg-brand-600 text-white" : "bg-slate-100"}`}>{c.text}</span></p>)}</div>
            <form onSubmit={sendChat} className="flex gap-2"><input className="input" value={text} maxLength={500} onChange={(e) => setText(e.target.value)} placeholder="Message" /><button className="btn-primary">Send</button></form>
          </Card>
        </div>
      )}
      <p className="text-xs text-slate-500">Not for emergencies: call 112 / 108. Consultations are not recorded by MediSmart.</p>
    </>
  );
}
