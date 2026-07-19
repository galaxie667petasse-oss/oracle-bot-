from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from v10.candidates import CandidateThresholds, evaluate_candidate
from v10.llm.budgets.manager import BudgetManager
from v10.llm.config import LLMRuntimeConfig
from v10.llm.evidence.packet_builder import CandidateEvidencePacketBuilder
from v10.llm.evaluation.dataset import synthetic_candidate
from v10.llm.orchestrator import LLMOrchestrator
from v10.llm.providers.mock import MockLLMProvider
from v10.odds import proportional_no_vig
from v10.settlement import settle_market
from v10.time import ensure_utc, utc_now

from .closing import select_near_close
from .experiments import DEFAULT_EXPERIMENT_KEY, ShadowExperimentRepository
from .freshness import PrematchFreshnessPolicy
from .material_changes import MaterialChangeDetector
from .providers import MockPrematchProvider
from .timeline import generate_prematch_jobs


def deterministic_shadow_decision(candidate: dict[str, Any]) -> dict[str, Any]:
    reasons = list(candidate.get("deterministic_reasons", []))
    market = candidate.get("market", {})
    quality = candidate.get("quality", {})
    if candidate.get("deterministic_status") not in {"ELIGIBLE", "PRELIMINARY"}:
        return {"decision": "NO_BET", "reasons": reasons or ["deterministic_ineligible"], "paper_only": True}
    if not market.get("odds_fresh", True):
        return {"decision": "NO_BET", "reasons": ["odds_stale"], "paper_only": True}
    if float(market.get("expected_value_calibrated", 0) or 0) <= 0:
        return {"decision": "NO_BET", "reasons": ["ev_not_positive"], "paper_only": True}
    if quality.get("status") == "FAIL":
        return {"decision": "NO_BET", "reasons": ["quality_fail"], "paper_only": True}
    return {
        "decision": "SHADOW_ACCEPTED",
        "reasons": ["deterministic_thresholds_passed", "statistical_model_not_validated_for_real_signals"],
        "paper_only": True,
        "real_signal_allowed": False,
    }


class PrematchShadowScanService:
    def __init__(self, provider: MockPrematchProvider | None = None, llm_config: LLMRuntimeConfig | None = None):
        self.provider = provider or MockPrematchProvider()
        self.llm_config = llm_config or LLMRuntimeConfig()

    def build_candidate(self, fixture_id: str, odds: dict[str, float], as_of: datetime) -> dict[str, Any]:
        model_prob = {"home": 0.54, "draw": 0.25, "away": 0.21, "model_versions": ["ensemble_v1"]}
        fair = proportional_no_vig(odds)
        evaluation = evaluate_candidate(
            fixture_id=fixture_id,
            market_key="match_winner",
            selection_key="home",
            decimal_odds=odds["home"],
            p_model=model_prob["home"],
            p_market_fair=fair["home"],
            uncertainty_low=0.50,
            uncertainty_high=0.58,
            data_quality_status="PASS",
            bookmaker_count=3,
            thresholds=CandidateThresholds(min_edge_probability_points=0.02, min_expected_value_per_unit=0.02, max_uncertainty=0.10, min_bookmaker_count=2),
        )
        candidate = synthetic_candidate("shadow_accept")
        candidate.update(
            {
                "candidate_id": f"cand_{fixture_id}_{int(as_of.timestamp())}",
                "fixture_id": fixture_id,
                "probabilities": model_prob,
                "market": {
                    "p_market_fair": fair["home"],
                    "edge_calibrated": evaluation.edge_probability_points,
                    "expected_value_calibrated": evaluation.expected_value_per_unit,
                    "bookmaker_count": 3,
                    "odds_fresh": True,
                    "line_movement_pct": 0.04,
                },
                "quality": {"completeness": 0.84, "status": "PASS", "recent_form_available": True, "schedule_available": True},
                "deterministic_status": "ELIGIBLE" if evaluation.decision == "candidate" else "INELIGIBLE",
                "deterministic_reasons": evaluation.blockers,
            }
        )
        return candidate

    async def run_mock_scan(self, session: Session | None = None, fixture_id: str = "fixture_demo", as_of: datetime | None = None, mock_scenario: str = "valid") -> dict[str, Any]:
        as_of = ensure_utc(as_of or utc_now(), "as_of")
        event_time = as_of + timedelta(hours=24)
        fixture = self.provider.refresh_fixture(fixture_id)
        odds_rows = self.provider.refresh_odds(fixture_id, as_of)
        odds = {"home": 2.20, "draw": 3.40, "away": 3.10}
        freshness = PrematchFreshnessPolicy().evaluate(
            {"fixture": as_of, "odds": as_of, "lineup": None, "availability": None, "team_statistics": as_of, "standings": as_of},
            phase="T24",
            now=as_of,
        )
        candidate = self.build_candidate(fixture_id, odds, as_of)
        packet = CandidateEvidencePacketBuilder().build(candidate, as_of)
        deterministic = deterministic_shadow_decision(candidate)
        llm_result = await LLMOrchestrator(
            self.llm_config,
            MockLLMProvider(mock_scenario),
            BudgetManager(self.llm_config.daily_budget_usd, self.llm_config.scan_budget_usd, self.llm_config.fixture_budget_usd),
        ).analyze_candidate(candidate, as_of, allow_paid=False, portfolio_candidate_count=1, top_finalist=True)
        llm_decision = llm_result.get("decision", {}).get("final_status", "WATCH")
        if session is not None:
            repo = ShadowExperimentRepository(session)
            experiment, _ = repo.get_or_create(DEFAULT_EXPERIMENT_KEY, apply=True)
            if experiment:
                repo.record_decision(experiment.id, candidate["candidate_id"], fixture_id, "deterministic_only", deterministic["decision"], as_of, packet.packet_hash, deterministic)
                repo.record_decision(experiment.id, candidate["candidate_id"], fixture_id, "deterministic_plus_llm", llm_decision, as_of, packet.packet_hash, llm_result, prompt_versions=["sol_shadow_judge_v1"])
        return {
            "fixture": fixture,
            "odds_snapshots": odds_rows,
            "freshness": freshness,
            "candidate": candidate,
            "evidence_packet_hash": packet.packet_hash,
            "deterministic_arm": deterministic,
            "llm_arm": {"decision": llm_decision, "review": llm_result},
            "scan": {
                "fixtures_considered": 1,
                "fixtures_filtered": 0 if candidate["deterministic_status"] == "ELIGIBLE" else 1,
                "candidates_generated": 1,
                "llm_calls": len(llm_result.get("calls", [])),
                "paid_calls": False,
            },
            "paper_only": True,
            "lab_only": True,
            "can_influence_picks": False,
        }


