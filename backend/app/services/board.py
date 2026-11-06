"""Second-opinion workflow: complexity triggers, a 3-method AI ensemble, and report assembly.

HONESTY NOTES
* The "three independent models" are three independent METHODS: (1) the nine ML risk models, (2) a rule engine over lab findings,
  vitals and symptoms, (3) an LLM when LLM_API_KEY is set. Without a key only two run and the report says so.
* The ML models are trained on synthetic data and the rules are simple. Outputs are decision support for a clinician, never a diagnosis.
* Rare-disease detection is a keyword match against a small curated list; it is NOT exhaustive.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

from . import ml, symptoms, vitals_rules

CANON = {
    "diabetes": ("Diabetes / glucose disorder", "Endocrinologist"), "heart": ("Heart disease", "Cardiologist"), "kidney": ("Kidney disease", "Nephrologist"),
    "liver": ("Liver disease", "Gastroenterologist"), "stroke": ("Stroke risk", "Neurologist"), "hypertension": ("Hypertension", "Cardiologist"),
    "thyroid": ("Thyroid disorder", "Endocrinologist"), "anemia": ("Anaemia", "General Physician"), "cancer": ("Cancer (needs screening workup)", "Oncologist"),
    "dyslipidaemia": ("Dyslipidaemia", "Cardiologist"), "infection": ("Infection / inflammation", "General Physician"), "acute": ("Acute physiological deterioration", "General Physician"),
}
SPEC_FALLBACK = "General Physician"
RARE = ["cystic fibrosis", "huntington", "amyotrophic", "als ", "myasthenia", "guillain", "sarcoidosis", "wilson disease", "amyloidosis", "scleroderma", "pulmonary hypertension",
        "marfan", "thalassemia major", "hemophilia", "sickle cell", "multiple sclerosis", "lupus", "addison", "cushing", "pheochromocytoma", "acromegaly", "porphyria", "gaucher",
        "duchenne", "fabry", "pompe", "behcet", "takayasu", "vasculitis", "hemochromatosis"]
TEST_MAP = {"glucose": "diabetes", "hba1c": "diabetes", "fasting": "diabetes", "creatinine": "kidney", "urea": "kidney", "egfr": "kidney", "bun": "kidney", "uric": "kidney",
            "alt": "liver", "ast": "liver", "sgpt": "liver", "sgot": "liver", "bilirubin": "liver", "alp": "liver", "albumin": "liver",
            "tsh": "thyroid", "t3": "thyroid", "t4": "thyroid", "hemoglobin": "anemia", "haemoglobin": "anemia", "rbc": "anemia", "ferritin": "anemia", "mcv": "anemia",
            "ldl": "dyslipidaemia", "cholesterol": "dyslipidaemia", "triglyceride": "dyslipidaemia", "hdl": "dyslipidaemia", "wbc": "infection", "crp": "infection", "esr": "infection", "platelet": "infection"}
SYMPTOM_MAP = {"diabetes": "diabetes", "thyroid": "thyroid", "anemia": "anemia", "anaemia": "anemia", "hypertension": "hypertension", "heart": "heart", "cardiac": "heart", "kidney": "kidney", "liver": "liver", "stroke": "stroke"}


def _key_for_title(title: str) -> str | None:
    t = title.lower()
    for k in CANON:
        if k in t:
            return k
    for word, k in SYMPTOM_MAP.items():
        if word in t:
            return k
    return None


def triggers(risks: list[dict], findings: list[dict], conditions: list[str], extra_text: str = "", vitals_status: str | None = None) -> list[str]:
    out = []
    high = [r for r in risks if r.get("level") == "high"]
    if len(high) >= 2:
        out.append("multi_high_risk: " + ", ".join(r["disease"] for r in high))
    crit = [f for f in findings if f.get("severity") == "critical" and f.get("status") != "normal"]
    if crit:
        out.append("critical_lab_values: " + ", ".join(f["test"] for f in crit[:5]))
    if vitals_status == "critical" and high:
        out.append("critical_vitals_with_high_risk")
    blob = (" ".join(conditions) + " " + extra_text).lower() + " "
    hit = [w.strip() for w in RARE if w in blob]
    if hit:
        out.append("rare_condition_keyword: " + ", ".join(sorted(set(hit))[:4]))
    return out


# ---------------- providers ----------------
def provider_risk_models(values: dict, stored: dict | None = None) -> dict:
    """Uses the larger of (a) a fresh prediction from the patient's profile/vitals/labs and (b) the latest risk check the patient actually ran."""
    stored = stored or {}
    res = sorted((ml.predict(d, values) for d in ml.SPECS), key=lambda r: -max(r["probability"], stored.get(r["disease"], 0)))
    items = []
    for r in res[:4]:
        k = r["disease"] if r["disease"] in CANON else _key_for_title(r["title"])
        p = max(r["probability"], stored.get(r["disease"], 0))
        if k and p >= 0.15:
            items.append({"key": k, "score": round(p, 3), "why": f"{r['title']}: {round(p * 100)}%"})
    return {"provider": "risk_models", "label": "ML risk models (synthetic-data demo)", "available": True, "items": items[:3]}


