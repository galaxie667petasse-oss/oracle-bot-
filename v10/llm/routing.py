from __future__ import annotations

from dataclasses import dataclass, field

from .evidence.models import CandidateEvidencePacket


@dataclass(frozen=True)
class LLMRoutePlan:
    complexity_score: float
    luna_batchable: bool
    run_luna: bool
    terra_panels: list[str] = field(default_factory=list)
    run_devils_advocate: bool = False
    run_portfolio: bool = False
    run_sol: bool = False
    skipped_agents: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    max_calls: int = 0


class ComplexityRouter:
    def score(self, packet: CandidateEvidencePacket, portfolio_candidate_count: int = 1) -> tuple[float, list[str]]:
        reasons: list[str] = []
        quality = float(packet.quality.get("completeness", packet.quality.get("score", 0.75)) or 0.0)
        uncertainty = float(packet.uncertainty.get("score", 0.0) or 0.0)
        model_disagreement = float(packet.uncertainty.get("model_disagreement", 0.0) or 0.0)
        edge = abs(float(packet.market.get("edge_calibrated", packet.market.get("edge", 0.0)) or 0.0))
        bookmaker_count = int(packet.market.get("bookmaker_count", 0) or 0)
        odds_move = abs(float(packet.market.get("line_movement_pct", 0.0) or 0.0))
        score = 0.0
        if quality < 0.7:
            score += 0.25
            reasons.append("low_data_quality")
        if uncertainty > 0.08:
            score += 0.25
            reasons.append("high_uncertainty")
        if model_disagreement > 0.06:
            score += 0.2
            reasons.append("model_disagreement")
        if 0.02 <= edge <= 0.05:
            score += 0.15
            reasons.append("thin_edge")
        if bookmaker_count < 2:
            score += 0.2
            reasons.append("limited_bookmakers")
        if odds_move > 0.08:
            score += 0.15
            reasons.append("large_line_movement")
        if packet.missing_information:
            score += 0.1
            reasons.append("missing_information")
        if portfolio_candidate_count > 1:
            score += 0.1
            reasons.append("portfolio_context")
        return min(score, 1.0), reasons

    def plan(self, packet: CandidateEvidencePacket, portfolio_candidate_count: int = 1, top_finalist: bool = False) -> LLMRoutePlan:
        if packet.deterministic_status not in {"ELIGIBLE", "PRELIMINARY"}:
            return LLMRoutePlan(
                complexity_score=0.0,
                luna_batchable=False,
                run_luna=False,
                skipped_agents=["all"],
                reasons=["deterministic_ineligible"],
                max_calls=0,
            )
        score, reasons = self.score(packet, portfolio_candidate_count)
        panels: list[str] = []
        skipped: list[str] = []
        if score >= 0.25:
            panels.append("quantitative_integrity")
        else:
            skipped.append("terra_panels_low_complexity")
        has_context = any(key in packet.quality for key in ("recent_form_available", "schedule_available", "competition_context_available"))
        has_fresh = any(item.type in {"SQUAD_AVAILABILITY", "LINEUP", "COMPETITION_CONTEXT"} for item in packet.evidence)
        if score >= 0.45 and has_context:
            panels.append("match_context")
        elif score >= 0.45:
            skipped.append("match_context_no_structured_data")
        if has_fresh:
            panels.append("fresh_information")
        else:
            skipped.append("fresh_information_no_evidence")
        run_devils = score >= 0.55 or bool(packet.missing_information)
        run_portfolio = portfolio_candidate_count > 1
        ev = float(packet.market.get("expected_value_calibrated", packet.market.get("ev", 0.0)) or 0.0)
        odds_fresh = bool(packet.market.get("odds_fresh", True))
        run_sol = bool(top_finalist and score >= 0.5 and ev > 0 and odds_fresh)
        max_calls = int(bool(True)) + len(panels) + int(run_devils) + int(run_portfolio) + int(run_sol)
        return LLMRoutePlan(
            complexity_score=score,
            luna_batchable=score < 0.45,
            run_luna=True,
            terra_panels=panels,
            run_devils_advocate=run_devils,
            run_portfolio=run_portfolio,
            run_sol=run_sol,
            skipped_agents=skipped,
            reasons=reasons,
            max_calls=max_calls,
        )
