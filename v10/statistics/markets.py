from __future__ import annotations

from .types import ScoreDistribution


def _validate_matrix(distribution: ScoreDistribution) -> None:
    if not distribution.matrix or not distribution.matrix[0]:
        raise ValueError("score distribution matrix is empty")
    total = distribution.total_mass()
    if total <= 0.0:
        raise ValueError("score distribution has no probability mass")


def normalize_probabilities(values: dict[str, float]) -> dict[str, float]:
    total = sum(values.values())
    if total <= 0.0:
        raise ValueError("probabilities sum to zero")
    normalized = {key: max(0.0, float(value) / total) for key, value in values.items()}
    residual = 1.0 - sum(normalized.values())
    if normalized:
        first = next(iter(normalized))
        normalized[first] += residual
    return normalized


def derive_1x2(distribution: ScoreDistribution) -> dict[str, float]:
    _validate_matrix(distribution)
    home = draw = away = 0.0
    for i, row in enumerate(distribution.matrix):
        for j, probability in enumerate(row):
            if i > j:
                home += probability
            elif i == j:
                draw += probability
            else:
                away += probability
    return normalize_probabilities({"home": home, "draw": draw, "away": away})


def derive_double_chance(one_x_two: dict[str, float]) -> dict[str, float]:
    return {
        "1x": one_x_two["home"] + one_x_two["draw"],
        "12": one_x_two["home"] + one_x_two["away"],
        "x2": one_x_two["draw"] + one_x_two["away"],
    }


def derive_draw_no_bet(one_x_two: dict[str, float]) -> dict[str, float]:
    non_draw = one_x_two["home"] + one_x_two["away"]
    if non_draw <= 0.0:
        return {"home": 0.5, "away": 0.5, "push": 1.0}
    return {
        "home": one_x_two["home"] / non_draw,
        "away": one_x_two["away"] / non_draw,
        "push": one_x_two["draw"],
    }


def derive_totals(distribution: ScoreDistribution, lines: tuple[float, ...] = (1.5, 2.5, 3.5)) -> dict[str, dict[str, float]]:
    _validate_matrix(distribution)
    totals: dict[str, dict[str, float]] = {}
    for line in lines:
        over = 0.0
        for i, row in enumerate(distribution.matrix):
            for j, probability in enumerate(row):
                if i + j > line:
                    over += probability
        over = min(max(over, 0.0), 1.0)
        key = str(line).replace(".", "_")
        totals[f"over_under_{key}"] = {"over": over, "under": 1.0 - over}
    return totals


def derive_btts(distribution: ScoreDistribution) -> dict[str, float]:
    _validate_matrix(distribution)
    yes = 0.0
    for i, row in enumerate(distribution.matrix):
        for j, probability in enumerate(row):
            if i > 0 and j > 0:
                yes += probability
    yes = min(max(yes, 0.0), 1.0)
    return {"yes": yes, "no": 1.0 - yes}


def derive_all_markets(distribution: ScoreDistribution) -> dict[str, dict[str, float]]:
    one_x_two = derive_1x2(distribution)
    markets = {
        "match_winner": one_x_two,
        "double_chance": derive_double_chance(one_x_two),
        "draw_no_bet": derive_draw_no_bet(one_x_two),
        "both_teams_to_score": derive_btts(distribution),
    }
    markets.update(derive_totals(distribution))
    return markets
