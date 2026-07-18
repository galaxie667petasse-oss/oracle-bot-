from __future__ import annotations

from time import perf_counter

from v10.llm.agents.contracts import PANEL_ROLES
from v10.llm.contracts import LLMUsage, StructuredRequest, StructuredResponse


class MockLLMProvider:
    provider_key = "mock"

    def __init__(self, scenario: str = "valid"):
        self.scenario = scenario
        self.calls: list[StructuredRequest] = []

    async def health_check(self) -> dict:
        return {"provider": self.provider_key, "status": "OK", "paid_calls": False}

    async def generate_with_tools(self, request: StructuredRequest) -> StructuredResponse:
        return await self.generate_structured(request)

    async def generate_structured(self, request: StructuredRequest) -> StructuredResponse:
        start = perf_counter()
        self.calls.append(request)
        if self.scenario == "timeout":
            raise TimeoutError("mock timeout")
        if self.scenario == "429":
            raise RuntimeError("mock 429")
        if self.scenario == "model_unavailable":
            return self._response(request, {"error": "model_unavailable"}, "MODEL_UNAVAILABLE", start)
        if self.scenario == "json_invalid":
            return self._response(request, {"not": "valid"}, "INVALID_JSON", start)
        if request.panel_or_agent == "final_judge":
            recommendation = "ACCEPT_SHADOW"
            if self.scenario in {"insufficient", "invented_evidence"}:
                recommendation = "INSUFFICIENT_DATA"
            if self.scenario == "veto":
                recommendation = "REJECT"
            evidence_ids = list(request.input_payload.get("evidence_ids", []))
            if self.scenario == "invented_evidence":
                evidence_ids = ["invented-proof"]
            return self._response(
                request,
                {
                    "schema_version": "1.0",
                    "candidate_id": request.candidate_id,
                    "fixture_id": request.fixture_id,
                    "recommendation": recommendation,
                    "review_confidence": 0.72,
                    "supporting_evidence_ids": evidence_ids[:1],
                    "opposing_evidence_ids": [],
                    "acknowledged_vetoes": ["hard_veto"] if self.scenario == "veto" else [],
                    "key_supporting_factors": ["preuves coherentes"] if recommendation == "ACCEPT_SHADOW" else [],
                    "key_counterarguments": ["preuve insuffisante"] if recommendation != "ACCEPT_SHADOW" else [],
                    "missing_information": ["effectif non confirme"] if self.scenario == "insufficient" else [],
                    "unresolved_contradictions": [],
                    "material_change_triggers": ["odds_stale", "new_lineup"],
                    "summary": "revue shadow mock",
                },
                "OK",
                start,
            )
        verdict = "SUPPORT"
        veto = False
        veto_code = None
        if self.scenario == "veto":
            verdict, veto, veto_code = "STRONG_OPPOSE", True, "hard_veto"
        if self.scenario == "insufficient":
            verdict = "INSUFFICIENT_DATA"
        evidence_ids = list(request.input_payload.get("evidence_ids", []))
        if self.scenario == "invented_evidence":
            evidence_ids = ["invented-proof"]
        if request.panel_or_agent in PANEL_ROLES:
            findings = [
                self._finding_payload(request, role, verdict, veto, veto_code, evidence_ids)
                for role in PANEL_ROLES[request.panel_or_agent]
            ]
            panel = {
                "schema_version": "1.0",
                "panel_id": request.panel_or_agent,
                "candidate_id": request.candidate_id,
                "fixture_id": request.fixture_id,
                "findings": findings,
            }
            return self._response(request, panel, "OK", start)
        finding = self._finding_payload(request, request.panel_or_agent, verdict, veto, veto_code, evidence_ids)
        return self._response(request, finding, "OK", start)

    def _finding_payload(
        self,
        request: StructuredRequest,
        agent_id: str,
        verdict: str,
        veto: bool,
        veto_code: str | None,
        evidence_ids: list[str],
    ) -> dict:
        return {
            "schema_version": "1.0",
            "agent_id": agent_id,
            "candidate_id": request.candidate_id,
            "fixture_id": request.fixture_id,
            "market_key": request.input_payload.get("market_key", "match_winner"),
            "selection_key": request.input_payload.get("selection_key", "home"),
            "verdict": verdict,
            "confidence": 0.65,
            "evidence_ids": evidence_ids[:2],
            "risks": ["sample faible"] if self.scenario == "insufficient" else [],
            "missing_information": ["donnee manquante"] if self.scenario == "insufficient" else [],
            "contradictions": [],
            "veto": veto,
            "veto_code": veto_code,
            "summary": "analyse mock basee uniquement sur preuves",
        }

    def _response(self, request: StructuredRequest, output: dict, status: str, start: float) -> StructuredResponse:
        return StructuredResponse(
            request_id=request.request_id,
            provider=self.provider_key,
            requested_model=request.model,
            used_model=request.model,
            status=status,
            output=output,
            usage=LLMUsage(input_tokens=600, output_tokens=120),
            latency_ms=int((perf_counter() - start) * 1000),
        )
