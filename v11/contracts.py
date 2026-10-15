from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from v10.time import ensure_utc
from v11.markets import validate


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    @field_validator("*", mode="after")
    @classmethod
    def aware_dates(cls, value):
        if isinstance(value, datetime):
            return ensure_utc(value)
        return value


class Quote(StrictRecord):
    source: str = Field(min_length=1)
    bookmaker: str = Field(min_length=1)
    market: str
    selection: str
    odds: float = Field(gt=1)
    line: float | None = None
    observed_at: datetime
    provider_updated_at: datetime | None = None

    @model_validator(mode="after")
    def market_selection(self):
        validate(self.market, self.selection, self.line)
        if self.provider_updated_at and self.provider_updated_at > self.observed_at:
            raise ValueError("provider timestamp after observation")
        return self


class HistoryMatch(StrictRecord):
    match_id: str
    competition: str
    home: str
    away: str
    kickoff: datetime
    result_observed_at: datetime
    home_goals: int = Field(ge=0, strict=True)
    away_goals: int = Field(ge=0, strict=True)

    @model_validator(mode="after")
    def valid_result(self):
        if self.result_observed_at <= self.kickoff or self.home == self.away:
            raise ValueError("finished result must be observed after kickoff with distinct teams")
        return self


class Fixture(StrictRecord):
    fixture_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    competition: str
    home: str
    away: str
    kickoff: datetime
    observed_at: datetime
    status: str = "SCHEDULED"
    quotes: list[Quote] = Field(default_factory=list, max_length=2000)

    @model_validator(mode="after")
    def teams(self):
        if not self.home or not self.away or self.home == self.away:
            raise ValueError("distinct named teams required")
        keys = [(q.source, q.bookmaker, q.market, q.selection, q.line) for q in self.quotes]
        if len(keys) != len(set(keys)):
            raise ValueError("ambiguous duplicate quote in snapshot")
        return self


class Snapshot(StrictRecord):
    captured_at: datetime
    provenance: Literal["real_provider", "manual", "synthetic"]
    fixtures: list[Fixture] = Field(default_factory=list, max_length=500)
    history: list[HistoryMatch] = Field(default_factory=list, max_length=50000)

    @model_validator(mode="after")
    def timestamps_and_ids(self):
        ids = [f.fixture_id for f in self.fixtures]
        history_ids = [m.match_id for m in self.history]
        if len(ids) != len(set(ids)) or len(history_ids) != len(set(history_ids)):
            raise ValueError("duplicate fixture or history id")
        for f in self.fixtures:
            if f.observed_at > self.captured_at or any(q.observed_at > self.captured_at for q in f.quotes):
                raise ValueError("observation after snapshot")
        if any(m.result_observed_at > self.captured_at for m in self.history):
            raise ValueError("history result after snapshot")
        return self
