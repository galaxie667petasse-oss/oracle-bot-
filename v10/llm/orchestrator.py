from __future__ import annotations

from decimal import Decimal
from typing import Any

from v10.llm.agents.panels import build_panel_request
from v10.llm.agents.planner import planned_steps
from v10.llm.budgets.manager import BudgetManager
from v10.llm.cache.keys import llm_cache_key
from v10.llm.cache.repository import InMemoryLLMCache
from v10.llm.config import LLMRuntimeConfig
from v10.llm.contracts import AgentFinding, FinalJudgeReview, LLMProvider, PanelResult, StructuredResponse
from v10.llm.contradictions.engine import ContradictionEngine
from v10.llm.evidence.models import CandidateEvidencePacket
from v10.llm.evidence.packet_builder import CandidateEvidencePacketBuilder
from v10.llm.evidence.semantic_validator import SemanticValidator
from v10.llm.judge.gate import DeterministicDecisionGate
from v10.llm.registry import LLMModelRegistry
from v10.llm.routing import ComplexityRouter


class LLMOrchestrator:
    def __init__(
        self,
        config: LLMRuntimeConfig,
        provider: LLMProvider,
        budget: BudgetManager | None = None,
        cache: InMemoryLLMCache | None = None,
    ):
        self.config = config
        self.provider = provider
        self.registry = LLMModelRegistry(config)
        self.router = ComplexityRouter()
        self.budget = budget or BudgetManager(config.daily_budget_usd, config.scan_budget_usd, config.fixture_budget_usd)
        self.cache = cache or InMemoryLLMCache()
        self.contradictions = ContradictionEngine()
        self.gate = DeterministicDecisionGate()

    async def analyze_candidate(
        self,
        candidate: dict[str, Any],
        decision_as_of,
        allow_paid: bool = False,
        portfolio_candidate_count: int = 1,
        top_finalist: bool = False,
    ) -> dict[str, Any]:
        packet = CandidateEvidencePacketBuilder().build(candidate, decision_as_of)
        return await self.analyze_packet(packet, allow_paid=allow_paid, portfolio_candidate_count=portfolio_candidate_count, top_finalist=top_finalist)

    async def analyze_packet(
        self,
        packet: CandidateEvidencePacket,
        allow_paid: bool = False,
        portfolio_candidate_count: int = 1,
        top_finalist: bool = False,
    ) -> dict[str, Any]:
        plan = self.router.plan(packet, portfolio_candidate_count=portfolio_candidate_count, top_finalist=top_finalist)
        findings: list[AgentFinding] = []
        review: FinalJudgeReview | None = None
        calls: list[dict[str, Any]] = []
        semantic_errors: list[str] = []
        if not plan.run_luna:
            contradiction_report = self.contradictions.analyze(packet, findings, review)
            decision = self.gate.decide(packet, review, contradiction_report)
            return self._report(packet, plan, findings, review, contradiction_report, decision, calls, semantic_errors)
        validator = SemanticValidator(packet)
        provider_key = getattr(self.provider, "provider_key", "provider")
        for step in planned_steps(plan):
            request = build_panel_request(packet, step["panel_or_agent"], step["tier"], self.registry, allow_paid=allow_paid)
            cache_key = llm_cache_key(provider_key, request.model, request.reasoning_effort, request.prompt_version, request.schema_name, request.panel_or_agent, packet.packet_hash)
            cached = self.cache.get(cache_key)
            if cached:
                response = StructuredResponse(**cached)
                response.cache_status = "hit"
            else:
                reservation = None
                if allow_paid:
                    estimate = self.budget.estimate(request.model, input_tokens=1200, output_tokens=request.max_output_tokens)
                    reservation = self.budget.reserve(packet.candidate_id, request.model, estimate)
                response = await self.provider.generate_structured(request)
                if reservation:
                    actual = response.usage.estimated_cost_usd or self.budget.estimate(response.used_model, response.usage.input_tokens, response.usage.output_tokens, response.usage.cached_input_tokens)
                    self.budget.reconcile(reservation.reservation_id, actual)
                self.cache.put(cache_key, response.model_dump(mode="json"), packet.packet_hash)
            calls.append(
                {
                    "panel_or_agent": request.panel_or_agent,
                    "tier": request.tier,
                    "model": request.model,
                    "reasoning": request.reasoning_effort,
                    "status": response.status,
                    "cache": response.cache_status,
                }
            )
            if response.status != "OK":
                semantic_errors.append(response.status)
                continue
            try:
                if request.panel_or_agent == "final_judge":
                    candidate_review = FinalJudgeReview(**response.output)
                    validated = validator.validate_judge(candidate_review, self.contradictions.analyze(packet, findings).get("hard_vetoes", []))
                    if validated.ok:
                        review = candidate_review
                    else:
                        semantic_errors.extend(validated["errors"])
                else:
                    step_findings: list[AgentFinding]
                    if "findings" in response.output:
                        panel = PanelResult(**response.output)
                        step_findings = panel.findings
                    else:
                        step_findings = [AgentFinding(**response.output)]
                    stop_after_step = False
                    for finding in step_findings:
                        validated = validator.validate_finding(finding)
                        if validated.ok:
                            findings.append(finding)
                            if finding.veto:
                                calls[-1]["cascade_stopped"] = "agent_hard_veto"
                                stop_after_step = True
                        else:
                            semantic_errors.extend(validated["errors"])
                    if stop_after_step:
                        break
            except Exception as exc:
                semantic_errors.append(f"schema_invalid:{exc}")
        contradiction_report = self.contradictions.analyze(packet, findings, review)
        if semantic_errors:
            contradiction_report["contradictions"].append({"code": "semantic_validation_failed", "errors": semantic_errors, "hard_veto": True})
            contradiction_report["hard_vetoes"] = sorted(set(contradiction_report.get("hard_vetoes", []) + ["semantic_validation_failed"]))
            contradiction_report["status"] = "HARD_VETO"
        decision = self.gate.decide(packet, review, contradiction_report)
        return self._report(packet, plan, findings, review, contradiction_report, decision, calls, semantic_errors)

    def _report(self, packet, plan, findings, review, contradiction_report, decision, calls, semantic_errors) -> dict[str, Any]:
        return {
            "candidate_id": packet.candidate_id,
            "fixture_id": packet.fixture_id,
            "packet_hash": packet.packet_hash,
            "routing": plan.__dict__,
            "calls": calls,
            "findings": [finding.model_dump(mode="json") for finding in findings],
            "judge": review.model_dump(mode="json") if review else None,
            "contradictions": contradiction_report,
            "semantic_errors": semantic_errors,
            "decision": decision.__dict__,
            "budget": self.budget.status(),
            "cache": self.cache.status(),
            "telegram_sent": False,
            "bookmaker_action": False,
            "paper_only": True,
            "lab_only": True,
            "can_influence_picks": False,
        }
