from __future__ import annotations

from dataclasses import dataclass

from v10.llm.contracts import FinalJudgeReview
from v10.llm.evidence.models import CandidateEvidencePacket


@dataclass(frozen=True)
class GateDecision:
    final_status: str
    reasons: list[str]
    shadow_accepted: bool = False


class DeterministicDecisionGate:
    def decide(self, packet: CandidateEvidencePacket, review: FinalJudgeReview | None, contradiction_report: dict) -> GateDecision:
        reasons: list[str] = []
        if packet.deterministic_status not in {"ELIGIBLE", "PRELIMINARY"}:
            reasons.append("deterministic_ineligible")
        if contradiction_report.get("hard_vetoes"):
            reasons.extend(contradiction_report["hard_vetoes"])
        if not bool(packet.market.get("odds_fresh", True)):
            reasons.append("odds_stale")
        if float(packet.market.get("expected_value_calibrated", packet.market.get("ev", 0.0)) or 0.0) <= 0:
            reasons.append("ev_not_positive")
        if float(packet.quality.get("completeness", packet.quality.get("score", 1.0)) or 0.0) < 0.5:
            reasons.append("data_quality_too_low")
        if packet.missing_information and review is None:
            return GateDecision("INSUFFICIENT_DATA", ["missing_information_unreviewed"], False)
        if reasons:
            return GateDecision("NO_BET", sorted(set(reasons)), False)
        if review is None:
            return GateDecision("WATCH", ["unreviewed"], False)
        if review.recommendation == "ACCEPT_SHADOW":
            return GateDecision("SHADOW_ACCEPTED", ["sol_accept_shadow_all_deterministic_gates_passed"], True)
        if review.recommendation in {"WATCH", "INSUFFICIENT_DATA"}:
            return GateDecision(review.recommendation, review.missing_information or ["judge_no_accept"], False)
        return GateDecision("NO_BET", ["judge_rejected"], False)