def provider_rules(findings: list[dict], symptom_list: list[str], note: str, vitals_status: str | None) -> dict:
    tally: dict[str, list[str]] = {}
    for f in findings:
        if f.get("status") == "normal":
            continue
        name = (f.get("key") or f.get("test") or "").lower()
        for frag, k in TEST_MAP.items():
            if frag in name or frag in (f.get("test") or "").lower():
                tally.setdefault(k, []).append(f"{f['test']} {f['status']}")
                break
    items = [{"key": k, "score": round(min(0.95, 0.4 + 0.15 * len(v)), 3), "why": "; ".join(v[:4])} for k, v in tally.items()]
    if symptom_list or note:
        for c in symptoms.check(symptom_list, note)["possible_conditions"][:3]:
            k = _key_for_title(c["condition"]) or "infection" if any(w in c["condition"].lower() for w in ("flu", "infection", "cold", "fever", "pneumonia", "dengue", "malaria", "typhoid", "covid")) else _key_for_title(c["condition"])
            if k:
                items.append({"key": k, "score": round(c["match"] * 0.8, 3), "why": f"Symptom pattern matches {c['condition']}"})
    if vitals_status == "critical":
        items.append({"key": "acute", "score": 0.9, "why": "Latest vitals are in the critical range"})
    merged: dict[str, dict] = {}
    for it in items:
        m = merged.setdefault(it["key"], {"key": it["key"], "score": 0.0, "why": []})
        m["score"] = max(m["score"], it["score"]); m["why"].append(it["why"])
    out = sorted(({**m, "why": "; ".join(m["why"])[:300]} for m in merged.values()), key=lambda x: -x["score"])[:3]
    return {"provider": "clinical_rules", "label": "Rule engine (labs, vitals, symptoms)", "available": True, "items": out}


LLM_SYSTEM = ("You are a clinical decision-support assistant helping a panel of doctors prepare a second opinion. You receive an anonymised case. "
              "Reply with ONLY JSON: {\"differential\":[{\"key\":<one of %s or \"other\">,\"name\":<string>,\"score\":<0..1>,\"why\":<short string>}]} with at most 3 entries ordered by likelihood. "
              "Never give a definitive diagnosis or treatment.") % list(CANON)


def parse_llm_json(text: str) -> list[dict]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise ValueError("no json")
    data = json.loads(m.group(0))
    out = []
    for d in data.get("differential", [])[:3]:
        k = d.get("key") if d.get("key") in CANON else "other:" + str(d.get("name", "unknown"))[:60]
        out.append({"key": k, "score": round(min(1.0, max(0.0, float(d.get("score", 0.5)))), 3), "why": str(d.get("why", ""))[:300]})
    return out


async def provider_llm(packet: dict) -> dict:
    base = {"provider": "llm", "label": "LLM differential (anonymised case)", "available": False, "items": []}
    key = os.getenv("LLM_API_KEY")
    if not key:
        return {**base, "reason": "LLM_API_KEY is not set"}
    try:
        import httpx
        async with httpx.AsyncClient(timeout=45) as c:
            r = await c.post("https://api.anthropic.com/v1/messages", headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                             json={"model": os.getenv("LLM_MODEL", "claude-sonnet-5-5"), "max_tokens": 600, "system": LLM_SYSTEM, "messages": [{"role": "user", "content": json.dumps(packet)[:6000]}]})
            r.raise_for_status()
            text = "".join(b.get("text", "") for b in r.json().get("content", []))
        return {**base, "available": True, "items": parse_llm_json(text)}
    except Exception as e:
        return {**base, "reason": f"LLM call failed: {type(e).__name__}"}


