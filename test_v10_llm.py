import asyncio
import json
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from v10.config import load_settings
from v10.db.migrations import downgrade_base, migration_status, upgrade_head
from v10.llm.budgets.manager import BudgetManager
from v10.llm.cache.keys import llm_cache_key
from v10.llm.cache.repository import InMemoryLLMCache
from v10.llm.config import LLMRuntimeConfig
from v10.llm.contracts import AgentFinding, FinalJudgeReview
from v10.llm.agents.panels import build_panel_request
from v10.llm.evidence.models import EvidenceItem
from v10.llm.evidence.packet_builder import CandidateEvidencePacketBuilder
from v10.llm.evidence.semantic_validator import SemanticValidator
from v10.llm.evaluation.dataset import synthetic_candidate
from v10.llm.orchestrator import LLMOrchestrator
from v10.llm.providers.mock import MockLLMProvider
from v10.llm.providers.openai_responses import OpenAIResponsesProvider
from v10.llm.providers.replay import ReplayLLMProvider
from v10.llm.registry import LLMModelRegistry
from v10.llm.routing import ComplexityRouter


def make_packet(case_id="shadow_accept"):
    return CandidateEvidencePacketBuilder().build(synthetic_candidate(case_id), datetime(2026, 7, 19, tzinfo=UTC))


def test_config_closed_by_default_and_paid_requires_flags():
    config = LLMRuntimeConfig()
    assert config.enabled is False
    assert config.shadow_only is True
    assert config.allow_paid_calls is False
    assert config.can_call_paid(True) is False
    try:
        LLMRuntimeConfig(enabled=False, allow_paid_calls=True, daily_budget_usd=Decimal("1"))
    except ValueError:
        pass
    else:
        raise AssertionError("paid calls accepted without LLM enabled")
    try:
        LLMRuntimeConfig(enabled=True, allow_paid_calls=True, daily_budget_usd=Decimal("0"))
    except ValueError:
        pass
    else:
        raise AssertionError("paid calls accepted without budget")
    settings = load_settings({"LLM_ENABLED": "false", "LLM_ALLOW_PAID_CALLS": "false", "OPENAI_DAILY_BUDGET_USD": "0"})
    assert settings.safe_report()["llm"]["allow_paid_calls"] is False


def test_registry_routing_and_luna_batching():
    registry = LLMModelRegistry(LLMRuntimeConfig())
    assert registry.route("FAST").model == "gpt-5.6-luna"
    assert registry.route("SPECIALIST").reasoning_effort == "medium"
    assert registry.route("FINAL").reasoning_effort == "high"
    packet = make_packet("valid")
    plan = ComplexityRouter().plan(packet)
    assert plan.run_luna is True
    assert plan.luna_batchable is True
    assert "fresh_information_no_evidence" in plan.skipped_agents


def test_budget_reservation_and_fail_closed():
    manager = BudgetManager(Decimal("0.10"), Decimal("0.10"), Decimal("0.10"))
    estimate = manager.estimate("gpt-5.6-luna", 1000, 200)
    reservation = manager.reserve("scan:test", "gpt-5.6-luna", estimate)
    assert manager.reserved_usd == estimate
    manager.reconcile(reservation.reservation_id, Decimal("0.0001"))
    assert manager.spent_usd == Decimal("0.0001")
    zero = BudgetManager(Decimal("0"), Decimal("0"), Decimal("0"))
    try:
        zero.reserve("scan:test", "gpt-5.6-luna", Decimal("0.01"))
    except ValueError as exc:
        assert "budget_zero" in str(exc)
    else:
        raise AssertionError("zero budget accepted")


def test_cache_key_and_invalidation():
    key1 = llm_cache_key("mock", "gpt-5.6-luna", "low", "v1", "agent", "luna", "hash-a")
    key2 = llm_cache_key("mock", "gpt-5.6-luna", "low", "v1", "agent", "luna", "hash-b")
    assert key1 != key2
    cache = InMemoryLLMCache()
    cache.put(key1, {"ok": True}, "hash-a")
    assert cache.get(key1)["ok"] is True
    assert cache.invalidate_packet("hash-a") == 1


def test_evidence_semantic_validator_rejects_future_and_cross_fixture():
    packet = make_packet("valid")
    valid_id = next(iter(packet.evidence_ids()))
    finding = AgentFinding(
        agent_id="statistical_model_auditor",
        candidate_id=packet.candidate_id,
        fixture_id=packet.fixture_id,
        market_key=packet.market_key,
        selection_key=packet.selection_key,
        verdict="SUPPORT",
        confidence=0.5,
        evidence_ids=[valid_id],
        summary="preuve valide",
    )
    assert SemanticValidator(packet).validate_finding(finding).ok
    bad = finding.model_copy(update={"fixture_id": "other"})
    assert not SemanticValidator(packet).validate_finding(bad).ok
    future = EvidenceItem(
        candidate_id=packet.candidate_id,
        fixture_id=packet.fixture_id,
        type="MODEL_PREDICTION",
        source_reference="future",
        observed_at=packet.decision_as_of + timedelta(hours=1),
        effective_at=packet.decision_as_of + timedelta(hours=1),
        valid_as_of=True,
        reliability=1.0,
        content={},
    )
    packet.evidence.append(future)
    future_finding = finding.model_copy(update={"evidence_ids": [future.evidence_id]})
    assert "evidence_future_observed_at" in SemanticValidator(packet).validate_finding(future_finding)["errors"]


