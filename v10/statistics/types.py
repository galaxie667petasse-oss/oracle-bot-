from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from v10.time import ensure_utc


FEATURE_SCHEMA_VERSION = "football_features_v1"


@dataclass(frozen=True)
class TemporalContext:
    fixture_id: str
    decision_as_of: datetime
    data_cutoff: datetime
    training_cutoff: datetime

    def __post_init__(self) -> None:
        ensure_utc(self.decision_as_of, "decision_as_of")
        ensure_utc(self.data_cutoff, "data_cutoff")
        ensure_utc(self.training_cutoff, "training_cutoff")
        if self.data_cutoff > self.decision_as_of:
            raise ValueError("data_cutoff cannot be after decision_as_of")
        if self.training_cutoff > self.data_cutoff:
            raise ValueError("training_cutoff cannot be after data_cutoff")


@dataclass(frozen=True)
class HistoricalMatch:
    match_id: str
    event_time: datetime
    competition: str
    season: str
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    status: str = "FINISHED"
    halftime_home_goals: int | None = None
    halftime_away_goals: int | None = None
    odds_home: float | None = None
    odds_draw: float | None = None
    odds_away: float | None = None
    observed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        ensure_utc(self.event_time, "event_time")
        if self.observed_at is not None:
            ensure_utc(self.observed_at, "observed_at")
        if self.home_team == self.away_team:
            raise ValueError("home_team and away_team must differ")
        if self.home_goals < 0 or self.away_goals < 0:
            raise ValueError("goals must be non-negative")

    @property
    def total_goals(self) -> int:
        return self.home_goals + self.away_goals

    @property
    def result_key(self) -> str:
        if self.home_goals > self.away_goals:
            return "home"
        if self.home_goals < self.away_goals:
            return "away"
        return "draw"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["event_time"] = self.event_time.isoformat()
        if self.observed_at:
            data["observed_at"] = self.observed_at.isoformat()
        return data


@dataclass(frozen=True)
class DatasetRow:
    match: HistoricalMatch
    features: dict[str, float | int | str | None]
    labels: dict[str, int | float | str]
    data_completeness: float
    exclusion_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "match": self.match.to_dict(),
            "features": self.features,
            "labels": self.labels,
            "data_completeness": self.data_completeness,
            "exclusion_reason": self.exclusion_reason,
        }


@dataclass(frozen=True)
class ScoreDistribution:
    matrix: list[list[float]]
    max_goals_home: int
    max_goals_away: int
    tail_mass: float
    expected_home_goals: float
    expected_away_goals: float
    model_key: str
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def total_mass(self) -> float:
        return sum(sum(row) for row in self.matrix)


@dataclass(frozen=True)
class ModelPrediction:
    model_key: str
    probabilities_1x2: dict[str, float]
    markets: dict[str, dict[str, float]]
    score_distribution: ScoreDistribution | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    uncertainty: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_key": self.model_key,
            "probabilities_1x2": self.probabilities_1x2,
            "markets": self.markets,
            "score_distribution": self.score_distribution.__dict__ if self.score_distribution else None,
            "diagnostics": self.diagnostics,
            "uncertainty": self.uncertainty,
        }
