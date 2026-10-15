"""Keep V10 models and adapt optional penaltyblog behind the same prediction type."""
from __future__ import annotations

import importlib.metadata
import math

from v10.statistics.markets import derive_all_markets
from v10.statistics.types import HistoricalMatch, ModelPrediction, ScoreDistribution


class PenaltyblogAdapter:
    classes = {"poisson": "PoissonGoalsModel", "dixon_coles": "DixonColesGoalModel",
               "bivariate_poisson": "BivariatePoissonGoalModel"}

    def __init__(self, kind: str):
        if kind not in self.classes:
            raise ValueError("unsupported penaltyblog model")
        self.kind = kind
        self.model_key = f"penaltyblog_{kind}_v1"
        self.model = None

    def fit(self, matches: list[HistoricalMatch]) -> "PenaltyblogAdapter":
        try:
            from penaltyblog import models
        except ImportError as exc:
            raise RuntimeError("Install requirements-v11.txt to enable penaltyblog") from exc
        if not matches or any(m.status != "FINISHED" for m in matches):
            raise ValueError("finished history required")
        self.version = importlib.metadata.version("penaltyblog")
        cls = getattr(models, self.classes[self.kind])
        self.model = cls([m.home_goals for m in matches], [m.away_goals for m in matches],
                         [m.home_team for m in matches], [m.away_team for m in matches])
        self.model.fit()
        return self

    def predict(self, home_team: str, away_team: str) -> ModelPrediction:
        if self.model is None:
            raise ValueError("model not fitted")
        grid = self.model.predict(home_team, away_team, max_goals=12, normalize=False)
        matrix = grid.grid.tolist()
        mass = sum(map(sum, matrix))
        if not math.isfinite(mass) or not 0 < mass <= 1.000001:
            raise ValueError("invalid penaltyblog probability mass")
        if any(not math.isfinite(x) or x < 0 for row in matrix for x in row):
            raise ValueError("invalid penaltyblog grid")
        dist = ScoreDistribution([[x / mass for x in row] for row in matrix],
                                 len(matrix)-1, len(matrix[0])-1, max(0, 1-mass),
                                 float(grid.home_goal_expectation), float(grid.away_goal_expectation),
                                 self.model_key, {"library_version": self.version})
        markets = derive_all_markets(dist)
        return ModelPrediction(self.model_key, markets["match_winner"], markets, dist,
                               {"library_version": self.version},
                               {"status": "not_estimated", "validated_for_signals": False})
