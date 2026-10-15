from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from v10.time import parse_utc


KNOWN_MARKETS = {"match_winner", "double_chance", "draw_no_bet", "total_goals", "both_teams_to_score"}
SELECTIONS_BY_MARKET = {
    "match_winner": {"home", "draw", "away"},
    "double_chance": {"1x", "12", "x2", "home_draw", "home_away", "draw_away"},
    "draw_no_bet": {"home", "away"},
    "total_goals": {"over", "under"},
    "both_teams_to_score": {"yes", "no"},
}


class CanonicalFixtureObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_key: str
    external_fixture_id: str
    external_competition_id: str
    competition_name: str
    country: str | None = None
    season_external_id: str | None = None
    season_name: str | None = None
    home_team_external_id: str
    away_team_external_id: str
    home_team_name: str
    away_team_name: str
    event_time: datetime
    canonical_status: str
    provider_status: str | None = None
    venue: str | None = None
    round_name: str | None = None
    observed_at: datetime
    metadata: dict[str, Any] = {}
    warnings: list[str] = []

    @field_validator("event_time", "observed_at", mode="before")
    @classmethod
    def _dt(cls, value: Any) -> datetime:
        return parse_utc(value)

    @model_validator(mode="after")
    def _validate_teams(self) -> "CanonicalFixtureObservation":
        if self.home_team_external_id == self.away_team_external_id:
            raise ValueError("home and away teams must be distinct")
        return self


class CanonicalOddsObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_key: str
    external_fixture_id: str
    bookmaker_external_id: str | None = None
    bookmaker_name: str
    market_key: str
    selection_key: str
    line_value: Decimal | None = None
    decimal_odds: Decimal
    original_odds: str
    original_format: str = "decimal"
    status: str = "active"
    provider_timestamp: datetime | None = None
    observed_at: datetime
    raw_payload_id: str | None = None
    warnings: list[str] = []

    @field_validator("observed_at", mode="before")
    @classmethod
    def _observed(cls, value: Any) -> datetime:
        return parse_utc(value, "observed_at")

    @field_validator("provider_timestamp", mode="before")
    @classmethod
    def _provider_ts(cls, value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        return parse_utc(value, "provider_timestamp")

    @field_validator("decimal_odds", mode="before")
    @classmethod
    def _odds(cls, value: Any) -> Decimal:
        odds = Decimal(str(value))
        if odds <= Decimal("1"):
            raise ValueError("decimal_odds must be > 1")
        return odds

    @model_validator(mode="after")
    def _market_selection(self) -> "CanonicalOddsObservation":
        if self.market_key not in KNOWN_MARKETS:
            raise ValueError(f"unknown market_key: {self.market_key}")
        allowed = SELECTIONS_BY_MARKET[self.market_key]
        if self.selection_key not in allowed:
            raise ValueError(f"selection {self.selection_key} incompatible with {self.market_key}")
        if self.market_key == "total_goals" and self.line_value is None:
            raise ValueError("total_goals requires line_value")
        return self


class NormalizationReport(BaseModel):
    provider_key: str
    endpoint: str
    fixtures: list[CanonicalFixtureObservation] = []
    odds: list[CanonicalOddsObservation] = []
    errors: list[str] = []
    warnings: list[str] = []

