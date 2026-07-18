from __future__ import annotations

import math
from dataclasses import dataclass

from .markets import derive_all_markets
from .poisson import PoissonConfig, PoissonModel, independent_poisson_distribution
from .types import HistoricalMatch, ModelPrediction, ScoreDistribution


@dataclass(frozen=True)
class DixonColesConfig(PoissonConfig):
    rho_min: float = -0.20
    rho_max: float = 0.20
    rho_step: float = 0.02


class DixonColesModel(PoissonModel):
    model_key = "dixon_coles_v1"

    def __init__(self, config: DixonColesConfig | None = None):
        super().__init__(config or DixonColesConfig())
        self.config: DixonColesConfig
        self.rho = 0.0
        self.log_likelihood = float("-inf")

    def fit(self, matches: list[HistoricalMatch]) -> "DixonColesModel":
        super().fit(matches)
        if not self.converged:
            return self
        best_rho = 0.0
        best_ll = float("-inf")
        rho = self.config.rho_min
        while rho <= self.config.rho_max + 1e-12:
            try:
                ll = dixon_coles_log_likelihood(matches, self, rho)
            except ValueError:
                ll = float("-inf")
            if math.isfinite(ll) and ll > best_ll:
                best_ll = ll
                best_rho = round(rho, 6)
            rho += self.config.rho_step
        self.rho = best_rho
        self.log_likelihood = best_ll
        self.converged = math.isfinite(best_ll)
        return self

    def score_distribution(self, home_team: str, away_team: str) -> ScoreDistribution:
        lambda_home, lambda_away, diagnostics = self.expected_goals(home_team, away_team)
        base = independent_poisson_distribution(lambda_home, lambda_away, self.config.max_goals, self.model_key, diagnostics)
        matrix = []
        for i, row in enumerate(base.matrix):
            adjusted_row = []
            for j, probability in enumerate(row):
                adjusted_row.append(probability * tau(i, j, lambda_home, lambda_away, self.rho))
            matrix.append(adjusted_row)
        total = sum(sum(row) for row in matrix)
        if total <= 0.0 or not math.isfinite(total):
            raise ValueError("invalid Dixon-Coles probability matrix")
        matrix = [[value / total for value in row] for row in matrix]
        diagnostics = {
            **diagnostics,
            "rho": self.rho,
            "log_likelihood": self.log_likelihood,
            "converged": self.converged,
        }
        return ScoreDistribution(
            matrix=matrix,
            max_goals_home=base.max_goals_home,
            max_goals_away=base.max_goals_away,
            tail_mass=base.tail_mass,
            expected_home_goals=lambda_home,
            expected_away_goals=lambda_away,
            model_key=self.model_key,
            diagnostics=diagnostics,
        )

    def predict(self, home_team: str, away_team: str) -> ModelPrediction:
        distribution = self.score_distribution(home_team, away_team)
        markets = derive_all_markets(distribution)
        return ModelPrediction(
            model_key=self.model_key,
            probabilities_1x2=markets["match_winner"],
            markets=markets,
            score_distribution=distribution,
            diagnostics=distribution.diagnostics,
            uncertainty={"score": 0.3 if self.converged else 0.7, "sources": [] if self.converged else ["dixon_coles_not_converged"]},
        )

    def artifact(self) -> dict:
        artifact = super().artifact()
        artifact.update({"rho": self.rho, "log_likelihood": self.log_likelihood})
        return artifact


def tau(home_goals: int, away_goals: int, lambda_home: float, lambda_away: float, rho: float) -> float:
    if rho <= -1.0 or rho >= 1.0:
        raise ValueError("rho must be between -1 and 1")
    if home_goals == 0 and away_goals == 0:
        return 1.0 - lambda_home * lambda_away * rho
    if home_goals == 0 and away_goals == 1:
        return 1.0 + lambda_home * rho
    if home_goals == 1 and away_goals == 0:
        return 1.0 + lambda_away * rho
    if home_goals == 1 and away_goals == 1:
        return 1.0 - rho
    return 1.0


def dixon_coles_log_likelihood(matches: list[HistoricalMatch], model: PoissonModel, rho: float) -> float:
    ll = 0.0
    for match in matches:
        lambda_home, lambda_away, _ = model.expected_goals(match.home_team, match.away_team)
        correction = tau(match.home_goals, match.away_goals, lambda_home, lambda_away, rho)
        if correction <= 0.0:
            return float("-inf")
        log_prob = (
            -lambda_home
            + match.home_goals * math.log(lambda_home)
            - math.lgamma(match.home_goals + 1)
            - lambda_away
            + match.away_goals * math.log(lambda_away)
            - math.lgamma(match.away_goals + 1)
            + math.log(correction)
        )
        if not math.isfinite(log_prob):
            return float("-inf")
        ll += log_prob
    return ll
