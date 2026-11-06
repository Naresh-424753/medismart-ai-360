import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Alert, Badge, Card, Disclaimer, Empty, Field, toneFor, useAsync } from "../components/ui.jsx";

const GROUPS = [
  ["chest_xray", "Chest X-ray (pneumonia / TB / lung screening)"], ["brain_mri", "Brain MRI (abnormality highlighting)"], ["skin", "Skin lesion (ABCD analysis)"],
  ["retina", "Retina (diabetic retinopathy screening)"], ["cataract", "Eye / cataract screening"], ["segment", "Medical image segmentation"],
  ["fracture", "Bone fracture detection"], ["tumor_classification", "Brain tumor classification"], ["pneumonia_classification", "Pneumonia classification"],
];

export default function ImageAI() {
  const [kind, setKind] = useState("chest_xray");
  const [file, setFile] = useState(null);
  const [res, setRes] = useState(null);
  const [models, setModels] = useState([]);
  const [hist, setHist] = useState([]);
  const { busy, error, run } = useAsync();
  const load = () => { api("/ai/image-models").then(setModels).catch(() => {}); api("/ai/image-history").then(setHist).catch(() => {}); };
  useEffect(load, []);
  const mode = (k) => models.find((m) => m.kind === k)?.mode;

  const go = (e) => {
    e.preventDefault();
    if (!file) return;
    run(async () => {
      const form = new FormData();
      form.append("file", file);
      setRes(await api(`/ai/image/${kind}`, { method: "POST", form }));
      load();
    });
  };
  const download = () => {
    const blob = new Blob([res.report], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `image-report-${res.task}.txt`;
    a.click();
  };

  return (
    <>
      <h1 className="text-xl font-bold">Medical image AI</h1>
      <Alert tone="warn">Screening support only. Without trained neural-network weights this uses classical image analysis that highlights areas worth a doctor's attention. It does not diagnose.</Alert>
      <Card title="Analyse an image">
        <form onSubmit={go} className="grid gap-3 sm:grid-cols-2">
          <Field label="Analysis type">
            <select className="input" value={kind} onChange={(e) => { setKind(e.target.value); setRes(null); }}>
              {GROUPS.map(([k, l]) => <option key={k} value={k}>{l}{mode(k) === "needs-trained-model" ? " (needs trained model)" : ""}</option>)}
            </select>
          </Field>
          <Field label="Image (PNG / JPEG, max 10 MB)"><input className="input" type="file" accept="image/png,image/jpeg" onChange={(e) => setFile(e.target.files[0])} /></Field>
          <div className="sm:col-span-2"><button className="btn-primary" disabled={busy || !file}>{busy ? "Analysing…" : "Analyse"}</button></div>
        </form>
        <div className="mt-3"><Alert tone="error">{error}</Alert></div>
      </Card>

      {res && res.available === false && <Alert tone="info">{res.message}</Alert>}
      {res && res.available !== false && (
        <Card title="Result" action={<button className="btn-ghost" onClick={download}>Download report</button>}>
          <div className="grid gap-4 md:grid-cols-2">
            {res.overlay_png && <img src={res.overlay_png} alt="Analysed image with highlighted regions" className="w-full rounded-lg border border-slate-200" />}
            <div className="space-y-2 text-sm">
              <p><Badge tone={toneFor(res.level)}>{res.level || res.mode}</Badge> <span className="ml-1 text-slate-500">{res.mode === "cnn" ? "trained model" : "demo image analysis"}</span></p>
              <p className="font-medium">{res.finding}</p>
              {res.metrics && Object.keys(res.metrics).length > 0 && (
                <table className="w-full text-xs"><tbody>{Object.entries(res.metrics).map(([k, v]) => <tr key={k} className="border-t border-slate-100"><td className="py-1 capitalize text-slate-500">{k.replace(/_/g, " ")}</td><td className="py-1 text-right">{String(v)}</td></tr>)}</tbody></table>
              )}
              <pre className="whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-xs text-slate-700">{res.report}</pre>
            </div>
          </div>
        </Card>
      )}
      <Card title="Previous analyses">
        {hist.length === 0 ? <Empty>No images analysed yet.</Empty> : (
          <ul className="divide-y divide-slate-100 text-sm">
            {hist.map((h) => <li key={h.id} className="py-2"><span className="font-medium">{h.kind.replace(/_/g, " ")}</span> <span className="text-slate-500">· {new Date(h.ts).toLocaleString()} · {h.result?.finding || h.result?.message || ""}</span></li>)}
          </ul>
        )}
      </Card>
      <Disclaimer />
    </>
  );
}