def test_strict_outputs_reject_extra_and_judge_numeric_rewrite():
    payload = {
        "agent_id": "market_pricing_analyst",
        "candidate_id": "c",
        "fixture_id": "f",
        "market_key": "match_winner",
        "selection_key": "home",
        "verdict": "SUPPORT",
        "confidence": 0.5,
        "evidence_ids": [],
        "summary": "ok",
        "extra": "nope",
    }
    try:
        AgentFinding(**payload)
    except Exception:
        pass
    else:
        raise AssertionError("extra field accepted")
    try:
        FinalJudgeReview(
            candidate_id="c",
            fixture_id="f",
            recommendation="ACCEPT_SHADOW",
            review_confidence=0.5,
            key_supporting_factors=["p_model=0.9"],
            summary="bad",
        )
    except Exception:
        pass
    else:
        raise AssertionError("judge altered calculations")


def test_orchestrator_mock_veto_stops_cascade_and_invented_evidence_blocks():
    async def run():
        packet = make_packet("shadow_accept")
        vetoed = await LLMOrchestrator(LLMRuntimeConfig(), MockLLMProvider("veto")).analyze_packet(packet, top_finalist=True)
        assert len(vetoed["calls"]) == 1
        assert vetoed["decision"]["final_status"] == "NO_BET"
        invented = await LLMOrchestrator(LLMRuntimeConfig(), MockLLMProvider("invented_evidence")).analyze_packet(packet, top_finalist=True)
        assert invented["decision"]["final_status"] == "NO_BET"
        assert "semantic_validation_failed" in invented["contradictions"]["hard_vetoes"]

    asyncio.run(run())


def test_replay_provider_and_openai_provider_blocked_without_flags():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "replay.json"
        path.write_text(json.dumps({"schema_version": "1.0", "agent_id": "luna_triage", "candidate_id": "cand_valid", "fixture_id": "fixture_001", "market_key": "match_winner", "selection_key": "home", "verdict": "SUPPORT", "confidence": 0.5, "evidence_ids": [], "summary": "ok"}), encoding="utf-8")
        provider = ReplayLLMProvider(str(path))
        request = LLMOrchestrator(LLMRuntimeConfig(), MockLLMProvider()).registry.route("FAST")
        assert request.model == "gpt-5.6-luna"
    blocked = OpenAIResponsesProvider(LLMRuntimeConfig(), api_key="fake")
    try:
        asyncio.run(blocked.generate_structured(build_panel_request(make_packet("valid"), "luna_triage", "FAST", LLMModelRegistry(LLMRuntimeConfig()))))
    except PermissionError:
        pass
    else:
        raise AssertionError("OpenAI provider allowed paid call without flags")


def test_cli_llm_and_demo_no_paid_calls():
    doctor = json.loads(subprocess.check_output([sys.executable, "app.py", "llm", "doctor"], text=True))
    assert doctor["enabled"] is False
    assert doctor["paid_call_possible_without_allow_paid"] is False
    demo = json.loads(subprocess.check_output([sys.executable, "app.py", "demo", "llm-shadow-end-to-end", "--mock", "--json"], text=True))
    statuses = [row["decision"]["final_status"] for row in demo["scenarios"]]
    assert statuses == ["NO_BET", "NO_BET", "INSUFFICIENT_DATA", "SHADOW_ACCEPTED"]
    assert demo["paid_calls"] is False
    assert demo["telegram_sent"] is False


def test_migration_head_includes_llm_schema():
    from v10.config import V10Settings

    with tempfile.TemporaryDirectory() as tmp:
        settings = V10Settings(DATABASE_URL=f"sqlite:///{Path(tmp, 'llm.sqlite').as_posix()}")
        assert upgrade_head(settings)["up_to_date"] is True
        assert migration_status(settings)["current_revision"] == "20260719_0004"
        assert downgrade_base(settings)["current_revision"] is None


def main():
    test_config_closed_by_default_and_paid_requires_flags()
    test_registry_routing_and_luna_batching()
    test_budget_reservation_and_fail_closed()
    test_cache_key_and_invalidation()
    test_evidence_semantic_validator_rejects_future_and_cross_fixture()
    test_strict_outputs_reject_extra_and_judge_numeric_rewrite()
    test_orchestrator_mock_veto_stops_cascade_and_invented_evidence_blocks()
    test_replay_provider_and_openai_provider_blocked_without_flags()
    test_cli_llm_and_demo_no_paid_calls()
    test_migration_head_includes_llm_schema()
    print("test_v10_llm ok")


if __name__ == "__main__":
    main()
