from dataclasses import asdict, dataclass
from typing import Any

from .data_quality import PASS, PASS_WITH_WARNINGS
from .odds import edge_probability_points, expected_value_per_unit, parse_decimal_odds, validate_probability


@dataclass(frozen=True)
class CandidateThresholds:
    min_edge_probability_points: float = 0.03
    min_expected_value_per_unit: float = 0.02
    max_uncertainty: float = 0.08
    min_bookmaker_count: int = 2
    max_finalists_per_scan: int = 5


@dataclass(frozen=True)
class CandidateEvaluation:
    fixture_id: str
    market_key: str
    selection_key: str
    decimal_odds: float
    p_model: float
    p_market_fair: float
    edge_probability_points: float
    expected_value_per_unit: float
    uncertainty_width: float
    data_quality_status: str
    decision: str
    blockers: list[str]
    lab_only: bool = True
    can_influence_picks: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_candidate(
    fixture_id: str,
    market_key: str,
    selection_key: str,
    decimal_odds: Any,
    p_model: Any,
    p_market_fair: Any,
    uncertainty_low: Any,
    uncertainty_high: Any,
    data_quality_status: str,
    bookmaker_count: int,
    thresholds: CandidateThresholds | None = None,
) -> CandidateEvaluation:
    thresholds = thresholds or CandidateThresholds()
    price = parse_decimal_odds(decimal_odds)
    model = validate_probability(p_model, "p_model")
    market = validate_probability(p_market_fair, "p_market_fair")
    low = validate_probability(uncertainty_low, "uncertainty_low")
    high = validate_probability(uncertainty_high, "uncertainty_high")
    if high < low:
        raise ValueError("uncertainty_high must be >= uncertainty_low")
    edge = edge_probability_points(model, market)
    ev = expected_value_per_unit(model, price)
    uncertainty = high - low
    blockers: list[str] = []
    if data_quality_status not in {PASS, PASS_WITH_WARNINGS}:
        blockers.append("data_quality_not_pass")
    if bookmaker_count < thresholds.min_bookmaker_count:
        blockers.append("insufficient_bookmaker_count")
    if edge < thresholds.min_edge_probability_points:
        blockers.append("edge_below_threshold")
    if ev < thresholds.min_expected_value_per_unit:
        blockers.append("ev_below_threshold")
    if uncertainty > thresholds.max_uncertainty:
        blockers.append("uncertainty_too_high")
    return CandidateEvaluation(
        fixture_id=str(fixture_id),
        market_key=str(market_key),
        selection_key=str(selection_key),
        decimal_odds=round(price, 6),
        p_model=round(model, 6),
        p_market_fair=round(market, 6),
        edge_probability_points=round(edge, 6),
        expected_value_per_unit=round(ev, 6),
        uncertainty_width=round(uncertainty, 6),
        data_quality_status=str(data_quality_status),
        decision="candidate" if not blockers else "rejected",
        blockers=blockers,
    )