def name_of(key: str) -> str:
    return CANON[key][0] if key in CANON else key.split(":", 1)[-1]


def ensemble(providers: list[dict]) -> dict:
    live = [p for p in providers if p["available"]]  # a method that ran and found nothing still counts as having run
    n = len(live)
    keys = {i["key"] for p in live for i in p["items"]}
    rows = []
    for k in keys:
        sc = [next((i["score"] for i in p["items"] if i["key"] == k), 0.0) for p in live]
        votes = sum(1 for p in live if any(i["key"] == k for i in p["items"]))
        rows.append({"key": k, "condition": name_of(k), "consensus": round(sum(sc) / n, 3), "agreement": f"{votes}/{n}", "votes": votes,
                     "specialist": CANON.get(k, (None, SPEC_FALLBACK))[1],
                     "evidence": {p["provider"]: next((i["why"] for i in p["items"] if i["key"] == k), None) for p in live}})
    rows.sort(key=lambda r: (-r["votes"], -r["consensus"]))
    tops = {p["items"][0]["key"] for p in live if p["items"]}
    disagree = len(tops) >= 2 and len(tops) == sum(1 for p in live if p["items"])
    conf = "low" if n < 2 or disagree or not rows else "moderate" if rows[0]["votes"] < n else "higher"
    return {"methods_run": n, "methods_total": len(providers), "top": rows[:5], "methods_disagree_on_top": disagree, "confidence": conf,
            "note": ("Only %d of %d methods could run. " % (n, len(providers)) if n < len(providers) else "") + "Decision support only; a clinician must review."}


def report_hash(rep: dict) -> str:
    return hashlib.sha256(json.dumps(rep, sort_keys=True, default=str).encode()).hexdigest()


VERDICTS = {"agree", "modify", "disagree", "need_more_info"}


def build_report(case: dict) -> dict:
    ops = [p for p in case["panel"] if p["status"] == "submitted"]
    tally = {v: sum(1 for p in ops if p["opinion"]["verdict"] == v) for v in VERDICTS}
    top = max(tally.items(), key=lambda kv: kv[1])
    majority = top[0] if top[1] * 2 > len(ops) else "no_majority"
    tests: dict[str, int] = {}
    specs: dict[str, int] = {}
    for p in ops:
        for t in p["opinion"].get("recommended_tests", []):
            tests[t.strip().lower()] = tests.get(t.strip().lower(), 0) + 1
        s = (p["opinion"].get("recommended_specialist") or "").strip()
        if s:
            specs[s] = specs.get(s, 0) + 1
    ai_top = case["ensemble"]["top"][0]["condition"] if case["ensemble"]["top"] else "none identified"
    summary = (f"AI ensemble ({case['ensemble']['methods_run']}/{case['ensemble']['methods_total']} methods, confidence {case['ensemble']['confidence']}) ranked '{ai_top}' first. "
               f"{len(ops)} of {len(case['panel'])} panel doctors responded: {tally['agree']} agree, {tally['modify']} modify, {tally['disagree']} disagree, {tally['need_more_info']} need more information. "
               f"Panel verdict: {majority.replace('_', ' ')}.")
    dissent = [{"doctor": p["name"], "specialization": p["specialization"], "verdict": p["opinion"]["verdict"], "comments": p["opinion"].get("comments", "")} for p in ops if p["opinion"]["verdict"] != majority]
    rep = {"case_id": case["id"], "triggers": case["triggers"], "summary": summary, "ai_ensemble": case["ensemble"], "panel_verdict": majority, "vote_tally": tally,
           "doctor_opinions": [{"doctor": p["name"], "specialization": p["specialization"], **p["opinion"]} for p in ops],
           "recommended_tests": [t for t, _ in sorted(tests.items(), key=lambda kv: -kv[1])], "recommended_specialists": [s for s, _ in sorted(specs.items(), key=lambda kv: -kv[1])],
           "dissenting_views": dissent, "case_packet": case["packet"],
           "disclaimer": "Second-opinion report for clinical review. AI outputs come from demo-grade models and are not a diagnosis. Decisions rest with the treating clinician and the patient."}
    return rep
