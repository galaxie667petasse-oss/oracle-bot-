from __future__ import annotations

from datetime import UTC, datetime

from v10.llm.budgets.manager import BudgetManager
from v10.llm.config import LLMRuntimeConfig
from v10.llm.evaluation.dataset import synthetic_candidate
from v10.llm.orchestrator import LLMOrchestrator
from v10.llm.providers.mock import MockLLMProvider


async def run_llm_shadow_demo() -> dict:
    config = LLMRuntimeConfig()
    scenarios = [
        ("deterministic_reject", "valid"),
        ("hard_veto", "veto"),
        ("insufficient", "insufficient"),
        ("shadow_accept", "valid"),
    ]
    results = []
    as_of = datetime(2026, 7, 19, 12, tzinfo=UTC)
    for case_id, mock_scenario in scenarios:
        orchestrator = LLMOrchestrator(config, MockLLMProvider(mock_scenario), BudgetManager(config.daily_budget_usd, config.scan_budget_usd, config.fixture_budget_usd))
        result = await orchestrator.analyze_candidate(synthetic_candidate(case_id), as_of, allow_paid=False, portfolio_candidate_count=2, top_finalist=True)
        result["scenario"] = case_id
        result["mock_scenario"] = mock_scenario
        results.append(result)
    return {
        "demo": "llm_shadow_end_to_end_mock",
        "scenarios": results,
        "paid_calls": False,
        "telegram_sent": False,
        "bookmaker_action": False,
        "paper_only": True,
        "lab_only": True,
        "can_influence_picks": False,
    }
