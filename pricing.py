import math
from typing import Any, Dict, Iterable, Optional


def _as_float(value: Any) -> Optional[float]:
    try:
        number = float(str(value).strip().replace(",", "."))
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    return number


def _bounded_probability(value: Any) -> Optional[float]:
    probability = _as_float(value)
    if probability is None:
        return None
    return min(1.0, max(0.0, probability))


def implied_probability(odds: Any) -> Optional[float]:
    price = _as_float(odds)
    if price is None or price <= 1.0:
        return None
    return min(1.0, max(0.0, 1.0 / price))


def fair_odds(probability: Any) -> Optional[float]:
    probability = _bounded_probability(probability)
    if probability is None or probability <= 0.0:
        return None
    return 1.0 / probability


def market_margin(probabilities: Iterable[Any]) -> Optional[float]:
    total = 0.0
    count = 0
    for value in probabilities:
        probability = _bounded_probability(value)
        if probability is None:
            return None
        total += probability
        count += 1
    if count == 0:
        return None
    return total - 1.0


def _remove_vig(named_odds: Dict[str, Any]) -> Optional[Dict[str, float]]:
    implied = {}
    for key, odds in named_odds.items():
        probability = implied_probability(odds)
        if probability is None:
            return None
        implied[key] = probability
    total = sum(implied.values())
    if total <= 0.0:
        return None
    return {key: probability / total for key, probability in implied.items()}


def remove_vig_1x2(home_odds: Any, draw_odds: Any, away_odds: Any) -> Optional[Dict[str, float]]:
    return _remove_vig({"home": home_odds, "draw": draw_odds, "away": away_odds})


def remove_vig_two_way(over_odds: Any, under_odds: Any) -> Optional[Dict[str, float]]:
    return _remove_vig({"over": over_odds, "under": under_odds})


def edge_probability(model_probability: Any, market_probability: Any) -> Optional[float]:
    model = _bounded_probability(model_probability)
    market = _bounded_probability(market_probability)
    if model is None or market is None:
        return None
    return model - market


def expected_value(probability: Any, odds: Any) -> Optional[float]:
    probability = _bounded_probability(probability)
    price = _as_float(odds)
    if probability is None or price is None or price <= 1.0:
        return None
    return probability * price - 1.0
