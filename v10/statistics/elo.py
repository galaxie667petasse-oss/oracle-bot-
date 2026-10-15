from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from .types import HistoricalMatch, ModelPrediction


@dataclass(frozen=True)
class EloConfig:
    initial_rating: float = 1500.0
    scale: float = 400.0
    k_factor: float = 22.0
    home_advantage: float = 55.0
    draw_base_probability: float = 0.27
    draw_elo_scale: float = 475.0
    min_draw_probability: float = 0.12
    max_draw_probability: float = 0.34
    margin_multiplier_cap: float = 1.8
    season_regression_factor: float = 0.75
    league_mean: float = 1500.0


@dataclass
class EloState:
    ratings: dict[str, float] = field(default_factory=dict)
    home_ratings: dict[str, float] = field(default_factory=dict)
    away_ratings: dict[str, float] = field(default_factory=dict)


class EloModel:
    model_key = "elo_multiclass_v1"

    def __init__(self, config: EloConfig | None = None):
        self.config = config or EloConfig()
        self.state = EloState()
        self.matches_seen = 0

    def rating(self, team: str) -> float:
        return self.state.ratings.get(team, self.config.initial_rating)

    def expected_home_binary(self, home_team: str, away_team: str) -> float:
        return expected_score(
            self.rating(home_team) + self.config.home_advantage,
            self.rating(away_team),
            scale=self.config.scale,
        )

    def probabilities_1x2(self, home_team: str, away_team: str) -> dict[str, float]:
        expected_home = self.expected_home_binary(home_team, away_team)
        diff = abs((self.rating(home_team) + self.config.home_advantage) - self.rating(away_team))
        draw = self.config.draw_base_probability * math.exp(-diff / self.config.draw_elo_scale)
        draw = min(max(draw, self.config.min_draw_probability), self.config.max_draw_probability)
        non_draw = 1.0 - draw
        home = expected_home * non_draw
        away = (1.0 - expected_home) * non_draw
        total = home + draw + away
        return {"home": home / total, "draw": draw / total, "away": away / total}

    def predict(self, home_team: str, away_team: str) -> ModelPrediction:
        probs = self.probabilities_1x2(home_team, away_team)
        markets = {
            "match_winner": probs,
            "double_chance": {
                "1x": probs["home"] + probs["draw"],
                "12": probs["home"] + probs["away"],
                "x2": probs["draw"] + probs["away"],
            },
            "draw_no_bet": {
                "home": probs["home"] / max(probs["home"] + probs["away"], 1e-12),
                "away": probs["away"] / max(probs["home"] + probs["away"], 1e-12),
                "push": probs["draw"],
            },
        }
        return ModelPrediction(
            model_key=self.model_key,
            probabilities_1x2=probs,
            markets=markets,
            diagnostics={
                "home_rating": self.rating(home_team),
                "away_rating": self.rating(away_team),
                "home_advantage": self.config.home_advantage,
                "matches_seen": self.matches_seen,
            },
            uncertainty=elo_uncertainty(self.matches_seen),
        )

    def update(self, match: HistoricalMatch) -> None:
        home_rating = self.rating(match.home_team)
        away_rating = self.rating(match.away_team)
        expected_home = expected_score(home_rating + self.config.home_advantage, away_rating, self.config.scale)
        actual_home = actual_home_score(match.home_goals, match.away_goals)
        multiplier = margin_multiplier(match.home_goals, match.away_goals, cap=self.config.margin_multiplier_cap)
        change = self.config.k_factor * multiplier * (actual_home - expected_home)
        self.state.ratings[match.home_team] = home_rating + change
        self.state.ratings[match.away_team] = away_rating - change
        self.matches_seen += 1

    def fit(self, matches: list[HistoricalMatch]) -> "EloModel":
        previous_season: str | None = None
        for match in sorted(matches, key=lambda item: item.event_time):
            if previous_season is not None and match.season != previous_season:
                self.regress_new_season()
            previous_season = match.season
            self.update(match)
        return self

    def regress_new_season(self) -> None:
        factor = self.config.season_regression_factor
        mean = self.config.league_mean
        self.state.ratings = {team: mean + factor * (rating - mean) for team, rating in self.state.ratings.items()}

    def artifact(self) -> dict:
        return {
            "model_key": self.model_key,
            "config": asdict(self.config),
            "ratings": self.state.ratings,
            "matches_seen": self.matches_seen,
        }


def expected_score(rating_home_adjusted: float, rating_away: float, scale: float = 400.0) -> float:
    return 1.0 / (1.0 + 10.0 ** (-(rating_home_adjusted - rating_away) / scale))


def actual_home_score(home_goals: int, away_goals: int) -> float:
    if home_goals > away_goals:
        return 1.0
    if home_goals < away_goals:
        return 0.0
    return 0.5


def margin_multiplier(home_goals: int, away_goals: int, cap: float = 1.8) -> float:
    margin = abs(home_goals - away_goals)
    if margin <= 1:
        return 1.0
    return min(cap, math.log1p(margin) / math.log(2.0))


def elo_uncertainty(matches_seen: int) -> dict:
    if matches_seen < 30:
        return {"score": 0.45, "sources": ["limited_model_history"]}
    if matches_seen < 120:
        return {"score": 0.28, "sources": ["moderate_model_history"]}
    return {"score": 0.18, "sources": []}
