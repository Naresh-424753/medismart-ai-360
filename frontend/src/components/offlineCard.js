/** Builds a self-contained HTML emergency medical card that works offline (save to phone / print). */
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export function downloadOfflineCard(p) {
  const allergies = (p.allergies || []).map((a) => `<li>${esc(a.name)}${a.severity ? ` (${esc(a.severity)})` : ""}</li>`).join("") || "<li>None recorded</li>";
  const conditions = (p.diseases || []).map((d) => `<li>${esc(d.name)}</li>`).join("") || "<li>None recorded</li>";
  const contacts = (p.emergency_contacts || []).map((c) => `<li>${esc(c.name)} (${esc(c.relation)}): <a href="tel:${esc(c.phone)}">${esc(c.phone)}</a></li>`).join("") || "<li>None recorded</li>";
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Emergency medical card</title>
<style>body{font-family:system-ui,sans-serif;max-width:480px;margin:0 auto;padding:16px;color:#0f172a}h1{color:#b91c1c;font-size:20px;margin:0}
.box{border:2px solid #b91c1c;border-radius:12px;padding:14px}.bg{font-size:42px;font-weight:800;color:#b91c1c}h2{font-size:13px;text-transform:uppercase;color:#64748b;margin:14px 0 4px}ul{margin:0;padding-left:18px}small{color:#64748b}</style></head>
<body><div class="box"><h1>EMERGENCY MEDICAL CARD</h1><p><b>${esc(p.name)}</b><br>Health ID: ${esc(p.health_id)}${p.dob ? `<br>DOB: ${esc(p.dob)}` : ""}</p>
<h2>Blood group</h2><div class="bg">${esc(p.blood_group || "Unknown")}</div><h2>Allergies</h2><ul>${allergies}</ul><h2>Medical conditions</h2><ul>${conditions}</ul>
<h2>Emergency contacts</h2><ul>${contacts}</ul><p><a href="tel:112">Call 112</a> &middot; <a href="tel:108">Ambulance 108</a></p></div>
<p><small>Saved ${new Date().toLocaleDateString()} from MediSmart AI 360. Keep this file on your phone; it works without internet. Re-download after you change your details.</small></p></body></html>`;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([html], { type: "text/html" }));
  a.download = `emergency-card-${p.health_id}.html`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
