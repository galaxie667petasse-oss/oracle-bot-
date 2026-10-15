from __future__ import annotations

import itertools
from dataclasses import dataclass

from .markets import normalize_probabilities
from .metrics import multiclass_log_loss


@dataclass(frozen=True)
class EnsembleWeights:
    weights: dict[str, float]
    status: str = "DRAFT"

    def validate(self) -> None:
        if not self.weights:
            raise ValueError("ensemble requires weights")
        if any(value < 0.0 for value in self.weights.values()):
            raise ValueError("ensemble weights must be non-negative")
        if abs(sum(self.weights.values()) - 1.0) > 1e-6:
            raise ValueError("ensemble weights must sum to 1")


def combine_probabilities(model_probabilities: dict[str, dict[str, float]], weights: EnsembleWeights) -> dict[str, float]:
    weights.validate()
    combined = {"home": 0.0, "draw": 0.0, "away": 0.0}
    for model_key, weight in weights.weights.items():
        if model_key not in model_probabilities:
            continue
        probs = model_probabilities[model_key]
        for selection in combined:
            value = probs.get(selection)
            if value is None or value < 0.0 or value > 1.0:
                raise ValueError("invalid model probability")
            combined[selection] += weight * value
    return normalize_probabilities(combined)


def learn_weights_grid(model_predictions: list[dict[str, dict[str, float]]], labels: list[str], model_keys: list[str], step: float = 0.25) -> tuple[EnsembleWeights, dict]:
    if not model_keys:
        raise ValueError("model_keys required")
    if len(model_predictions) != len(labels):
        raise ValueError("predictions and labels length mismatch")
    best_weights = {key: 1.0 / len(model_keys) for key in model_keys}
    best_loss = float("inf")
    grid = [round(i * step, 10) for i in range(int(1.0 / step) + 1)]
    for values in itertools.product(grid, repeat=len(model_keys)):
        if abs(sum(values) - 1.0) > 1e-9:
            continue
        # Mild shrinkage avoids tiny validation samples assigning everything to one model.
        if max(values) > 0.85 and len(labels) < 200:
            continue
        weights = EnsembleWeights(dict(zip(model_keys, values)))
        combined = [combine_probabilities(row, weights) for row in model_predictions]
        loss = multiclass_log_loss(combined, labels)
        if loss < best_loss:
            best_loss = loss
            best_weights = weights.weights
    return EnsembleWeights(best_weights, status="VALIDATED"), {"validation_log_loss": best_loss, "sample_count": len(labels)}
