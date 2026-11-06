"""Prescription OCR + parsing: image -> text -> medicines, strength, timings, duration (always a DRAFT for human verification).

Printed prescriptions work reasonably; handwriting is read poorly by Tesseract, so every item carries a confidence and
review flags, and nothing becomes a reminder until a doctor or pharmacist has verified it.
"""
from __future__ import annotations

import difflib
import io
import re

from . import drugs

FORMS = r"(?:tab(?:let)?s?|cap(?:sule)?s?|syp|syrup|inj(?:ection)?|drops?|oint(?:ment)?|cream|gel|susp(?:ension)?)"
STRENGTH = re.compile(r"(\d+(?:\.\d+)?)\s?(mg|mcg|µg|g|ml|iu)\b", re.I)
PATTERN3 = re.compile(r"(?<![\d.])([0-3½])\s*[-–]\s*([0-3½])\s*[-–]\s*([0-3½])(?:\s*[-–]\s*([0-3½]))?(?![\d.])")
DURATION = re.compile(r"(?:x|×|for|\bfor\s+next)\s*(\d{1,3})\s*(days?|d|weeks?|wks?|months?)\b|\b(\d{1,3})\s*(days?|weeks?|months?)\b", re.I)
SLOTS4 = ["08:00", "13:00", "18:00", "22:00"]
SLOTS3 = ["08:00", "14:00", "21:00"]
FREQ_WORDS = [
    (r"\b(qid|q\.?i\.?d\.?|four times)\b", ["07:00", "12:00", "17:00", "22:00"], "4 times a day"),
    (r"\b(tds|t\.?d\.?s\.?|tid|t\.?i\.?d\.?|thrice|three times)\b", SLOTS3, "3 times a day"),
    (r"\b(bd|b\.?d\.?|bid|b\.?i\.?d\.?|twice|two times)\b", ["08:00", "20:00"], "twice a day"),
    (r"\b(hs|h\.?s\.?|at night|bedtime|nocte)\b", ["22:00"], "at bedtime"),
    (r"\b(od|o\.?d\.?|qd|once|daily|every day)\b", ["08:00"], "once a day"),
]
FOOD = [(r"\b(before (?:food|meals?)|ac|empty stomach)\b", "before food"), (r"\b(after (?:food|meals?)|pc|post meal)\b", "after food"), (r"\b(with (?:food|milk))\b", "with food")]
SKIP_WORDS = {"tablet", "tablets", "capsule", "capsules", "syrup", "daily", "night", "morning", "before", "after", "food", "meals", "days", "weeks", "once", "twice", "thrice",
              "doctor", "patient", "name", "age", "date", "address", "hospital", "clinic", "signature", "diagnosis", "advice", "follow", "review", "refill", "with", "water", "empty"}
_NAMES = None


def _names() -> dict[str, str]:
    global _NAMES
    if _NAMES is None:
        _NAMES = {}
        for n, d in drugs.DRUGS.items():
            _NAMES[n.lower()] = n
            for b in d.get("brands", []):
                _NAMES[b.lower()] = n
                first = b.lower().split()[0]
                if len(first) >= 4:
                    _NAMES.setdefault(first, n)
    return _NAMES


def preprocess_ocr(data: bytes) -> str:
    """Grayscale, upscale, denoise and binarise before Tesseract; falls back to the raw image if OpenCV is missing."""
    import pytesseract
    from PIL import Image
    try:
        import cv2
        import numpy as np
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError("not an image")
        if max(img.shape) < 1600:
            s = 1600 / max(img.shape)
            img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
        img = cv2.fastNlMeansDenoising(img, None, 12, 7, 21)
        img = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)
        pil = Image.fromarray(img)
    except ImportError:
        pil = Image.open(io.BytesIO(data))
    return pytesseract.image_to_string(pil, config="--psm 6")


def _times_from_pattern(g: tuple) -> tuple[list[str], str]:
    vals = [1 if x == "½" else int(x) if x else 0 for x in g]
    if len(g) == 4 and g[3] is not None:
        t = [SLOTS4[i] for i, v in enumerate(vals) if v]
    else:
        t = [SLOTS3[i] for i, v in enumerate(vals[:3]) if v]
    return t or ["08:00"], "-".join(str(x) for x in g if x is not None)


def _duration_days(text: str) -> int | None:
    m = DURATION.search(text)
    if not m:
        return None
    n = int(m.group(1) or m.group(3))
    unit = (m.group(2) or m.group(4)).lower()
    d = n * (30 if unit.startswith("month") else 7 if unit.startswith(("week", "wk")) else 1)
    return d if 1 <= d <= 730 else None


def _match_name(line: str) -> tuple[str | None, str | None, float, bool]:
    """-> (display name, canonical, confidence, in_database)."""
    low = line.lower()
    names = _names()
    for key in sorted(names, key=len, reverse=True):
        if re.search(rf"\b{re.escape(key)}\b", low):
            return key.title() if key != names[key] else names[key].title(), names[key], 0.92, True
    cand = re.match(rf"\s*(?:\d+[.)]\s*)?{FORMS}\.?\s+([A-Za-z][A-Za-z0-9\-]{{2,24}})", line, re.I)
    words = [cand.group(1)] if cand else [w for w in re.findall(r"[A-Za-z]{5,}", line) if w.lower() not in SKIP_WORDS]
    for w in words:
        close = difflib.get_close_matches(w.lower(), list(names), n=1, cutoff=0.82)
        if close:
            return close[0].title(), names[close[0]], round(0.5 + 0.4 * difflib.SequenceMatcher(None, w.lower(), close[0]).ratio(), 2), True
    if cand:
        return cand.group(1).title(), None, 0.4, False
    return None, None, 0, False


def parse(text: str) -> list[dict]:
    items: list[dict] = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for i, line in enumerate(lines):
        name, canon, conf, known = _match_name(line)
        if not name:
            continue
        ctx = " ".join([line] + lines[i + 1:i + 2]) if not (STRENGTH.search(line) and (PATTERN3.search(line) or any(re.search(p, line, re.I) for p, *_ in FREQ_WORDS))) else line
        low = ctx.lower()
        flags = []
        sm = STRENGTH.search(ctx)
        dose = f"{sm.group(1)} {sm.group(2).lower()}" if sm else ""
        times, freq = None, ""
        pm = PATTERN3.search(ctx)
        if pm:
            times, freq = _times_from_pattern(pm.groups())
        else:
            for pat, t, label in FREQ_WORDS:
                if re.search(pat, low):
                    times, freq = t, label
                    break
        if re.search(r"\b(sos|prn|as needed|when required|if needed)\b", low):
            flags.append("as-needed medicine: choose reminder times manually")
            times = times or ["08:00"]
            freq = freq or "as needed"
        if not times:
            times, freq = ["08:00"], ""
            flags.append("frequency not found, defaulted to once a day")
        if not dose:
            flags.append("strength not found")
        days = _duration_days(ctx)
        if days is None:
            days = 5
            flags.append("duration not found, defaulted to 5 days")
        food = next((lab for pat, lab in FOOD if re.search(pat, low)), "")
        if not known:
            flags.append("name not in the medicine database: check spelling")
        if conf < 0.8:
            flags.append("low OCR confidence")
        if any(it["name"].lower() == name.lower() and it["dose"] == dose for it in items):
            continue
        items.append({"name": name, "canonical": canon, "dose": dose, "times": times, "duration_days": days,
                      "instructions": ", ".join(x for x in (freq, food) if x), "confidence": conf, "in_database": known, "review_flags": flags})
    return items
