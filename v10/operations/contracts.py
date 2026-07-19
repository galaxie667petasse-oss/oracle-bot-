from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from v10.time import ensure_utc


class JobType(StrEnum):
    DISCOVER_FIXTURES = "DISCOVER_FIXTURES"
    REFRESH_FIXTURE = "REFRESH_FIXTURE"
    REFRESH_ODDS = "REFRESH_ODDS"
    REFRESH_TEAM_STATISTICS = "REFRESH_TEAM_STATISTICS"
    REFRESH_STANDINGS = "REFRESH_STANDINGS"
    REFRESH_AVAILABILITY = "REFRESH_AVAILABILITY"
    REFRESH_LINEUPS = "REFRESH_LINEUPS"
    REFRESH_CONTEXT = "REFRESH_CONTEXT"
    BUILD_FEATURES = "BUILD_FEATURES"
    GENERATE_PREDICTIONS = "GENERATE_PREDICTIONS"
    GENERATE_CANDIDATES = "GENERATE_CANDIDATES"
    RUN_LLM_SHADOW_REVIEW = "RUN_LLM_SHADOW_REVIEW"
    CAPTURE_NEAR_CLOSE_ODDS = "CAPTURE_NEAR_CLOSE_ODDS"
    REFRESH_RESULTS = "REFRESH_RESULTS"
    SETTLE_SIGNALS = "SETTLE_SIGNALS"
    RECONCILE_RESULTS = "RECONCILE_RESULTS"
    CALCULATE_CLV = "CALCULATE_CLV"
    GENERATE_DAILY_REPORT = "GENERATE_DAILY_REPORT"
    GENERATE_WEEKLY_REPORT = "GENERATE_WEEKLY_REPORT"
    RUN_STATISTICAL_EVALUATION = "RUN_STATISTICAL_EVALUATION"
    RUN_LLM_EVALUATION_BATCH = "RUN_LLM_EVALUATION_BATCH"
    CLEANUP_EXPIRED_JOBS = "CLEANUP_EXPIRED_JOBS"


class JobStatus(StrEnum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    RETRY = "RETRY"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class PrematchPhase(StrEnum):
    FAR = "FAR"
    T72 = "T72"
    T24 = "T24"
    T6 = "T6"
    T90 = "T90"
    T30 = "T30"
    T10 = "T10"
    NEAR_CLOSE = "NEAR_CLOSE"
    RESULT_CHECK = "RESULT_CHECK"
    RECONCILIATION = "RECONCILIATION"


@dataclass(frozen=True)
class ScheduledJobSpec:
    job_type: JobType
    due_at: datetime
    fixture_id: str | None = None
    candidate_id: str | None = None
    provider_key: str | None = None
    priority: int = 100
    phase: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    max_attempts: int = 3

    def __post_init__(self) -> None:
        ensure_utc(self.due_at, "due_at")

    @property
    def idempotency_key(self) -> str:
        fixture = self.fixture_id or "global"
        candidate = self.candidate_id or "none"
        provider = self.provider_key or "any"
        return f"{self.job_type.value}:{fixture}:{candidate}:{provider}:{self.due_at.isoformat()}:{self.phase}"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["job_type"] = self.job_type.value
        payload["due_at"] = self.due_at.isoformat()
        payload["idempotency_key"] = self.idempotency_key
        return payload


@dataclass(frozen=True)
class JobExecutionResult:
    status: JobStatus
    summary: dict[str, Any]
    retry_reason: str = ""
    error_code: str = ""
    error_summary: str = ""

