from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from .metrics import binary_brier, binary_log_loss, multiclass_log_loss


@dataclass(frozen=True)
class CalibrationResult:
    method: str
    status: str
    parameters: dict[str, float]
    sample_count: int
    metrics_before: dict[str, float]
    metrics_after: dict[str, float]
    reason: str = ""


class PlattCalibrator:
    method = "platt"

    def __init__(self, a: float = 1.0, b: float = 0.0):
        self.a = a
        self.b = b

    def fit(self, probabilities: list[float], labels: list[int], min_samples: int = 30, steps: int = 500, lr: float = 0.05) -> CalibrationResult:
        if len(probabilities) != len(labels):
            raise ValueError("probabilities and labels length mismatch")
        before = {"log_loss": binary_log_loss(probabilities, labels), "brier": binary_brier(probabilities, labels)}
        if len(labels) < min_samples:
            return CalibrationResult(self.method, "FALLBACK_UNCALIBRATED", {"a": 1.0, "b": 0.0}, len(labels), before, before, "small_sample")
        a, b = self.a, self.b
        logits = [safe_logit(p) for p in probabilities]
        for _ in range(steps):
            grad_a = 0.0
            grad_b = 0.0
            for x, y in zip(logits, labels):
                pred = sigmoid(a * x + b)
                grad_a += (pred - y) * x
                grad_b += pred - y
            a -= lr * grad_a / len(labels)
            b -= lr * grad_b / len(labels)
        self.a, self.b = a, b
        calibrated = [self.predict(p) for p in probabilities]
        after = {"log_loss": binary_log_loss(calibrated, labels), "brier": binary_brier(calibrated, labels)}
        status = "VALIDATED" if after["log_loss"] <= before["log_loss"] + 1e-9 else "REJECTED_DEGRADED"
        if status != "VALIDATED":
            self.a, self.b = 1.0, 0.0
            after = before
        return CalibrationResult(self.method, status, {"a": self.a, "b": self.b}, len(labels), before, after)

    def predict(self, probability: float) -> float:
        return sigmoid(self.a * safe_logit(probability) + self.b)

    def artifact(self) -> dict:
        return {"method": self.method, "a": self.a, "b": self.b}


class TemperatureScaler:
    method = "temperature_scaling"

    def __init__(self, temperature: float = 1.0):
        self.temperature = temperature

    def fit(self, probabilities: list[dict[str, float]], labels: list[str], min_samples: int = 30) -> CalibrationResult:
        before = {"log_loss": multiclass_log_loss(probabilities, labels)}
        if len(labels) < min_samples:
            return CalibrationResult(self.method, "FALLBACK_UNCALIBRATED", {"temperature": 1.0}, len(labels), before, before, "small_sample")
        best_temp = 1.0
        best_loss = before["log_loss"]
        for idx in range(5, 61):
            temp = idx / 10.0
            adjusted = [apply_temperature(prob, temp) for prob in probabilities]
            loss = multiclass_log_loss(adjusted, labels)
            if loss < best_loss:
                best_loss = loss
                best_temp = temp
        self.temperature = best_temp
        after = {"log_loss": best_loss}
        return CalibrationResult(self.method, "VALIDATED", {"temperature": best_temp}, len(labels), before, after)

    def predict(self, probabilities: dict[str, float]) -> dict[str, float]:
        return apply_temperature(probabilities, self.temperature)


def safe_logit(probability: float) -> float:
    p = min(max(float(probability), 1e-9), 1.0 - 1e-9)
    return math.log(p / (1.0 - p))


def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def apply_temperature(probabilities: dict[str, float], temperature: float) -> dict[str, float]:
    if temperature <= 0:
        raise ValueError("temperature must be positive")
    logits = {key: safe_logit(value) / temperature for key, value in probabilities.items()}
    max_logit = max(logits.values())
    exps = {key: math.exp(value - max_logit) for key, value in logits.items()}
    total = sum(exps.values())
    return {key: value / total for key, value in exps.items()}


def calibration_result_to_dict(result: CalibrationResult) -> dict:
    return asdict(result)
