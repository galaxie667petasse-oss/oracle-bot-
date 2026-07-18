from __future__ import annotations

from uuid import uuid4

from v10.llm.contracts import StructuredRequest
from v10.llm.evidence.models import CandidateEvidencePacket
from v10.llm.registry import LLMModelRegistry


def build_panel_request(packet: CandidateEvidencePacket, panel_or_agent: str, tier: str, registry: LLMModelRegistry, allow_paid: bool = False) -> StructuredRequest:
    route = registry.route(tier)
    return StructuredRequest(
        request_id=str(uuid4()),
        candidate_id=packet.candidate_id,
        fixture_id=packet.fixture_id,
        tier=route.tier,
        panel_or_agent=panel_or_agent,
        model=route.model,
        reasoning_effort=route.reasoning_effort,
        schema_name="final_judge_review" if panel_or_agent == "final_judge" else "agent_finding",
        prompt_version="phase4_v1",
        packet_hash=packet.packet_hash,
        allow_paid=allow_paid,
        input_payload={
            "candidate_id": packet.candidate_id,
            "fixture_id": packet.fixture_id,
            "market_key": packet.market_key,
            "selection_key": packet.selection_key,
            "decision_as_of": packet.decision_as_of.isoformat(),
            "probabilities": packet.probabilities,
            "market": packet.market,
            "quality": packet.quality,
            "uncertainty": packet.uncertainty,
            "missing_information": packet.missing_information,
            "evidence_ids": sorted(packet.evidence_ids()),
            "instruction": "Use only evidence_ids. Do not change probability, odds, EV, CLV, stake, bankroll or results.",
        },
    )
