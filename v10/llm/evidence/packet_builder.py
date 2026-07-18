from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import CandidateEvidencePacket, EvidenceItem


class CandidateEvidencePacketBuilder:
    def build(self, candidate: dict[str, Any], decision_as_of: datetime) -> CandidateEvidencePacket:
        candidate_id = str(candidate["candidate_id"])
        fixture_id = str(candidate["fixture_id"])
        market_key = str(candidate.get("market_key", "match_winner"))
        selection_key = str(candidate.get("selection_key", "home"))
        evidence: list[EvidenceItem] = []
        base = {"candidate_id": candidate_id, "fixture_id": fixture_id, "observed_at": decision_as_of, "effective_at": decision_as_of}
        evidence.append(
            EvidenceItem(
                **base,
                type="MODEL_PREDICTION",
                source_reference=str(candidate.get("model_version_id", "synthetic-model")),
                valid_as_of=True,
                reliability=float(candidate.get("model_reliability", 0.8)),
                content={
                    "probabilities": candidate.get("probabilities", {}),
                    "uncertainty": candidate.get("uncertainty", {}),
                    "model_versions": candidate.get("model_versions", []),
                },
            )
        )
        evidence.append(
            EvidenceItem(
                **base,
                type="MARKET_SNAPSHOT",
                source_reference=str(candidate.get("market_snapshot_id", "synthetic-market")),
                valid_as_of=bool(candidate.get("odds_fresh", True)),
                reliability=float(candidate.get("market_reliability", 0.85)),
                content=candidate.get("market", {}),
            )
        )
        evidence.append(
            EvidenceItem(
                **base,
                type="DATA_QUALITY",
                source_reference=str(candidate.get("quality_report_id", "synthetic-quality")),
                valid_as_of=True,
                reliability=float(candidate.get("quality", {}).get("completeness", 0.75)),
                content=candidate.get("quality", {}),
            )
        )
        if candidate.get("deterministic_reasons"):
            evidence.append(
                EvidenceItem(
                    **base,
                    type="DETERMINISTIC_FILTER",
                    source_reference="deterministic-filter-v1",
                    valid_as_of=True,
                    reliability=1.0,
                    content={"reasons": candidate.get("deterministic_reasons", [])},
                )
            )
        return CandidateEvidencePacket(
            candidate_id=candidate_id,
            fixture_id=fixture_id,
            market_key=market_key,
            selection_key=selection_key,
            decision_as_of=decision_as_of,
            deterministic_status=str(candidate.get("deterministic_status", "ELIGIBLE")),
            deterministic_reasons=list(candidate.get("deterministic_reasons", [])),
            probabilities=dict(candidate.get("probabilities", {})),
            market=dict(candidate.get("market", {})),
            quality=dict(candidate.get("quality", {})),
            uncertainty=dict(candidate.get("uncertainty", {})),
            missing_information=list(candidate.get("missing_information", [])),
            evidence=evidence,
        )
