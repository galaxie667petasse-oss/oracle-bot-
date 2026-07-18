from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


SCHEMA_VERSION = "1.0"
VERDICTS = {"STRONG_SUPPORT", "SUPPORT", "NEUTRAL", "OPPOSE", "STRONG_OPPOSE", "INSUFFICIENT_DATA", "ERROR"}
JUDGE_RECOMMENDATIONS = {"ACCEPT_SHADOW", "WATCH", "REJECT", "INSUFFICIENT_DATA", "ERROR"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LLMUsage(StrictModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    estimated_cost_usd: Decimal = Decimal("0")


class StructuredRequest(StrictModel):
    request_id: str
    candidate_id: str
    fixture_id: str
    tier: str
    panel_or_agent: str
    model: str
    reasoning_effort: str
    schema_name: str
    prompt_version: str
    packet_hash: str
    input_payload: dict[str, Any]
    allow_paid: bool = False
    max_output_tokens: int = 1200


class StructuredResponse(StrictModel):
    request_id: str
    provider: str
    requested_model: str
    used_model: str
    status: str
    output: dict[str, Any]
    usage: LLMUsage = Field(default_factory=LLMUsage)
    response_id: str | None = None
    latency_ms: int = 0
    cache_status: str = "miss"
    error_message: str = ""


class AgentFinding(StrictModel):
    schema_version: str = SCHEMA_VERSION
    agent_id: str
    candidate_id: str
    fixture_id: str
    market_key: str
    selection_key: str
    verdict: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str]
    risks: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    veto: bool = False
    veto_code: str | None = None
    summary: str

    @field_validator("verdict")
    @classmethod
    def _valid_verdict(cls, value: str) -> str:
        if value not in VERDICTS:
            raise ValueError("verdict invalide")
        return value

    @field_validator("summary")
    @classmethod
    def _no_probability_rewrite(cls, value: str) -> str:
        forbidden = ("new probability", "adjusted probability", "stake", "mise")
        if any(token in value.lower() for token in forbidden):
            raise ValueError("finding must not alter deterministic calculations")
        return value


class PanelResult(StrictModel):
    schema_version: str = SCHEMA_VERSION
    panel_id: str
    candidate_id: str
    fixture_id: str
    findings: list[AgentFinding]


class FinalJudgeReview(StrictModel):
    schema_version: str = SCHEMA_VERSION
    candidate_id: str
    fixture_id: str
    recommendation: str
    review_confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    opposing_evidence_ids: list[str] = Field(default_factory=list)
    acknowledged_vetoes: list[str] = Field(default_factory=list)
    key_supporting_factors: list[str] = Field(default_factory=list)
    key_counterarguments: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    unresolved_contradictions: list[str] = Field(default_factory=list)
    material_change_triggers: list[str] = Field(default_factory=list)
    summary: str

    @field_validator("recommendation")
    @classmethod
    def _valid_recommendation(cls, value: str) -> str:
        if value not in JUDGE_RECOMMENDATIONS:
            raise ValueError("recommendation invalide")
        return value

    @field_validator("key_supporting_factors", "key_counterarguments", mode="before")
    @classmethod
    def _forbid_numbers_as_claims(cls, value):
        text = " ".join(value or []) if isinstance(value, list) else str(value)
        forbidden = ("p_model", "probability=", "ev=", "stake", "kelly", "bankroll")
        if any(token in text.lower() for token in forbidden):
            raise ValueError("judge cannot modify or restate calculation fields as new facts")
        return value


class LLMProvider(Protocol):
    async def generate_structured(self, request: StructuredRequest) -> StructuredResponse:
        ...

    async def generate_with_tools(self, request: StructuredRequest) -> StructuredResponse:
        ...

    async def health_check(self) -> dict[str, Any]:
        ...


def utc_iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")
