import numpy as np

from app.services import board as B
from app.services import federated as F


def test_fedavg_weights_by_sample_count():
    w, b = F.fedavg([0.0, 0.0], 0.0, [{"delta_w": [1, 1], "delta_b": 1, "n": 1}, {"delta_w": [3, 3], "delta_b": 3, "n": 3}])
    assert np.allclose(w, [2.5, 2.5]) and abs(b - 2.5) < 1e-9


def test_federated_update_validation():
    assert F.validate_update({"delta_w": [0, 0], "delta_b": 0, "n": 5}, 2, 10) is None
    assert F.validate_update({"delta_w": [0], "delta_b": 0, "n": 5}, 2, 10)
    assert F.validate_update({"delta_w": [float("nan"), 0], "delta_b": 0, "n": 5}, 2, 10)
    assert F.validate_update({"delta_w": [100, 0], "delta_b": 0, "n": 5}, 2, 10)


def test_federated_learns():
    r = F.simulate("diabetes", 3, 6)
    assert r["federated"]["auc"] > 0.75 and r["curve"][-1]["auc"] >= r["curve"][0]["auc"] - 0.02


def test_ensemble_flags_disagreement_and_missing_method():
    a = {"provider": "a", "available": True, "items": [{"key": "diabetes", "score": .8, "why": ""}]}
    b = {"provider": "b", "available": True, "items": [{"key": "heart", "score": .7, "why": ""}]}
    c = {"provider": "c", "available": False, "items": []}
    e = B.ensemble([a, b, c])
    assert e["methods_run"] == 2 and e["methods_total"] == 3 and e["methods_disagree_on_top"] and e["confidence"] == "low"


def test_triggers():
    assert B.triggers([{"disease": "a", "level": "high"}, {"disease": "b", "level": "high"}], [], [])
    assert B.triggers([], [], ["Myasthenia gravis"])
    assert B.triggers([{"disease": "a", "level": "low"}], [], ["asthma"]) == []
