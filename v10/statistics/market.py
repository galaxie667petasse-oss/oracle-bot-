from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from v10.candidates import CandidateThresholds, evaluate_candidate
from v10.odds import expected_value_per_unit, proportional_no_vig, raw_implied_probability


@dataclass(frozen=True)
class MarketComparison:
    market_key: str
    selection_key: str
    p_model_raw: float
    p_model_calibrated: float
    p_market_raw: float
    p_market_fair: float
    best_decimal_odds: float
    median_decimal_odds: float
    bookmaker_count: int
    odds_observed_at: str
    edge_raw: float
    edge_calibrated: float
    expected_value_raw: float
    expected_value_calibrated: float
    candidate_decision: str
    candidate_blockers: list[str]


def compare_1x2_market(
    fixture_id: str,
    model_probabilities: Mapping[str, float],
    odds: Mapping[str, float],
    odds_observed_at: str,
    bookmaker_count: int,
    thresholds: CandidateThresholds | None = None,
) -> list[MarketComparison]:
    fair = proportional_no_vig(odds)
    rows = []
    for selection, p_model in model_probabilities.items():
        price = float(odds[selection])
        p_market_raw = raw_implied_probability(price)
        p_market_fair = fair[selection]
        calibrated = float(p_model)
        candidate = evaluate_candidate(
            fixture_id=fixture_id,
            market_key="match_winner",
            selection_key=selection,
            decimal_odds=price,
            p_model=calibrated,
            p_market_fair=p_market_fair,
            uncertainty_low=max(0.0, calibrated - 0.04),
            uncertainty_high=min(1.0, calibrated + 0.04),
            data_quality_status="PASS",
            bookmaker_count=bookmaker_count,
            thresholds=thresholds,
        )
        rows.append(
            MarketComparison(
                market_key="match_winner",
                selection_key=selection,
                p_model_raw=float(p_model),
                p_model_calibrated=calibrated,
                p_market_raw=p_market_raw,
                p_market_fair=p_market_fair,
                best_decimal_odds=price,
                median_decimal_odds=price,
                bookmaker_count=bookmaker_count,
                odds_observed_at=odds_observed_at,
                edge_raw=float(p_model) - p_market_fair,
                edge_calibrated=calibrated - p_market_fair,
                expected_value_raw=expected_value_per_unit(float(p_model), price),
                expected_value_calibrated=expected_value_per_unit(calibrated, price),
                candidate_decision=candidate.decision,
                candidate_blockers=candidate.blockers,
            )
        )
    return rows
