"""Regulation-time settlement and EV, including Asian quarter lines.

V10 settlement is retained unchanged. V11 requires an explicit 90-minute score:
extra-time scores, abandoned matches and unknown statuses are never inferred.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from v10.settlement import settle_market
from v10.statistics.types import ScoreDistribution


def finite(value: float) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("finite number required")
    return value


def quarter_line(value: float | None) -> float:
    if value is None:
        raise ValueError("line required")
    value = finite(value)
    if not (value * 4).is_integer():
        raise ValueError("line must be a multiple of 0.25")
    return value


def validate(market: str, selection: str, line: float | None = None) -> None:
    allowed = {"match_winner": {"home", "draw", "away"},
               "double_chance": {"1x", "12", "x2"},
               "total_goals": {"over", "under"},
               "both_teams_to_score": {"yes", "no"},
               "asian_handicap": {"home", "away"},
               "draw_no_bet": {"home", "away"}}
    if market == "correct_score":
        parts = selection.split(":")
        if len(parts) != 2 or any(not p.isdigit() for p in parts):
            raise ValueError("correct score requires home:away")
    elif market not in allowed or selection not in allowed[market]:
        raise ValueError("unsupported market or selection")
    if market in {"total_goals", "asian_handicap"}:
        checked = quarter_line(line)
        if market == "total_goals" and checked < 0:
            raise ValueError("negative goal line")
    elif line is not None:
        raise ValueError("unexpected line")


@dataclass(frozen=True)
class Settlement:
    status: str
    profit_units: float | None
    rule_version: str = "v11-regulation-90m-1"


def settle(market: str, selection: str, odds: float, home: int, away: int,
           line: float | None = None, status: str = "FT") -> Settlement:
    validate(market, selection, line)
    odds = finite(odds)
    if odds <= 1:
        raise ValueError("decimal odds must exceed 1")
    if any(type(x) is not int or x < 0 for x in (home, away)):
        raise ValueError("non-negative integer regulation scores required")
    if status in {"CANC", "CANCELLED"}:
        return Settlement("void", 0.0)
    if status not in {"FT", "FINISHED"}:
        return Settlement("pending", None)
    if market == "correct_score":
        profit = odds - 1 if selection == f"{home}:{away}" else -1.0
    elif market in {"asian_handicap", "total_goals"}:
        strike = quarter_line(line)
        # A quarter line is two equal stakes on the neighbouring half lines.
        strikes = [strike] if (strike * 2).is_integer() else [strike - .25, strike + .25]
        margins = []
        for part in strikes:
            if market == "asian_handicap":
                margin = (home - away if selection == "home" else away - home) + part
            else:
                margin = (home + away - part) * (1 if selection == "over" else -1)
            margins.append(odds - 1 if margin > 0 else -1.0 if margin < 0 else 0.0)
        profit = sum(margins) / len(margins)
    else:
        profit = settle_market(market, selection, odds, home, away).profit_units
    kind = "win" if profit > 0 else "loss" if profit < 0 else "push"
    if market in {"asian_handicap", "total_goals"} and len(strikes) == 2:
        if 0 in margins and profit != 0:
            kind = "half_win" if profit > 0 else "half_loss"
    return Settlement(kind, profit)


def price(distribution: ScoreDistribution, market: str, selection: str,
          odds: float, line: float | None = None) -> dict:
    """Expected profit over all score cells; pushes never count as losses."""
    validate(market, selection, line)
    matrix = distribution.matrix
    if not matrix or any(len(row) != len(matrix[0]) for row in matrix):
        raise ValueError("nonempty rectangular score matrix required")
    if any(not math.isfinite(p) or p < 0 for row in matrix for p in row):
        raise ValueError("invalid probability cell")
    mass = sum(map(sum, matrix))
    if abs(mass - 1) > 1e-7:
        raise ValueError("score matrix must sum to one")
    probabilities = {key: 0.0 for key in ("win", "half_win", "push", "half_loss", "loss")}
    ev = 0.0
    for home, row in enumerate(matrix):
        for away, p in enumerate(row):
            result = settle(market, selection, odds, home, away, line)
            probabilities[result.status] += p
            ev += p * result.profit_units
    return {"settlement_probabilities": probabilities, "expected_value": ev,
            "tail_mass": distribution.tail_mass, "rule_version": Settlement.__dataclass_fields__["rule_version"].default}
