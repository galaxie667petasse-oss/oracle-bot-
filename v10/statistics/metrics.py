from __future__ import annotations

import math
from typing import Iterable


EPS = 1e-12


def clip_probability(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("probability is not finite")
    return min(max(float(value), EPS), 1.0 - EPS)


def multiclass_log_loss(probabilities: list[dict[str, float]], labels: list[str]) -> float:
    if len(probabilities) != len(labels):
        raise ValueError("probabilities and labels length mismatch")
    if not labels:
        return float("nan")
    return -sum(math.log(clip_probability(prob[label])) for prob, label in zip(probabilities, labels)) / len(labels)


def multiclass_brier(probabilities: list[dict[str, float]], labels: list[str], classes: tuple[str, ...] = ("home", "draw", "away")) -> float:
    if len(probabilities) != len(labels):
        raise ValueError("probabilities and labels length mismatch")
    if not labels:
        return float("nan")
    total = 0.0
    for prob, label in zip(probabilities, labels):
        total += sum((prob.get(cls, 0.0) - (1.0 if label == cls else 0.0)) ** 2 for cls in classes)
    return total / len(labels)


def binary_log_loss(probabilities: Iterable[float], labels: Iterable[int]) -> float:
    rows = list(zip(probabilities, labels))
    if not rows:
        return float("nan")
    return -sum(label * math.log(clip_probability(p)) + (1 - label) * math.log(clip_probability(1.0 - p)) for p, label in rows) / len(rows)


def binary_brier(probabilities: Iterable[float], labels: Iterable[int]) -> float:
    rows = list(zip(probabilities, labels))
    if not rows:
        return float("nan")
    return sum((float(p) - int(label)) ** 2 for p, label in rows) / len(rows)


def expected_calibration_error(probabilities: list[float], labels: list[int], bins: int = 10) -> dict:
    if len(probabilities) != len(labels):
        raise ValueError("probabilities and labels length mismatch")
    if not probabilities:
        return {"ece": float("nan"), "mce": float("nan"), "bins": []}
    bucket_rows = []
    ece = 0.0
    mce = 0.0
    for idx in range(bins):
        low = idx / bins
        high = (idx + 1) / bins
        selected = [(p, y) for p, y in zip(probabilities, labels) if (low <= p < high) or (idx == bins - 1 and p == 1.0)]
        if not selected:
            continue
        conf = sum(p for p, _ in selected) / len(selected)
        acc = sum(y for _, y in selected) / len(selected)
        gap = abs(conf - acc)
        ece += len(selected) / len(probabilities) * gap
        mce = max(mce, gap)
        bucket_rows.append({"low": low, "high": high, "count": len(selected), "confidence": conf, "accuracy": acc, "gap": gap})
    return {"ece": ece, "mce": mce, "bins": bucket_rows}


def score_nll(home_goals: list[int], away_goals: list[int], probability_lookup: list[float]) -> float:
    if not probability_lookup:
        return float("nan")
    return -sum(math.log(clip_probability(p)) for p in probability_lookup) / len(probability_lookup)
