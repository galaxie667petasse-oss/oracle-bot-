from dataclasses import asdict, dataclass
from typing import Any

from .odds import parse_decimal_odds


FINAL_STATUSES = {"FT", "AET", "PEN", "FINISHED", "MATCH FINISHED"}
VOID_STATUSES = {"CANC", "CANCELLED", "ABD", "ABANDONED", "PST", "POSTPONED", "SUSP"}
RULE_VERSION = "v10.0-regulation-time-baseline"


@dataclass(frozen=True)
class SettlementResult:
    result_status: str
    profit_units: float
    settlement_status: str
    reason: str
    rule_version: str = RULE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _score(home_goals: Any, away_goals: Any) -> tuple[int, int] | None:
    try:
        return int(home_goals), int(away_goals)
    except Exception:
        return None


def _profit(result_status: str, decimal_odds: Any) -> float:
    if result_status == "win":
        return round(parse_decimal_odds(decimal_odds) - 1.0, 6)
    if result_status == "loss":
        return -1.0
    return 0.0


def settle_market(
    market_key: str,
    selection_key: str,
    decimal_odds: Any,
    home_goals: Any,
    away_goals: Any,
    fixture_status: str = "FT",
    line: float | None = None,
) -> SettlementResult:
    status = str(fixture_status or "").strip().upper()
    market = str(market_key or "").strip().lower()
    selection = str(selection_key or "").strip().lower()
    if status in VOID_STATUSES:
        return SettlementResult("void", 0.0, "void", f"fixture_status={status}")
    if status and status not in FINAL_STATUSES:
        return SettlementResult("unknown", 0.0, "pending_result", f"fixture_not_final={status}")
    parsed = _score(home_goals, away_goals)
    if parsed is None:
        return SettlementResult("unknown", 0.0, "pending_result", "score_missing")
    home, away = parsed
    total = home + away
    result = "unknown"
    reason = "unsupported_market"

    if market in {"h2h", "match_winner", "1x2"}:
        if selection == "home":
            result = "win" if home > away else "loss"
        elif selection == "away":
            result = "win" if away > home else "loss"
        elif selection == "draw":
            result = "win" if home == away else "loss"
        reason = "match_winner_regulation"
    elif market in {"draw_no_bet", "dnb"}:
        if home == away:
            result = "push"
        elif selection == "home":
            result = "win" if home > away else "loss"
        elif selection == "away":
            result = "win" if away > home else "loss"
        reason = "draw_no_bet_regulation"
    elif market in {"double_chance", "dc"}:
        home_win = home > away
        away_win = away > home
        draw = home == away
        accepted = {
            "home_draw": home_win or draw,
            "1x": home_win or draw,
            "home_away": home_win or away_win,
            "12": home_win or away_win,
            "draw_away": draw or away_win,
            "x2": draw or away_win,
        }
        result = "win" if accepted.get(selection, False) else "loss"
        reason = "double_chance_regulation"
    elif market in {"total_goals", "totals", "over_under"}:
        if line is None:
            return SettlementResult("unknown", 0.0, "pending_result", "line_missing")
        if total == line:
            result = "push"
        elif selection == "over":
            result = "win" if total > line else "loss"
        elif selection == "under":
            result = "win" if total < line else "loss"
        reason = f"total_goals_line_{line}"
    elif market in {"both_teams_to_score", "btts"}:
        both = home > 0 and away > 0
        if selection in {"yes", "oui"}:
            result = "win" if both else "loss"
        elif selection in {"no", "non"}:
            result = "loss" if both else "win"
        reason = "btts_regulation"

    if result == "unknown":
        return SettlementResult("unknown", 0.0, "pending_result", reason)
    return SettlementResult(result, _profit(result, decimal_odds), "settled", reason)

