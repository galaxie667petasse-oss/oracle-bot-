from __future__ import annotations

from v10.llm.contracts import AgentFinding, FinalJudgeReview
from v10.llm.evidence.models import CandidateEvidencePacket


def deterministic_hard_vetoes(packet: CandidateEvidencePacket) -> list[str]:
    vetoes: list[str] = []
    if packet.deterministic_status not in {"ELIGIBLE", "PRELIMINARY"}:
        vetoes.append("deterministic_ineligible")
    if not bool(packet.market.get("odds_fresh", True)):
        vetoes.append("odds_stale")
    if float(packet.market.get("expected_value_calibrated", packet.market.get("ev", 0.0)) or 0.0) <= 0:
        vetoes.append("ev_not_positive")
    if float(packet.quality.get("completeness", packet.quality.get("score", 1.0)) or 0.0) < 0.5:
        vetoes.append("data_quality_too_low")
    return vetoes


def finding_contradictions(packet: CandidateEvidencePacket, findings: list[AgentFinding]) -> list[dict]:
    contradictions: list[dict] = []
    valid_ids = packet.evidence_ids()
    for finding in findings:
        for evidence_id in finding.evidence_ids:
            if evidence_id not in valid_ids:
                contradictions.append({"code": "agent_cited_missing_evidence", "agent_id": finding.agent_id, "hard_veto": True})
        if finding.veto:
            contradictions.append({"code": finding.veto_code or "agent_veto", "agent_id": finding.agent_id, "hard_veto": True})
        if finding.agent_id == "squad_availability_analyst" and not any(item.type in {"SQUAD_AVAILABILITY", "LINEUP"} for item in packet.evidence):
            contradictions.append({"code": "squad_agent_without_squad_evidence", "agent_id": finding.agent_id, "hard_veto": True})
    return contradictions


def judge_contradictions(review: FinalJudgeReview | None, hard_vetoes: list[str]) -> list[dict]:
    if review is None:
        return []
    if review.recommendation == "ACCEPT_SHADOW" and hard_vetoes:
        return [{"code": "judge_ignored_hard_veto", "hard_veto": True, "vetoes": hard_vetoes}]
    return []
