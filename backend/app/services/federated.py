"""Federated learning (FedAvg) for the demo risk models. Pure numpy.

What is real here
* Each hospital trains on its OWN data and uploads only a weight update (delta) + sample count + local validation numbers.
* The coordinator averages updates weighted by sample count (FedAvg, McMahan et al. 2017).
* Optional per-update L2 clipping and Gaussian noise (the building blocks of differentially-private FL).

What is NOT claimed
* No formal privacy guarantee: the noise multiplier is not tied to an (epsilon, delta) accountant, and the coordinator sees each
  hospital's individual update (no secure aggregation). Model updates can still leak information (gradient inversion, membership inference).
* The shipped models are logistic regressions on the synthetic-data demo feature set, not clinical models.
"""
from __future__ import annotations

import math

import numpy as np

from . import ml


def spec_scaler(disease: str):
    f = ml.SPECS[disease]["features"]
    names = list(f)
    mu = np.array([f[k][4] for k in names], dtype=float)
    sd = np.array([f[k][5] for k in names], dtype=float)
    return names, mu, sd


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def local_train(w, b, X, y, epochs=5, lr=0.1, l2=1e-3, batch=64, seed=0):
    """Mini-batch gradient descent on logistic loss starting from the global weights. X must already be standardized."""
    rng = np.random.default_rng(seed)
    w = np.array(w, dtype=float).copy(); b = float(b)
    n = len(y)
    for _ in range(epochs):
        idx = rng.permutation(n)
        for s in range(0, n, batch):
            j = idx[s:s + batch]
            p = sigmoid(X[j] @ w + b)
            g = p - y[j]
            w -= lr * (X[j].T @ g / len(j) + l2 * w)
            b -= lr * float(g.mean())
    return w, b


def evaluate(w, b, X, y) -> dict:
    from sklearn.metrics import roc_auc_score
    p = sigmoid(X @ np.array(w) + b)
    eps = 1e-9
    loss = float(-np.mean(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps)))
    auc = float(roc_auc_score(y, p)) if 0 < y.sum() < len(y) else None
    return {"n": int(len(y)), "loss": round(loss, 4), "auc": None if auc is None else round(auc, 4)}


def clip_and_noise(delta: np.ndarray, clip: float | None, sigma: float, rng) -> np.ndarray:
    d = np.array(delta, dtype=float)
    if clip:
        n = float(np.linalg.norm(d))
        if n > clip:
            d = d * (clip / n)
    if sigma and clip:
        d = d + rng.normal(0, sigma * clip, size=d.shape)
    return d


def fedavg(global_w, global_b, updates: list[dict]):
    """updates: [{delta_w, delta_b, n}] -> new (w, b). Weighted by sample count."""
    tot = sum(u["n"] for u in updates)
    if tot <= 0:
        raise ValueError("no samples")
    dw = sum(np.array(u["delta_w"], dtype=float) * u["n"] for u in updates) / tot
    db = sum(float(u["delta_b"]) * u["n"] for u in updates) / tot
    return np.array(global_w, dtype=float) + dw, float(global_b) + db


def validate_update(u: dict, dim: int, max_norm: float) -> str | None:
    try:
        dw = np.array(u["delta_w"], dtype=float)
        db = float(u["delta_b"]); n = int(u["n"])
    except Exception:
        return "Malformed update"
    if dw.shape != (dim,):
        return f"delta_w must have {dim} numbers"
    if not (np.isfinite(dw).all() and math.isfinite(db)):
        return "Update contains non-finite numbers"
    if not (1 <= n <= 10_000_000):
        return "n must be between 1 and 10,000,000"
    if float(np.linalg.norm(np.append(dw, db))) > max_norm:
        return f"Update norm exceeds the allowed maximum ({max_norm})"
    return None


def make_hospital_data(disease: str, hospital: int, n: int, seed: int = 0, shift: float = 0.6):
    """Synthetic non-IID cohort: each hospital's population is shifted differently (e.g. older / higher-BMI)."""
    names, mu, sd = spec_scaler(disease)
    spec = ml.SPECS[disease]
    rng = np.random.default_rng(1000 * (hospital + 1) + seed)
    cols, logit = [], np.full(n, spec["intercept"], dtype=float)
    offs = rng.normal(0, shift, len(names))
    for i, k in enumerate(names):
        lab, lo, hi, dflt, m, s, wt, kind = spec["features"][k]
        if kind == "bin":
            x = rng.binomial(1, float(np.clip(m + 0.15 * offs[i], 0.02, 0.98)), n).astype(float)
        else:
            x = np.clip(rng.normal(m + offs[i] * s, s, n), lo, hi)
        logit += wt * (x - m) / s
        cols.append(x)
    y = rng.binomial(1, sigmoid(logit)).astype(float)
    X = (np.column_stack(cols) - mu) / sd
    return X, y


def simulate(disease: str = "diabetes", hospitals: int = 4, rounds: int = 12, n_per: int = 600, epochs: int = 3, clip: float | None = None, sigma: float = 0.0, seed: int = 1) -> dict:
    """Compare: each hospital alone (local-only), federated averaging, and centralised pooling (upper bound that needs all raw data in one place)."""
    names, _, _ = spec_scaler(disease)
    dim = len(names)
    data = [make_hospital_data(disease, h, n_per, seed) for h in range(hospitals)]
    splits = []
    for X, y in data:
        k = int(len(y) * 0.8)
        splits.append((X[:k], y[:k], X[k:], y[k:]))
    Xte = np.vstack([s[2] for s in splits]); yte = np.concatenate([s[3] for s in splits])
    rng = np.random.default_rng(seed)
    w, b = np.zeros(dim), 0.0
    curve = []
    for r in range(1, rounds + 1):
        ups = []
        for h, (Xtr, ytr, _, _) in enumerate(splits):
            lw, lb = local_train(w, b, Xtr, ytr, epochs=epochs, seed=seed * 100 + r * 10 + h)
            d = clip_and_noise(np.append(lw - w, lb - b), clip, sigma, rng)
            ups.append({"delta_w": d[:-1], "delta_b": d[-1], "n": len(ytr)})
        w, b = fedavg(w, b, ups)
        m = evaluate(w, b, Xte, yte)
        curve.append({"round": r, "auc": m["auc"], "loss": m["loss"]})
    fed = evaluate(w, b, Xte, yte)
    local = []
    for h, (Xtr, ytr, _, _) in enumerate(splits):
        lw, lb = local_train(np.zeros(dim), 0.0, Xtr, ytr, epochs=epochs * rounds, seed=seed + h)
        local.append({"hospital": f"Hospital {h + 1}", **evaluate(lw, lb, Xte, yte)})
    Xall = np.vstack([s[0] for s in splits]); yall = np.concatenate([s[1] for s in splits])
    cw, cb = local_train(np.zeros(dim), 0.0, Xall, yall, epochs=epochs * rounds, seed=seed)
    cen = evaluate(cw, cb, Xte, yte)
    return {"disease": disease, "hospitals": hospitals, "rounds": rounds, "clip": clip, "noise_multiplier": sigma, "curve": curve, "federated": fed, "local_only": local,
            "centralised": cen, "note": "Synthetic non-IID data. Centralised pooling is the upper bound but requires moving all raw data to one place."}
