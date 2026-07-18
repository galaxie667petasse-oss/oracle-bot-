from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from .markets import derive_all_markets
from .types import HistoricalMatch, ModelPrediction, ScoreDistribution


@dataclass(frozen=True)
class PoissonConfig:
    max_goals: int = 10
    shrinkage_matches: float = 8.0
    min_lambda: float = 0.05
    max_lambda: float = 5.5
    exclude_friendlies: bool = True


@dataclass
class TeamGoalStats:
    matches: int = 0
    home_matches: int = 0
    away_matches: int = 0
    goals_for: float = 0.0
    goals_against: float = 0.0
    home_goals_for: float = 0.0
    home_goals_against: float = 0.0
    away_goals_for: float = 0.0
    away_goals_against: float = 0.0


class PoissonModel:
    model_key = "poisson_independent_v1"

    def __init__(self, config: PoissonConfig | None = None):
        self.config = config or PoissonConfig()
        self.team_stats: dict[str, TeamGoalStats] = {}
        self.matches_seen = 0
        self.avg_home_goals = 1.35
        self.avg_away_goals = 1.10
        self.converged = False

    def fit(self, matches: list[HistoricalMatch]) -> "PoissonModel":
        clean = [m for m in matches if m.status == "FINISHED"]
        if not clean:
            self.converged = False
            return self
        total_home = sum(m.home_goals for m in clean)
        total_away = sum(m.away_goals for m in clean)
        self.avg_home_goals = total_home / len(clean)
        self.avg_away_goals = total_away / len(clean)
        for match in clean:
            self._update_stats(match)
        self.matches_seen = len(clean)
        self.converged = True
        return self

    def _stats(self, team: str) -> TeamGoalStats:
        if team not in self.team_stats:
            self.team_stats[team] = TeamGoalStats()
        return self.team_stats[team]

    def _update_stats(self, match: HistoricalMatch) -> None:
        home = self._stats(match.home_team)
        away = self._stats(match.away_team)
        home.matches += 1
        home.home_matches += 1
        home.goals_for += match.home_goals
        home.goals_against += match.away_goals
        home.home_goals_for += match.home_goals
        home.home_goals_against += match.away_goals
        away.matches += 1
        away.away_matches += 1
        away.goals_for += match.away_goals
        away.goals_against += match.home_goals
        away.away_goals_for += match.away_goals
        away.away_goals_against += match.home_goals

    def expected_goals(self, home_team: str, away_team: str) -> tuple[float, float, dict]:
        home = self.team_stats.get(home_team, TeamGoalStats())
        away = self.team_stats.get(away_team, TeamGoalStats())
        h_attack = shrink_ratio(home.home_goals_for, home.home_matches, self.avg_home_goals, self.config.shrinkage_matches)
        h_defence_weakness = shrink_ratio(home.home_goals_against, home.home_matches, self.avg_away_goals, self.config.shrinkage_matches)
        a_attack = shrink_ratio(away.away_goals_for, away.away_matches, self.avg_away_goals, self.config.shrinkage_matches)
        a_defence_weakness = shrink_ratio(away.away_goals_against, away.away_matches, self.avg_home_goals, self.config.shrinkage_matches)
        lambda_home = self.avg_home_goals * (h_attack / max(self.avg_home_goals, 1e-9)) * (a_defence_weakness / max(self.avg_home_goals, 1e-9))
        lambda_away = self.avg_away_goals * (a_attack / max(self.avg_away_goals, 1e-9)) * (h_defence_weakness / max(self.avg_away_goals, 1e-9))
        lambda_home = min(max(lambda_home, self.config.min_lambda), self.config.max_lambda)
        lambda_away = min(max(lambda_away, self.config.min_lambda), self.config.max_lambda)
        diagnostics = {
            "home_team_matches": home.matches,
            "away_team_matches": away.matches,
            "avg_home_goals": self.avg_home_goals,
            "avg_away_goals": self.avg_away_goals,
            "converged": self.converged,
        }
        return lambda_home, lambda_away, diagnostics

    def score_distribution(self, home_team: str, away_team: str) -> ScoreDistribution:
        lambda_home, lambda_away, diagnostics = self.expected_goals(home_team, away_team)
        return independent_poisson_distribution(lambda_home, lambda_away, self.config.max_goals, self.model_key, diagnostics)

    def predict(self, home_team: str, away_team: str) -> ModelPrediction:
        distribution = self.score_distribution(home_team, away_team)
        markets = derive_all_markets(distribution)
        return ModelPrediction(
            model_key=self.model_key,
            probabilities_1x2=markets["match_winner"],
            markets=markets,
            score_distribution=distribution,
            diagnostics=distribution.diagnostics,
            uncertainty=goal_model_uncertainty(self.matches_seen, distribution.diagnostics),
        )

    def artifact(self) -> dict:
        return {
            "model_key": self.model_key,
            "config": asdict(self.config),
            "avg_home_goals": self.avg_home_goals,
            "avg_away_goals": self.avg_away_goals,
            "team_stats": {team: asdict(stats) for team, stats in self.team_stats.items()},
            "matches_seen": self.matches_seen,
            "converged": self.converged,
        }


def shrink_ratio(total: float, count: int, fallback_average: float, shrinkage_matches: float) -> float:
    if count <= 0:
        return fallback_average
    return (total + shrinkage_matches * fallback_average) / (count + shrinkage_matches)


def poisson_pmf(lam: float, k: int) -> float:
    if lam <= 0.0:
        raise ValueError("lambda must be positive")
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def independent_poisson_distribution(lambda_home: float, lambda_away: float, max_goals: int, model_key: str, diagnostics: dict | None = None) -> ScoreDistribution:
    if lambda_home <= 0.0 or lambda_away <= 0.0:
        raise ValueError("lambdas must be positive")
    if max_goals < 3:
        raise ValueError("max_goals must be >= 3")
    home_probs = [poisson_pmf(lambda_home, i) for i in range(max_goals + 1)]
    away_probs = [poisson_pmf(lambda_away, j) for j in range(max_goals + 1)]
    mass_home = sum(home_probs)
    mass_away = sum(away_probs)
    matrix = [[home_probs[i] * away_probs[j] for j in range(max_goals + 1)] for i in range(max_goals + 1)]
    total = sum(sum(row) for row in matrix)
    tail_mass = max(0.0, 1.0 - total)
    if total > 0:
        matrix = [[value / total for value in row] for row in matrix]
    return ScoreDistribution(
        matrix=matrix,
        max_goals_home=max_goals,
        max_goals_away=max_goals,
        tail_mass=tail_mass + max(0.0, 1.0 - mass_home) + max(0.0, 1.0 - mass_away),
        expected_home_goals=lambda_home,
        expected_away_goals=lambda_away,
        model_key=model_key,
        diagnostics=diagnostics or {},
    )


def goal_model_uncertainty(matches_seen: int, diagnostics: dict) -> dict:
    sources: list[str] = []
    score = 0.18
    if matches_seen < 80:
        score += 0.22
        sources.append("limited_goal_history")
    if diagnostics.get("home_team_matches", 0) < 8:
        score += 0.12
        sources.append("limited_home_team_history")
    if diagnostics.get("away_team_matches", 0) < 8:
        score += 0.12
        sources.append("limited_away_team_history")
    if not diagnostics.get("converged", False):
        score += 0.2
        sources.append("model_not_converged")
    return {"score": min(score, 0.95), "sources": sources}
