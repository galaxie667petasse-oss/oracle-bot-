from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ModelPrice:
    model_name: str
    input_per_million_usd: Decimal
    output_per_million_usd: Decimal
    cached_input_per_million_usd: Decimal = Decimal("0")
    pricing_version: str = "manual_v1"
    source_url: str = "docs/LLM_BUDGETS.md"

    def estimate(self, input_tokens: int, output_tokens: int, cached_input_tokens: int = 0) -> Decimal:
        uncached = max(input_tokens - cached_input_tokens, 0)
        cost = (
            Decimal(uncached) * self.input_per_million_usd
            + Decimal(output_tokens) * self.output_per_million_usd
            + Decimal(cached_input_tokens) * self.cached_input_per_million_usd
        ) / Decimal(1_000_000)
        return cost.quantize(Decimal("0.00000001"))


class PricingTable:
    def __init__(self, prices: dict[str, ModelPrice] | None = None):
        self.prices = prices or {
            # Placeholder prices are intentionally conservative and documented as configurable.
            "gpt-5.6-luna": ModelPrice("gpt-5.6-luna", Decimal("0.15"), Decimal("0.60")),
            "gpt-5.6-terra": ModelPrice("gpt-5.6-terra", Decimal("1.00"), Decimal("4.00")),
            "gpt-5.6-sol": ModelPrice("gpt-5.6-sol", Decimal("5.00"), Decimal("20.00")),
        }

    def require(self, model_name: str) -> ModelPrice:
        if model_name not in self.prices:
            raise ValueError(f"prix modele inconnu: {model_name}")
        return self.prices[model_name]

    def estimate(self, model_name: str, input_tokens: int, output_tokens: int, cached_input_tokens: int = 0) -> Decimal:
        return self.require(model_name).estimate(input_tokens, output_tokens, cached_input_tokens)

    def to_dict(self) -> dict:
        return {key: {**value.__dict__, "input_per_million_usd": str(value.input_per_million_usd), "output_per_million_usd": str(value.output_per_million_usd), "cached_input_per_million_usd": str(value.cached_input_per_million_usd)} for key, value in self.prices.items()}
