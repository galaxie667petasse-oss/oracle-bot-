import math
from typing import Any, Mapping


def parse_decimal_odds(value: Any) -> float:
    try:
        price = float(str(value).strip().replace(",", "."))
    except Exception as exc:
        raise ValueError("decimal odds must be numeric") from exc
    if not math.isfinite(price) or price <= 1.0:
        raise ValueError("decimal odds must be > 1.0")
    return price


def validate_probability(value: Any, name: str = "probability") -> float:
    try:
        probability = float(str(value).strip().replace(",", "."))
    except Exception as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(probability) or probability < 0.0 or probability > 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return probability


def raw_implied_probability(decimal_odds: Any) -> float:
    return 1.0 / parse_decimal_odds(decimal_odds)


def overround(selection_odds: Mapping[str, Any]) -> float:
    if not selection_odds:
        raise ValueError("market must contain at least one selection")
    return sum(raw_implied_probability(odds) for odds in selection_odds.values())


def proportional_no_vig(selection_odds: Mapping[str, Any]) -> dict[str, float]:
    total = overround(selection_odds)
    if total <= 0.0:
        raise ValueError("market overround must be positive")
    return {selection: raw_implied_probability(odds) / total for selection, odds in selection_odds.items()}


def fair_odds(probability: Any) -> float:
    probability = validate_probability(probability)
    if probability <= 0.0:
        raise ValueError("probability must be > 0 for fair odds")
    return 1.0 / probability


def edge_probability_points(model_probability: Any, market_fair_probability: Any) -> float:
    return validate_probability(model_probability, "model_probability") - validate_probability(
        market_fair_probability,
        "market_fair_probability",
    )


def expected_value_per_unit(model_probability: Any, decimal_odds: Any) -> float:
    p = validate_probability(model_probability, "model_probability")
    price = parse_decimal_odds(decimal_odds)
    return p * (price - 1.0) - (1.0 - p)


def clv_odds_pct(taken_odds: Any, closing_odds: Any) -> float:
    taken = parse_decimal_odds(taken_odds)
    closing = parse_decimal_odds(closing_odds)
    return taken / closing - 1.0


def clv_probability_points(closing_fair_probability: Any, taken_fair_probability: Any) -> float:
    return validate_probability(closing_fair_probability, "closing_fair_probability") - validate_probability(
        taken_fair_probability,
        "taken_fair_probability",
    )

