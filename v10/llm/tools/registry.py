from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from v10.llm.evidence.models import CandidateEvidencePacket


READ_ONLY_TOOL_NAMES = {
    "get_candidate_snapshot",
    "get_fixture_snapshot",
    "get_feature_snapshot",
    "get_model_predictions",
    "get_score_distribution_summary",
    "get_market_snapshot",
    "get_odds_history",
    "get_data_quality_report",
    "get_team_form_snapshot",
    "get_schedule_snapshot",
    "get_player_availability_snapshot",
    "get_lineup_snapshot",
    "get_competition_context",
    "get_portfolio_exposure",
    "get_evidence_item",
    "list_validated_findings",
}


@dataclass
class ReadOnlyToolRegistry:
    packet: CandidateEvidencePacket
    calls: list[dict[str, Any]] = field(default_factory=list)

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in READ_ONLY_TOOL_NAMES:
            raise ValueError("tool_not_allowed")
        fixture_id = arguments.get("fixture_id", self.packet.fixture_id)
        if str(fixture_id) != self.packet.fixture_id:
            raise ValueError("tool_cross_fixture")
        self.calls.append({"name": name, "arguments": dict(arguments)})
        if name == "get_candidate_snapshot":
            return self.packet.model_dump(mode="json", exclude={"evidence"})
        if name == "get_evidence_item":
            evidence_id = str(arguments.get("evidence_id", ""))
            for item in self.packet.evidence:
                if item.evidence_id == evidence_id:
                    return item.model_dump(mode="json")
            raise ValueError("evidence_not_found")
        if name == "get_model_predictions":
            return {"probabilities": self.packet.probabilities, "evidence_ids": [item.evidence_id for item in self.packet.evidence if item.type == "MODEL_PREDICTION"]}
        if name == "get_market_snapshot":
            return {"market": self.packet.market, "evidence_ids": [item.evidence_id for item in self.packet.evidence if item.type == "MARKET_SNAPSHOT"]}
        if name == "get_data_quality_report":
            return {"quality": self.packet.quality, "evidence_ids": [item.evidence_id for item in self.packet.evidence if item.type == "DATA_QUALITY"]}
        return {"status": "NO_DATA", "missing": True, "as_of": self.packet.decision_as_of.isoformat()}
