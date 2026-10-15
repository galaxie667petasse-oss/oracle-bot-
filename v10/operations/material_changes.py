from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from v10.config import V10Settings
from v10.llm.evidence.models import stable_hash


@dataclass(frozen=True)
class MaterialChangeThresholds:
    odds_relative_change: float = 0.03
    fair_probability_change_pp: float = 0.015
    model_probability_change_pp: float = 0.02
    uncertainty_change: float = 0.10

    @classmethod
    def from_settings(cls, settings: V10Settings) -> "MaterialChangeThresholds":
        return cls(
            odds_relative_change=settings.material_odds_relative_change,
            fair_probability_change_pp=settings.material_fair_probability_change_pp,
            model_probability_change_pp=settings.material_model_probability_change_pp,
            uncertainty_change=settings.material_uncertainty_change,
        )


class MaterialChangeDetector:
    def __init__(self, thresholds: MaterialChangeThresholds | None = None):
        self.thresholds = thresholds or MaterialChangeThresholds()

    def detect(self, old: dict[str, Any], new: dict[str, Any]) -> dict:
        rules: list[str] = []
        if old.get("fixture_status") != new.get("fixture_status"):
            rules.append("fixture_status_changed")
        if old.get("event_time") != new.get("event_time"):
            rules.append("event_time_changed")
        old_odds = float(old.get("decimal_odds", 0) or 0)
        new_odds = float(new.get("decimal_odds", 0) or 0)
        if old_odds > 0 and abs(new_odds - old_odds) / old_odds >= self.thresholds.odds_relative_change:
            rules.append("odds_relative_change")
        if abs(float(new.get("fair_probability", 0) or 0) - float(old.get("fair_probability", 0) or 0)) >= self.thresholds.fair_probability_change_pp:
            rules.append("fair_probability_change")
        if abs(float(new.get("model_probability", 0) or 0) - float(old.get("model_probability", 0) or 0)) >= self.thresholds.model_probability_change_pp:
            rules.append("model_probability_change")
        if abs(float(new.get("uncertainty", 0) or 0) - float(old.get("uncertainty", 0) or 0)) >= self.thresholds.uncertainty_change:
            rules.append("uncertainty_change")
        if bool(new.get("lineup_confirmed")) and not bool(old.get("lineup_confirmed")):
            rules.append("lineup_confirmed")
        if old.get("quality_status") != new.get("quality_status") and new.get("quality_status") == "FAIL":
            rules.append("quality_failed")
        if bool(new.get("hard_veto")) and not bool(old.get("hard_veto")):
            rules.append("hard_veto_appeared")
        material = bool(rules)
        return {
            "old_fingerprint": stable_hash(old),
            "new_fingerprint": stable_hash(new),
            "material": material,
            "severity": "HIGH" if any(rule in rules for rule in ("event_time_changed", "quality_failed", "hard_veto_appeared")) else ("MEDIUM" if material else "INFO"),
            "rules": rules,
            "caused_rescan": material,
            "caused_llm_rerun": any(rule not in {"odds_relative_change"} for rule in rules),
        }

