from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from v10.time import parse_utc


EVIDENCE_TYPES = {
    "MODEL_PREDICTION",
    "MARKET_SNAPSHOT",
    "ODDS_HISTORY",
    "DATA_QUALITY",
    "FEATURE_SNAPSHOT",
    "SCORE_DISTRIBUTION",
    "TEAM_FORM",
    "SCHEDULE",
    "SQUAD_AVAILABILITY",
    "LINEUP",
    "COMPETITION_CONTEXT",
    "PORTFOLIO_EXPOSURE",
    "DETERMINISTIC_FILTER",
}


def stable_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(default_factory=lambda: str(uuid4()))
    candidate_id: str
    fixture_id: str
    type: str
    source_reference: str
    observed_at: datetime
    effective_at: datetime
    valid_as_of: bool
    reliability: float = Field(ge=0.0, le=1.0)
    content_hash: str = ""
    content: dict[str, Any]

    @field_validator("type")
    @classmethod
    def _known_type(cls, value: str) -> str:
        if value not in EVIDENCE_TYPES:
            raise ValueError("unknown evidence type")
        return value

    @field_validator("observed_at", "effective_at", mode="before")
    @classmethod
    def _utc(cls, value):
        return parse_utc(value) if isinstance(value, str) else value

    def model_post_init(self, __context) -> None:
        if not self.content_hash:
            self.content_hash = stable_hash(self.content)


class CandidateEvidencePacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    fixture_id: str
    market_key: str
    selection_key: str
    decision_as_of: datetime
    deterministic_status: str
    deterministic_reasons: list[str] = Field(default_factory=list)
    probabilities: dict[str, Any]
    market: dict[str, Any]
    quality: dict[str, Any]
    uncertainty: dict[str, Any]
    missing_information: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem]
    packet_hash: str = ""

    @field_validator("decision_as_of", mode="before")
    @classmethod
    def _utc(cls, value):
        return parse_utc(value) if isinstance(value, str) else value

    def model_post_init(self, __context) -> None:
        if not self.packet_hash:
            payload = self.model_dump(mode="json", exclude={"packet_hash"})
            self.packet_hash = stable_hash(payload)

    def evidence_ids(self) -> set[str]:
        return {item.evidence_id for item in self.evidence}
