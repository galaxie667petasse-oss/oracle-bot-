from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .models import EvidenceItem


@dataclass
class EvidenceRegistry:
    items: dict[str, EvidenceItem] = field(default_factory=dict)

    def add(self, item: EvidenceItem) -> EvidenceItem:
        self.items[item.evidence_id] = item
        return item

    def get(self, evidence_id: str) -> EvidenceItem | None:
        return self.items.get(evidence_id)

    def validate_reference(self, evidence_id: str, candidate_id: str, fixture_id: str, as_of: datetime) -> tuple[bool, str]:
        item = self.get(evidence_id)
        if item is None:
            return False, "evidence_not_found"
        if item.candidate_id != candidate_id:
            return False, "evidence_cross_candidate"
        if item.fixture_id != fixture_id:
            return False, "evidence_cross_fixture"
        if item.observed_at > as_of:
            return False, "evidence_future_observed_at"
        if not item.valid_as_of:
            return False, "evidence_not_valid_as_of"
        return True, "ok"

    def by_type(self, evidence_type: str) -> list[EvidenceItem]:
        return [item for item in self.items.values() if item.type == evidence_type]
