from __future__ import annotations

from v10.llm.contracts import AgentFinding, FinalJudgeReview
from v10.llm.evidence.models import CandidateEvidencePacket

from .rules import deterministic_hard_vetoes, finding_contradictions, judge_contradictions


class ContradictionEngine:
    def analyze(self, packet: CandidateEvidencePacket, findings: list[AgentFinding], review: FinalJudgeReview | None = None) -> dict:
        hard = deterministic_hard_vetoes(packet)
        contradictions = finding_contradictions(packet, findings)
        hard.extend([item["code"] for item in contradictions if item.get("hard_veto")])
        contradictions.extend(judge_contradictions(review, hard))
        hard.extend([item["code"] for item in contradictions if item.get("hard_veto") and item["code"] not in hard])
        return {
            "hard_vetoes": sorted(set(hard)),
            "contradictions": contradictions,
            "status": "HARD_VETO" if hard else ("CONTRADICTIONS" if contradictions else "OK"),
        }
