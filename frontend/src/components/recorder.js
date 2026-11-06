// Records microphone audio and returns a 16 kHz mono 16-bit WAV Blob (accepted by Whisper and Bhashini).
export async function startWavRecorder(maxSeconds = 30, onAutoStop) {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
  const Ctx = window.AudioContext || window.webkitAudioContext;
  const ctx = new Ctx();
  const src = ctx.createMediaStreamSource(stream);
  const proc = ctx.createScriptProcessor(4096, 1, 1);
  const chunks = [];
  proc.onaudioprocess = (e) => chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
  src.connect(proc); proc.connect(ctx.destination);
  let done = false, timer;
  const finish = async () => {
    if (done) return null;
    done = true; clearTimeout(timer);
    proc.disconnect(); src.disconnect(); stream.getTracks().forEach((t) => t.stop());
    const rate = ctx.sampleRate; await ctx.close().catch(() => {});
    return encodeWav(downsample(merge(chunks), rate, 16000), 16000);
  };
  timer = setTimeout(async () => { const b = await finish(); onAutoStop?.(b); }, maxSeconds * 1000);
  return { stop: finish };
}
const merge = (chunks) => { const n = chunks.reduce((a, c) => a + c.length, 0); const out = new Float32Array(n); let o = 0; chunks.forEach((c) => { out.set(c, o); o += c.length; }); return out; };
function downsample(buf, from, to) {
  if (from === to) return buf;
  const ratio = from / to, n = Math.floor(buf.length / ratio), out = new Float32Array(n);
  for (let i = 0; i < n; i++) { const a = Math.floor(i * ratio), b = Math.min(buf.length, Math.floor((i + 1) * ratio)); let s = 0; for (let j = a; j < b; j++) s += buf[j]; out[i] = s / Math.max(1, b - a); }
  return out;
}
function encodeWav(samples, rate) {
  const buf = new ArrayBuffer(44 + samples.length * 2), v = new DataView(buf);
  const w = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  w(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); w(8, "WAVE"); w(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, "data"); v.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) { const s = Math.max(-1, Math.min(1, samples[i])); v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true); }
  return new Blob([buf], { type: "audio/wav" });
}
