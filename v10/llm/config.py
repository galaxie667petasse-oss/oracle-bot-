from __future__ import annotations

from decimal import Decimal
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from v10.config import V10Settings


class LLMRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    shadow_only: bool = True
    allow_paid_calls: bool = False
    require_cli_allow_paid: bool = True
    daily_budget_usd: Decimal = Decimal("0")
    scan_budget_usd: Decimal = Decimal("0")
    fixture_budget_usd: Decimal = Decimal("0")
    model_fast: str = "gpt-5.6-luna"
    model_specialist: str = "gpt-5.6-terra"
    model_final: str = "gpt-5.6-sol"
    reasoning_fast: str = "low"
    reasoning_specialist: str = "medium"
    reasoning_final: str = "high"
    max_concurrency: int = 3
    max_agent_rounds: int = 2
    max_tool_calls_per_agent: int = 4
    max_calls_per_fixture: int = 6
    max_calls_per_scan: int = 30
    max_candidates_per_scan: int = 10
    max_finalists_per_scan: int = 3
    max_sol_calls_per_scan: int = 2
    max_sol_calls_per_fixture: int = 1
    allow_xhigh: bool = False
    allow_max: bool = False
    allow_pro: bool = False

    @model_validator(mode="after")
    def _closed_by_default(self) -> "LLMRuntimeConfig":
        if self.allow_paid_calls and not self.enabled:
            raise ValueError("paid calls require LLM_ENABLED=true")
        if self.allow_paid_calls and self.daily_budget_usd <= 0:
            raise ValueError("paid calls require positive daily budget")
        for effort in (self.reasoning_fast, self.reasoning_specialist, self.reasoning_final):
            if effort == "xhigh" and not self.allow_xhigh:
                raise ValueError("xhigh reasoning requires OPENAI_ALLOW_XHIGH=true")
            if effort == "max" and not self.allow_max:
                raise ValueError("max reasoning requires OPENAI_ALLOW_MAX=true")
        return self

    @classmethod
    def from_settings(cls, settings: V10Settings) -> "LLMRuntimeConfig":
        return cls(
            enabled=settings.llm_enabled,
            shadow_only=settings.llm_shadow_only,
            allow_paid_calls=settings.llm_allow_paid_calls,
            daily_budget_usd=Decimal(str(settings.openai_daily_budget_usd)),
            scan_budget_usd=Decimal(str(settings.openai_scan_budget_usd)),
            fixture_budget_usd=Decimal(str(settings.openai_fixture_budget_usd)),
            model_fast=settings.openai_model_fast or "gpt-5.6-luna",
            model_specialist=settings.openai_model_specialist or "gpt-5.6-terra",
            model_final=settings.openai_model_final or "gpt-5.6-sol",
            reasoning_fast=settings.openai_reasoning_fast,
            reasoning_specialist=settings.openai_reasoning_specialist,
            reasoning_final=settings.openai_reasoning_final,
            max_concurrency=settings.openai_max_concurrency,
            max_agent_rounds=settings.openai_max_agent_rounds,
            max_tool_calls_per_agent=settings.openai_max_tool_calls_per_agent,
            max_calls_per_fixture=settings.openai_max_calls_per_fixture or 6,
            max_calls_per_scan=settings.openai_max_calls_per_scan,
            max_candidates_per_scan=settings.openai_max_candidates_per_scan,
            max_finalists_per_scan=settings.openai_max_finalists_per_scan or 3,
            max_sol_calls_per_scan=settings.openai_max_sol_calls_per_scan,
            max_sol_calls_per_fixture=settings.openai_max_sol_calls_per_fixture,
            allow_xhigh=settings.openai_allow_xhigh,
            allow_max=settings.openai_allow_max,
            allow_pro=settings.openai_allow_pro,
        )

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "LLMRuntimeConfig":
        settings = V10Settings(**{key: value for key, value in env.items()})
        return cls.from_settings(settings)

    def can_call_paid(self, allow_paid_cli: bool = False) -> bool:
        return (
            self.enabled
            and self.allow_paid_calls
            and self.daily_budget_usd > 0
            and (allow_paid_cli or not self.require_cli_allow_paid)
        )

    def safe_report(self) -> dict:
        return {
            "enabled": self.enabled,
            "shadow_only": self.shadow_only,
            "allow_paid_calls": self.allow_paid_calls,
            "daily_budget_usd": str(self.daily_budget_usd),
            "scan_budget_usd": str(self.scan_budget_usd),
            "fixture_budget_usd": str(self.fixture_budget_usd),
            "models": {"FAST": self.model_fast, "SPECIALIST": self.model_specialist, "FINAL": self.model_final},
            "reasoning": {"FAST": self.reasoning_fast, "SPECIALIST": self.reasoning_specialist, "FINAL": self.reasoning_final},
            "limits": {
                "max_calls_per_scan": self.max_calls_per_scan,
                "max_calls_per_fixture": self.max_calls_per_fixture,
                "max_finalists_per_scan": self.max_finalists_per_scan,
                "max_sol_calls_per_scan": self.max_sol_calls_per_scan,
            },
            "lab_only": True,
            "can_influence_picks": False,
        }
