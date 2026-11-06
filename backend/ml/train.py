"""Train / retrain the risk models.

    python ml/train.py                 # synthetic data (demo)
    python ml/train.py --real          # use CSVs in ml/data/

Real-data mode expects  ml/data/diabetes.csv  and  ml/data/heart.csv  with the
feature columns named exactly as in app/services/ml.py SPECS plus a binary
`target` column (e.g. map the Pima Indians Diabetes or UCI Heart datasets onto
those names). Models are written to ml/models/*.joblib and picked up on restart.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import ml  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"


def load_real(name):
    import csv

    with open(DATA / f"{name}.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    feats = list(ml.SPECS[name])
    X = np.array([[float(r[c]) for c in feats] for r in rows])
    y = np.array([int(float(r["target"])) for r in rows])
    return X, y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", action="store_true")
    args = ap.parse_args()
    for name in ml.SPECS:
        X, y = load_real(name) if args.real else ml.make_synthetic(name)
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=0, stratify=y)
        model = ml.train(name, Xtr, ytr)
        auc = roc_auc_score(yte, model.predict_proba(Xte)[:, 1])
        print(f"{name:9s} rows={len(y):6d}  positives={y.mean():.1%}  hold-out AUC={auc:.3f}"
              + ("" if args.real else "   (synthetic data - plumbing check only)"))
        if not args.real:
            ml.train(name)  # final model on the full synthetic set


if __name__ == "__main__":
    main()
