"""Medical-image AI plug-in point.

No pretrained weights are shipped: a medical-imaging model must be trained/validated on proper data before it is
shown to patients. Put trained Keras models at  backend/models/<kind>.keras  (see ml/train_image_classifier.py) and
they are picked up automatically. Until then the API answers 503 with a clear message instead of faking a result.
"""
from __future__ import annotations

import io
import json
import os

MODELS_DIR = os.getenv("MODELS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "models"))

KINDS = {
    "chest-xray": {"title": "Chest X-ray (pneumonia / TB screening)", "labels": ["normal", "pneumonia", "tuberculosis"], "size": 224},
    "brain-mri": {"title": "Brain MRI (tumor screening)", "labels": ["no_tumor", "glioma", "meningioma", "pituitary"], "size": 224},
    "skin-lesion": {"title": "Skin lesion classification", "labels": ["benign", "malignant"], "size": 224},
    "retina": {"title": "Retinal image (diabetic retinopathy)", "labels": ["no_dr", "mild", "moderate", "severe", "proliferative"], "size": 224},
    "eye-cataract": {"title": "Cataract screening", "labels": ["normal", "cataract"], "size": 224},
    "bone-fracture": {"title": "Bone fracture detection", "labels": ["no_fracture", "fracture"], "size": 224},
}


class ModelUnavailable(Exception):
    pass


_cache: dict = {}


def _path(kind):
    return os.path.join(MODELS_DIR, f"{kind}.keras")


def status() -> list[dict]:
    return [{"kind": k, "title": v["title"], "labels": v["labels"], "loaded": os.path.exists(_path(k))} for k, v in KINDS.items()]


def analyze(kind: str, data: bytes) -> dict:
    spec = KINDS[kind]
    if not os.path.exists(_path(kind)):
        raise ModelUnavailable(f"No trained model installed for '{kind}'. Train one with ml/train_image_classifier.py and save it as models/{kind}.keras.")
    try:
        import numpy as np
        from PIL import Image
        img = Image.open(io.BytesIO(data)).convert("RGB").resize((spec["size"],) * 2)
    except Exception:
        raise ValueError("Could not read the image file")
    try:
        import tensorflow as tf
    except ImportError:
        raise ModelUnavailable("TensorFlow is not installed on the server (pip install tensorflow).")
    if kind not in _cache:
        _cache[kind] = tf.keras.models.load_model(_path(kind))
    x = np.asarray(img, dtype="float32")[None]
    probs = _cache[kind].predict(x, verbose=0)[0]
    labels = spec["labels"]
    if len(probs) != len(labels):
        raise ModelUnavailable("Model output size does not match the configured labels")
    order = sorted(range(len(labels)), key=lambda i: -probs[i])
    return {
        "kind": kind, "top_label": labels[order[0]], "confidence": float(probs[order[0]]),
        "scores": {labels[i]: round(float(probs[i]), 4) for i in order},
        "disclaimer": "AI screening support only - must be confirmed by a radiologist/doctor.",
    }
