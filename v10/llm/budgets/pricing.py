from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ModelPrice:
    model_name: str
    input_per_million_usd: Decimal
    output_per_million_usd: Decimal
    cached_input_per_million_usd: Decimal = Decimal("0")
    cache_write_multiplier: Decimal = Decimal("1.25")
    pricing_version: str = "openai_short_context_2026_07_19"
    source_url: str = "https://developers.openai.com/api/docs/pricing"

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
            # Short-context prices verified against the OpenAI pricing page on 2026-07-19.
            # Runtime pricing still fails closed when a model is absent from this table.
            "gpt-5.6-luna": ModelPrice("gpt-5.6-luna", Decimal("1.00"), Decimal("6.00"), Decimal("0.10")),
            "gpt-5.6-terra": ModelPrice("gpt-5.6-terra", Decimal("2.50"), Decimal("15.00"), Decimal("0.25")),
            "gpt-5.6-sol": ModelPrice("gpt-5.6-sol", Decimal("5.00"), Decimal("30.00"), Decimal("0.50")),
        }

    def require(self, model_name: str) -> ModelPrice:
        if model_name not in self.prices:
            raise ValueError(f"prix modele inconnu: {model_name}")
        return self.prices[model_name]

    def estimate(self, model_name: str, input_tokens: int, output_tokens: int, cached_input_tokens: int = 0) -> Decimal:
        return self.require(model_name).estimate(input_tokens, output_tokens, cached_input_tokens)

    def to_dict(self) -> dict:
        return {
            key: {
                **value.__dict__,
                "input_per_million_usd": str(value.input_per_million_usd),
                "output_per_million_usd": str(value.output_per_million_usd),
                "cached_input_per_million_usd": str(value.cached_input_per_million_usd),
                "cache_write_multiplier": str(value.cache_write_multiplier),
            }
            for key, value in self.prices.items()
        }
