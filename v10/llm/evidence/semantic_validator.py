from __future__ import annotations

from v10.llm.contracts import AgentFinding, FinalJudgeReview

from .models import CandidateEvidencePacket
from .registry import EvidenceRegistry


class SemanticValidationResult(dict):
    @property
    def ok(self) -> bool:
        return not self.get("errors")


class SemanticValidator:
    def __init__(self, packet: CandidateEvidencePacket):
        self.packet = packet
        self.registry = EvidenceRegistry({item.evidence_id: item for item in packet.evidence})

    def validate_finding(self, finding: AgentFinding) -> SemanticValidationResult:
        errors: list[str] = []
        if finding.candidate_id != self.packet.candidate_id:
            errors.append("finding_cross_candidate")
        if finding.fixture_id != self.packet.fixture_id:
            errors.append("finding_cross_fixture")
        for evidence_id in finding.evidence_ids:
            ok, reason = self.registry.validate_reference(evidence_id, self.packet.candidate_id, self.packet.fixture_id, self.packet.decision_as_of)
            if not ok:
                errors.append(reason)
        if finding.agent_id in {"squad_availability_analyst", "tactical_matchup_analyst", "news_source_reliability_analyst"}:
            allowed = {"SQUAD_AVAILABILITY", "LINEUP", "COMPETITION_CONTEXT"}
            if not any(self.registry.get(eid) and self.registry.get(eid).type in allowed for eid in finding.evidence_ids):
                errors.append("agent_has_no_authorized_fresh_evidence")
        return SemanticValidationResult({"errors": errors, "validated": not errors})

    def validate_judge(self, review: FinalJudgeReview, hard_vetoes: list[str] | None = None) -> SemanticValidationResult:
        errors: list[str] = []
        if review.candidate_id != self.packet.candidate_id:
            errors.append("judge_cross_candidate")
        if review.fixture_id != self.packet.fixture_id:
            errors.append("judge_cross_fixture")
        for evidence_id in review.supporting_evidence_ids + review.opposing_evidence_ids:
            ok, reason = self.registry.validate_reference(evidence_id, self.packet.candidate_id, self.packet.fixture_id, self.packet.decision_as_of)
            if not ok:
                errors.append(reason)
        for veto in hard_vetoes or []:
            if veto not in review.acknowledged_vetoes and review.recommendation == "ACCEPT_SHADOW":
                errors.append("judge_ignored_hard_veto")
        return SemanticValidationResult({"errors": errors, "validated": not errors})
