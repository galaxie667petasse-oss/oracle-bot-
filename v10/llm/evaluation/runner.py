from __future__ import annotations

from decimal import Decimal

from v10.llm.budgets.manager import BudgetManager
from v10.llm.config import LLMRuntimeConfig
from v10.llm.orchestrator import LLMOrchestrator
from v10.llm.providers.mock import MockLLMProvider

from .dataset import default_eval_cases
from .metrics import summarize_llm_results


async def run_mock_evaluation(scenario: str = "valid") -> dict:
    config = LLMRuntimeConfig()
    provider = MockLLMProvider(scenario=scenario)
    orchestrator = LLMOrchestrator(config, provider, BudgetManager(Decimal("0"), Decimal("0"), Decimal("0")))
    results = []
    for item in default_eval_cases():
        results.append(await orchestrator.analyze_candidate(item["candidate"], item["as_of"], top_finalist=True))
    return {"scenario": scenario, "results": results, "metrics": summarize_llm_results(results), "paid_calls": False}
