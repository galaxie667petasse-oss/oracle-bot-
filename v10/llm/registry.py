from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .config import LLMRuntimeConfig


@dataclass(frozen=True)
class ModelRoute:
    tier: str
    model: str
    reasoning_effort: str
    mode: str = "standard"


class LLMModelRegistry:
    """Logical model registry. It does not call OpenAI by itself."""

    official_docs_checked = {
        "responses_api": "https://platform.openai.com/docs/api-reference/responses",
        "models": "https://platform.openai.com/docs/models",
        "structured_outputs": "https://platform.openai.com/docs/guides/structured-outputs",
    }

    def __init__(self, config: LLMRuntimeConfig):
        self.config = config

    def route(self, tier: str) -> ModelRoute:
        upper = tier.upper()
        if upper == "FAST":
            return ModelRoute("FAST", self.config.model_fast, self.config.reasoning_fast)
        if upper == "SPECIALIST":
            return ModelRoute("SPECIALIST", self.config.model_specialist, self.config.reasoning_specialist)
        if upper == "FINAL":
            return ModelRoute("FINAL", self.config.model_final, self.config.reasoning_final)
        raise ValueError(f"unknown logical tier: {tier}")

    def all_routes(self) -> list[ModelRoute]:
        return [self.route("FAST"), self.route("SPECIALIST"), self.route("FINAL")]

    def fallback_chain(self, tier: str) -> list[ModelRoute]:
        upper = tier.upper()
        if upper == "FINAL":
            return [self.route("FINAL"), self.route("SPECIALIST"), self.route("FAST")]
        if upper == "SPECIALIST":
            return [self.route("SPECIALIST"), self.route("FAST")]
        return [self.route("FAST")]

    def availability_report(self, available_models: Iterable[str] | None = None) -> dict:
        available = set(available_models or [])
        routes = self.all_routes()
        return {
            "routes": [route.__dict__ for route in routes],
            "availability": {
                route.tier: ("UNKNOWN_NOT_CHECKED" if not available else ("AVAILABLE" if route.model in available else "UNAVAILABLE"))
                for route in routes
            },
            "fallback_policy": {
                "FINAL": ["FINAL", "SPECIALIST", "FAST"],
                "SPECIALIST": ["SPECIALIST", "FAST"],
                "FAST": ["FAST"],
            },
            "degraded_model_status": "DEGRADED_MODEL",
            "no_model_status": "UNREVIEWED",
            "official_docs_checked": self.official_docs_checked,
        }
