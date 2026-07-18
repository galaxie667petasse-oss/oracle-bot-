from dataclasses import dataclass
from typing import Any

from .odds import expected_value_per_unit, parse_decimal_odds, validate_probability


@dataclass(frozen=True)
class PaperRiskConfig:
    kelly_fraction: float = 0.10
    max_signal_fraction: float = 0.01
    max_daily_exposure_fraction: float = 0.03
    max_competition_exposure_fraction: float = 0.02
    max_correlated_exposure_fraction: float = 0.015
    max_uncertainty: float = 0.08
    real_money_actions_enabled: bool = False


def full_kelly_fraction(model_probability: Any, decimal_odds: Any) -> float:
    p = validate_probability(model_probability, "model_probability")
    price = parse_decimal_odds(decimal_odds)
    b = price - 1.0
    q = 1.0 - p
    value = (b * p - q) / b
    return max(0.0, value)


def capped_paper_fraction(
    model_probability: Any,
    decimal_odds: Any,
    uncertainty: float,
    config: PaperRiskConfig | None = None,
    current_daily_exposure: float = 0.0,
    current_competition_exposure: float = 0.0,
    current_correlated_exposure: float = 0.0,
) -> dict[str, Any]:
    config = config or PaperRiskConfig()
    if config.real_money_actions_enabled:
        raise ValueError("real money actions are unsupported by the V10 lab risk layer")
    ev = expected_value_per_unit(model_probability, decimal_odds)
    if ev <= 0.0:
        return {"fraction": 0.0, "reason": "negative_or_zero_ev", "paper_only": True}
    if uncertainty > config.max_uncertainty:
        return {"fraction": 0.0, "reason": "uncertainty_too_high", "paper_only": True}
    raw = full_kelly_fraction(model_probability, decimal_odds) * max(0.0, config.kelly_fraction)
    remaining_daily = max(0.0, config.max_daily_exposure_fraction - current_daily_exposure)
    remaining_competition = max(0.0, config.max_competition_exposure_fraction - current_competition_exposure)
    remaining_correlated = max(0.0, config.max_correlated_exposure_fraction - current_correlated_exposure)
    capped = min(raw, config.max_signal_fraction, remaining_daily, remaining_competition, remaining_correlated)
    reason = "capped" if capped < raw else "ok"
    return {
        "fraction": round(max(0.0, capped), 6),
        "full_kelly": round(full_kelly_fraction(model_probability, decimal_odds), 6),
        "expected_value_per_unit": round(ev, 6),
        "reason": reason,
        "paper_only": True,
        "lab_only": True,
        "can_influence_picks": False,
    }

