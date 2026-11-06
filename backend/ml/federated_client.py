"""Run this INSIDE a hospital's network. Raw patient data (the CSV) never leaves this machine; only a weight update is uploaded.

  python ml/federated_client.py --api http://server:8000 --email hospital@x.in --password ... --disease diabetes --csv local_patients.csv

CSV columns: one per model feature (names are printed by --show-features) plus a `label` column (0/1).
Needs: numpy, scikit-learn, httpx.
"""
import argparse
import sys
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import federated as F  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True); ap.add_argument("--email", required=True); ap.add_argument("--password", required=True)
    ap.add_argument("--disease", required=True); ap.add_argument("--csv", required=True)
    ap.add_argument("--show-features", action="store_true")
    a = ap.parse_args()
    c = httpx.Client(base_url=a.api, timeout=30)
    r = c.post("/auth/login", json={"email": a.email, "password": a.password}); r.raise_for_status()
    c.headers["Authorization"] = f"Bearer {r.json()['token']}"
    g = c.get(f"/federated/global/{a.disease}"); g.raise_for_status(); g = g.json()
    if a.show_features:
        print(g["features"]); return
    if not g["round"]:
        sys.exit("No open round for this model. Ask the coordinator to start one.")
    import csv
    rows = list(csv.DictReader(open(a.csv)))
    X = np.array([[float(r[f]) for f in g["features"]] for r in rows]); y = np.array([float(r["label"]) for r in rows])
    X = (X - np.array(g["scaler"]["mean"])) / np.array(g["scaler"]["sd"])
    rng = np.random.default_rng(0); idx = rng.permutation(len(y)); k = int(0.8 * len(y))
    tr, te = idx[:k], idx[k:]
    w0, b0 = np.array(g["w"]), g["b"]
    prev = F.evaluate(w0, b0, X[te], y[te])
    rd = g["round"]
    w, b = F.local_train(w0, b0, X[tr], y[tr], epochs=rd["epochs"], lr=rd["lr"])
    d = F.clip_and_noise(np.append(w - w0, b - b0), rd["clip"], rd["noise_multiplier"], rng)
    out = c.post("/federated/update", json={"disease": a.disease, "round_id": rd["id"], "delta_w": d[:-1].tolist(), "delta_b": float(d[-1]), "n": int(len(tr)), "eval_prev": prev})
    print(out.status_code, out.json())


if __name__ == "__main__":
    main()
