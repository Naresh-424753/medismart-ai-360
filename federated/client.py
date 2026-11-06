#!/usr/bin/env python3
"""MediSmart federated-learning client for ONE hospital. Runs on the hospital's own machine.

Raw patient data stays in your CSV; only a weight update (plus sample count and holdout metrics) is sent to the coordinator.

CSV columns must be the model's feature names (see `GET /federated/global/<disease>` -> features) plus a `label` column (0/1).
Usage:
  pip install numpy scikit-learn requests
  python client.py --api http://localhost:8000 --token <hospital JWT> --disease diabetes --csv my_patients.csv
"""
import argparse, sys
import numpy as np
import requests


def sigmoid(z): return 1 / (1 + np.exp(-np.clip(z, -30, 30)))


def train(w, b, X, y, epochs, lr, l2=1e-3, batch=64, seed=0):
    rng = np.random.default_rng(seed); w = w.copy()
    for _ in range(epochs):
        idx = rng.permutation(len(y))
        for s in range(0, len(y), batch):
            j = idx[s:s + batch]; g = sigmoid(X[j] @ w + b) - y[j]
            w -= lr * (X[j].T @ g / len(j) + l2 * w); b -= lr * g.mean()
    return w, float(b)


def metrics(w, b, X, y):
    from sklearn.metrics import roc_auc_score
    p = sigmoid(X @ w + b)
    return {"n": int(len(y)), "loss": float(-np.mean(y * np.log(p + 1e-9) + (1 - y) * np.log(1 - p + 1e-9))), "auc": float(roc_auc_score(y, p)) if 0 < y.sum() < len(y) else None}


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--api", required=True); a.add_argument("--token", required=True); a.add_argument("--disease", required=True); a.add_argument("--csv", required=True)
    a = a.parse_args()
    H = {"Authorization": f"Bearer {a.token}"}
    g = requests.get(f"{a.api}/federated/global/{a.disease}", headers=H, timeout=30); g.raise_for_status(); g = g.json()
    if not g["round"]:
        sys.exit("No open round for this model. Ask the administrator to start one.")
    import csv
    rows = list(csv.DictReader(open(a.csv)))
    X = np.array([[float(r[f]) for f in g["features"]] for r in rows]); y = np.array([float(r["label"]) for r in rows])
    X = (X - np.array(g["scaler"]["mean"])) / np.array(g["scaler"]["sd"])
    k = int(len(y) * 0.8); rng = np.random.default_rng(0); idx = rng.permutation(len(y)); tr, te = idx[:k], idx[k:]
    w0, b0 = np.array(g["w"]), g["b"]
    prev = metrics(w0, b0, X[te], y[te]) if len(te) > 10 else None  # how good is the CURRENT global model on my held-out data
    w1, b1 = train(w0, b0, X[tr], y[tr], g["round"]["epochs"], g["round"]["lr"])
    d = np.append(w1 - w0, b1 - b0)
    clip, sigma = g["round"]["clip"], g["round"]["noise_multiplier"]
    if clip and np.linalg.norm(d) > clip: d = d * clip / np.linalg.norm(d)
    if clip and sigma: d = d + np.random.default_rng().normal(0, sigma * clip, d.shape)
    r = requests.post(f"{a.api}/federated/update", headers=H, timeout=60, json={"disease": a.disease, "round_id": g["round"]["id"], "delta_w": d[:-1].tolist(), "delta_b": float(d[-1]), "n": int(len(tr)), "eval_prev": prev})
    print(r.status_code, r.json())


if __name__ == "__main__":
    main()