async def operational_shadow_demo_payload() -> dict[str, Any]:
    as_of = datetime(2026, 7, 19, 12, tzinfo=UTC)
    service = PrematchShadowScanService(MockPrematchProvider(base_time=as_of))
    fixture_id = "fixture_demo"
    event_time = as_of + timedelta(hours=24)
    jobs = [job.to_dict() for job in generate_prematch_jobs(fixture_id, event_time)]
    first_scan = await service.run_mock_scan(fixture_id=fixture_id, as_of=as_of, mock_scenario="valid")
    old_state = {"decimal_odds": 2.20, "fair_probability": 0.45, "model_probability": 0.54, "uncertainty": 0.08, "fixture_status": "SCHEDULED", "event_time": event_time.isoformat(), "quality_status": "PASS"}
    material = MaterialChangeDetector().detect(old_state, {**old_state, "decimal_odds": 2.34, "fair_probability": 0.47})
    non_material = MaterialChangeDetector().detect(old_state, {**old_state, "decimal_odds": 2.22, "fair_probability": 0.451})
    lineup_material = MaterialChangeDetector().detect(old_state, {**old_state, "lineup_confirmed": True})
    near_close = select_near_close(event_time, [{"id": "near_close_1", "decimal_odds": "2.18", "observed_at": (event_time - timedelta(minutes=4)).isoformat(), "bookmaker_count": 3}, {"id": "future_rejected", "decimal_odds": "2.30", "observed_at": (event_time + timedelta(seconds=5)).isoformat(), "bookmaker_count": 3}])
    settlement = settle_market("match_winner", "home", Decimal("2.18"), 2, 1, fixture_status="FT")
    clv = {"taken_odds": "2.20", "near_close_odds": str(near_close.decimal_odds), "clv_odds_pct": round(float(Decimal("2.20") / near_close.decimal_odds - Decimal("1")), 6) if near_close.decimal_odds else None}
    scenarios = {
        "fixture_postponed": MaterialChangeDetector().detect(old_state, {**old_state, "fixture_status": "POSTPONED"}),
        "provider_unavailable": {"status": "DEGRADED", "alert_created": True, "network_called": False},
        "quota_nearly_exhausted": {"allowed_optional_refresh": False, "priority": "results_and_finalists_first"},
        "lease_recovered": {"expired": 1, "recovered": 1},
        "duplicate_job": {"first_inserted": 1, "second_ignored": 1},
        "post_kickoff_odds_rejected": {"quality": select_near_close(event_time, [{"decimal_odds": "2.50", "observed_at": (event_time + timedelta(minutes=1)).isoformat()}]).quality},
        "llm_budget_exhausted": {"decision": "WATCH", "paid_calls": False},
        "result_corrected": {"append_only_correction": True},
    }
    return {
        "demo": "operational_shadow_end_to_end",
        "fixture_id": fixture_id,
        "jobs_generated": len(jobs),
        "jobs": jobs,
        "scan": first_scan,
        "material_change": material,
        "non_material_change": non_material,
        "lineup_material_change": lineup_material,
        "near_close": near_close.to_dict(),
        "settlement": settlement.to_dict(),
        "clv": clv,
        "experiment_report": {
            "arms": ["deterministic_only", "deterministic_plus_llm"],
            "same_candidate": True,
            "outcome_hidden_until_after_match": True,
            "bias_warning": "synthetic demo only",
        },
        "scenarios": scenarios,
        "costs": {"simulated_usd": "0.00000000", "real_openai_calls": 0, "batch_uploads": 0},
        "telegram_sent": False,
        "bookmaker_action": False,
        "paper_only": True,
        "lab_only": True,
        "can_influence_picks": False,
    }
