"""Medical-image screening support.

HONESTY NOTE (also shown to users in every response):
* Without trained weights this module runs *classical computer-vision heuristics* (OpenCV) that highlight
  regions worth a clinician's attention: opacity patterns, left/right asymmetry, ABCD skin features, dark/bright
  retinal spots, lens haze. They are NOT diagnoses and are far less accurate than a trained CNN.
* If an ONNX model exists at ml/models/images/<task>.onnx (+ <task>.json with {"labels": [...]}) and onnxruntime is
  installed, that model is used instead and the response says mode="cnn". See ml/train_image_classifier.py to train one.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import cv2
import numpy as np

MODEL_DIR = Path(__file__).resolve().parents[2] / "ml" / "models" / "images"
HEURISTIC_TASKS = {"chest_xray", "brain_mri", "skin", "retina", "cataract", "segment"}
CNN_ONLY_TASKS = {"fracture", "tumor_classification", "pneumonia_classification"}
TASKS = sorted(HEURISTIC_TASKS | CNN_ONLY_TASKS)
MAX_PIXELS = 25_000_000
DISCLAIMER = ("Screening support only, not a diagnosis. Results must be reviewed by a qualified doctor/radiologist. "
              "Image quality, device and patient factors strongly affect results.")


class ImageError(ValueError):
    pass


def decode(data: bytes, max_side: int = 512) -> np.ndarray:
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ImageError("Could not read the image. Upload a PNG or JPEG.")
    h, w = img.shape[:2]
    if h * w > MAX_PIXELS:
        raise ImageError("Image is too large")
    if h < 64 or w < 64:
        raise ImageError("Image is too small to analyse (minimum 64x64)")
    s = max_side / max(h, w)
    return cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA) if s < 1 else img


def to_b64_png(img: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", img)
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode() if ok else ""


def _heat_overlay(base: np.ndarray, heat: np.ndarray, alpha: float = 0.45) -> np.ndarray:
    heat = cv2.normalize(heat.astype(np.float32), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    color = cv2.applyColorMap(heat, cv2.COLORMAP_JET)
    mask = (heat > 90)[..., None]
    return np.where(mask, cv2.addWeighted(base, 1 - alpha, color, alpha, 0), base)


def _level(score: float, lo: float, hi: float) -> str:
    return "high" if score >= hi else "moderate" if score >= lo else "low"


# --------------------------------------------------------------------------- heuristics
def chest_xray(img: np.ndarray) -> dict:
    g = cv2.createCLAHE(2.0, (8, 8)).apply(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    h, w = g.shape
    left, right = g[int(.2 * h):int(.8 * h), int(.12 * w):int(.45 * w)], g[int(.2 * h):int(.8 * h), int(.55 * w):int(.88 * w)]
    thr = np.percentile(g, 80)
    dl, dr = float((left > thr).mean()), float((right > thr).mean())
    lower = g[int(.5 * h):int(.8 * h), int(.12 * w):int(.88 * w)]
    lower_dense = float((lower > thr).mean())
    asym = abs(dl - dr) / max(dl + dr, 1e-6)
    score = float(np.clip(0.55 * asym * 2 + 0.45 * max(0.0, lower_dense - 0.2) * 2.5, 0, 1))
    heat = np.zeros_like(g, dtype=np.float32)
    heat[int(.2 * h):int(.8 * h), int(.12 * w):int(.88 * w)] = cv2.GaussianBlur(
        (g[int(.2 * h):int(.8 * h), int(.12 * w):int(.88 * w)] > np.percentile(g, 88)).astype(np.float32), (0, 0), 9)
    lvl = _level(score, 0.35, 0.6)
    finding = {"low": "No marked asymmetric or lower-zone opacity pattern found by the heuristic.",
               "moderate": "Some increased opacity or left/right asymmetry. Could reflect infection, fluid or positioning; needs radiologist review.",
               "high": "Marked asymmetric/lower-zone opacity pattern. Please get a radiologist review soon, especially with cough, fever or breathlessness."}[lvl]
    return {"score": round(score, 2), "level": lvl, "finding": finding, "metrics": {"left_density": round(dl, 3), "right_density": round(dr, 3),
            "asymmetry": round(asym, 3), "lower_zone_density": round(lower_dense, 3)}, "overlay": _heat_overlay(img, heat)}


def brain_mri(img: np.ndarray) -> dict:
    g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    _, brain = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    brain = cv2.morphologyEx(brain, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    area_brain = max(int((brain > 0).sum()), 1)
    ys, xs = np.where(brain > 0)
    cx = int(xs.mean()) if len(xs) else g.shape[1] // 2
    w = g.shape[1]
    # mirror about the brain's own midline
    shift = w // 2 - cx
    M = np.float32([[1, 0, shift], [0, 1, 0]])
    centered = cv2.warpAffine(g, M, (w, g.shape[0]))
    diff = cv2.absdiff(centered, cv2.flip(centered, 1)).astype(np.float32)
    diff = cv2.GaussianBlur(diff, (0, 0), 5)
    mask_c = cv2.warpAffine(brain, M, (w, g.shape[0])) > 0
    diff[~mask_c] = 0
    thr = max(25.0, float(np.percentile(diff[mask_c], 97))) if mask_c.any() else 25.0
    cand = ((diff > thr) & mask_c).astype(np.uint8) * 255
    cand = cv2.morphologyEx(cand, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    cnts, _ = cv2.findContours(cand, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = cv2.warpAffine(img, M, (w, g.shape[0]))
    regions = []
    for c in sorted(cnts, key=cv2.contourArea, reverse=True)[:3]:
        a = cv2.contourArea(c)
        if a / area_brain > 0.004:
            x, y, bw, bh = cv2.boundingRect(c)
            regions.append({"bbox": [int(x), int(y), int(bw), int(bh)], "area_pct_of_brain": round(100 * a / area_brain, 2)})
            cv2.rectangle(out, (x, y), (x + bw, y + bh), (0, 0, 255), 2)
    asym = float(diff[mask_c].mean() / 255) if mask_c.any() else 0.0
    score = float(np.clip(asym * 6 + (0.25 if regions else 0), 0, 1))
    lvl = _level(score, 0.3, 0.55)
    finding = {"low": "No prominent asymmetric region found by the heuristic.",
               "moderate": "Mild left/right asymmetry; may be normal anatomy, tilt or artefact. Radiologist review advised if symptoms exist.",
               "high": "Prominent asymmetric region(s) highlighted. This does NOT identify a tumour; consult a neurologist/radiologist."}[lvl]
    return {"score": round(score, 2), "level": lvl, "finding": finding, "regions": regions,
            "metrics": {"mean_asymmetry": round(asym, 3)}, "overlay": out}


def skin(img: np.ndarray) -> dict:
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (7, 7), 0)
    _, m = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    m = cv2.morphologyEx(cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = [c for c in cnts if cv2.contourArea(c) > 0.003 * m.size]
    if not cnts:
        return {"score": 0.0, "level": "low", "finding": "No distinct lesion could be segmented. Retake the photo closer, in even light, on plain skin.",
                "metrics": {}, "overlay": img}
    c = max(cnts, key=cv2.contourArea)
    area, per = cv2.contourArea(c), cv2.arcLength(c, True)
    lesion = np.zeros_like(m)
    cv2.drawContours(lesion, [c], -1, 255, -1)
    x, y, bw, bh = cv2.boundingRect(c)
    crop = lesion[y:y + bh, x:x + bw]
    asym = float(1 - np.logical_and(crop > 0, cv2.flip(crop, 1) > 0).sum() / max((crop > 0).sum(), 1))  # A
    asym2 = float(1 - np.logical_and(crop > 0, cv2.flip(crop, 0) > 0).sum() / max((crop > 0).sum(), 1))
    A = (asym + asym2) / 2
    B = float(np.clip(per ** 2 / (4 * np.pi * area) - 1, 0, 2) / 2)  # compactness; 0 = circle
    px = hsv[lesion > 0].astype(np.float32)
    k = 3
    _, labels, centers = cv2.kmeans(px[:, :3], k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 15, 1.0), 2, cv2.KMEANS_PP_CENTERS)
    spread = float(np.mean([np.linalg.norm(centers[i] - centers[j]) for i in range(k) for j in range(i + 1, k)]))
    C = float(np.clip(spread / 120, 0, 1))
    D = float(np.clip(max(bw, bh) / img.shape[1] / 0.5, 0, 1))
    score = float(np.clip(0.3 * A + 0.3 * B + 0.3 * C + 0.1 * D, 0, 1))
    lvl = _level(score, 0.3, 0.5)
    finding = {"low": "Lesion looks fairly symmetric, regular and uniform in colour. Keep monitoring for change.",
               "moderate": "Some irregular features (asymmetry/border/colour). A dermatologist check is advisable.",
               "high": "Several concerning ABCD-style features. Please see a dermatologist soon; this is not a cancer diagnosis."}[lvl]
    out = img.copy()
    cv2.drawContours(out, [c], -1, (0, 0, 255), 2)
    return {"score": round(score, 2), "level": lvl, "finding": finding,
            "metrics": {"asymmetry": round(A, 2), "border_irregularity": round(B, 2), "colour_variation": round(C, 2),
                        "relative_size": round(D, 2), "evolution": "needs follow-up photos over time"}, "overlay": out}


def retina(img: np.ndarray) -> dict:
    green = cv2.createCLAHE(2.0, (8, 8)).apply(img[:, :, 1])
    h, w = green.shape
    yy, xx = np.ogrid[:h, :w]
    fov = ((yy - h / 2) ** 2 + (xx - w / 2) ** 2) < (0.46 * min(h, w)) ** 2
    dark = cv2.morphologyEx(green, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    bright = cv2.morphologyEx(green, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21)))
    dmask = ((dark > np.percentile(dark[fov], 98.5)) & fov).astype(np.uint8)
    bmask = ((bright > np.percentile(bright[fov], 99.2)) & fov).astype(np.uint8)
    nd = max(cv2.connectedComponents(dmask)[0] - 1, 0)
    nb = max(cv2.connectedComponents(bmask)[0] - 1, 0)
    score = float(np.clip((nd / 120) * 0.6 + (nb / 80) * 0.4, 0, 1))
    lvl = _level(score, 0.35, 0.65)
    out = img.copy()
    out[dmask > 0] = (0, 0, 255)
    out[bmask > 0] = (0, 255, 255)
    finding = {"low": "Few isolated dark/bright spots; no clear lesion pattern from the heuristic.",
               "moderate": "Several dark and/or bright spots (possible microaneurysm/haemorrhage/exudate-like). Dilated eye exam advised, especially with diabetes.",
               "high": "Many spot-like lesions. Please see an ophthalmologist soon for a diabetic retinopathy check."}[lvl]
    return {"score": round(score, 2), "level": lvl, "finding": finding,
            "metrics": {"dark_spot_candidates": nd, "bright_spot_candidates": nb, "legend": "red=dark spots, yellow=bright spots"}, "overlay": out}


def cataract(img: np.ndarray) -> dict:
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    sharp = float(cv2.Laplacian(g, cv2.CV_64F).var())
    contrast = float(g.std())
    h, w = g.shape
    centre = g[int(.3 * h):int(.7 * h), int(.3 * w):int(.7 * w)]
    haze = float(np.clip(1 - (centre.std() / 60), 0, 1))
    score = float(np.clip(0.5 * haze + 0.5 * np.clip(1 - sharp / 400, 0, 1), 0, 1))
    lvl = _level(score, 0.4, 0.65)
    finding = {"low": "Pupil/lens area looks clear in this photo.",
               "moderate": "Some haze or blur in the pupil area. Could be a focus issue or early lens clouding. An eye exam is advised.",
               "high": "Marked haze/blur. If your vision is cloudy, glary or dim, see an ophthalmologist."}[lvl]
    return {"score": round(score, 2), "level": lvl, "finding": finding,
            "metrics": {"sharpness": round(sharp, 1), "contrast": round(contrast, 1), "centre_haze": round(haze, 2)}, "overlay": img}


def segment(img: np.ndarray) -> dict:
    g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    _, m = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = img.copy()
    cv2.drawContours(out, cnts, -1, (0, 255, 0), 2)
    cover = float((m > 0).mean())
    return {"score": round(cover, 2), "level": "info", "finding": f"Segmented {len(cnts)} region(s) covering {cover:.0%} of the image (Otsu threshold).",
            "metrics": {"regions": len(cnts), "coverage": round(cover, 3)}, "overlay": out}


HEURISTICS = {"chest_xray": chest_xray, "brain_mri": brain_mri, "skin": skin, "retina": retina, "cataract": cataract, "segment": segment}


# --------------------------------------------------------------------------- optional CNN (ONNX)
def _cnn(img: np.ndarray, task: str) -> dict | None:
    mp, lp = MODEL_DIR / f"{task}.onnx", MODEL_DIR / f"{task}.json"
    if not (mp.exists() and lp.exists()):
        return None
    try:
        import onnxruntime as ort
    except ImportError:
        return None
    labels = json.loads(lp.read_text())["labels"]
    x = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), (224, 224)).astype(np.float32) / 255.0
    x = ((x - np.array([0.485, 0.456, 0.406])) / np.array([0.229, 0.224, 0.225])).astype(np.float32).transpose(2, 0, 1)[None]
    sess = ort.InferenceSession(str(mp), providers=["CPUExecutionProvider"])
    logits = sess.run(None, {sess.get_inputs()[0].name: x})[0][0]
    e = np.exp(logits - logits.max())
    p = e / e.sum()
    top = int(p.argmax())
    probs = {labels[i]: round(float(p[i]), 3) for i in range(len(labels))}
    return {"label": labels[top], "confidence": round(float(p[top]), 3), "probabilities": probs}


def analyze(data: bytes, task: str) -> dict:
    if task not in TASKS:
        raise ImageError(f"Unknown task. Choose one of: {', '.join(TASKS)}")
    img = decode(data)
    cnn_task = task if task in CNN_ONLY_TASKS else task
    cnn = _cnn(img, cnn_task)
    if cnn:
        res = {"mode": "cnn", **cnn, "finding": f"Model output: {cnn['label']} ({cnn['confidence']:.0%} confidence).", "level": "info"}
        overlay = img
    elif task in CNN_ONLY_TASKS:
        return {"task": task, "mode": "unavailable", "available": False, "disclaimer": DISCLAIMER,
                "message": f"'{task}' needs a trained model. Train one with ml/train_image_classifier.py and place {task}.onnx + {task}.json in ml/models/images/."}
    else:
        r = HEURISTICS[task](img)
        overlay = r.pop("overlay")
        res = {"mode": "heuristic-demo", **r}
    res.update({"task": task, "overlay_png": to_b64_png(overlay), "disclaimer": DISCLAIMER,
                "report": generate_report(task, res)})
    return res


def generate_report(task: str, res: dict) -> str:
    names = {"chest_xray": "Chest X-ray", "brain_mri": "Brain MRI", "skin": "Skin lesion photo", "retina": "Retinal photo",
             "cataract": "Eye (lens) photo", "segment": "Image segmentation", "fracture": "Bone X-ray",
             "tumor_classification": "Brain MRI classification", "pneumonia_classification": "Chest X-ray classification"}
    lines = [f"AUTOMATED IMAGE SCREENING SUMMARY: {names.get(task, task)}", f"Method: {res.get('mode')}",
             f"Finding: {res.get('finding')}"]
    if "metrics" in res and res["metrics"]:
        lines.append("Measurements: " + "; ".join(f"{k}={v}" for k, v in res["metrics"].items()))
    if res.get("regions"):
        lines.append("Highlighted regions: " + "; ".join(f"bbox {r['bbox']} ({r['area_pct_of_brain']}% of brain area)" for r in res["regions"]))
    lines.append("Recommendation: share this image and summary with a qualified doctor. " + DISCLAIMER)
    return "\n".join(lines)
