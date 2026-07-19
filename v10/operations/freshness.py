from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from v10.config import V10Settings
from v10.time import ensure_utc, utc_now


@dataclass(frozen=True)
class FreshnessRule:
    key: str
    max_age: timedelta
    criticality: str
    missing_behavior: str
    stale_behavior: str


class PrematchFreshnessPolicy:
    version = "prematch_freshness_v1"

    def __init__(self, settings: V10Settings | None = None):
        self.settings = settings or V10Settings()

    def odds_max_age(self, phase: str) -> timedelta:
        if phase == "T10":
            return timedelta(minutes=self.settings.max_odds_age_minutes_t10)
        if phase == "T30":
            return timedelta(minutes=self.settings.max_odds_age_minutes_t30)
        if phase == "T90":
            return timedelta(minutes=self.settings.max_odds_age_minutes_t90)
        return timedelta(minutes=self.settings.max_odds_age_minutes_t24)

    def rules(self, phase: str) -> dict[str, FreshnessRule]:
        return {
            "fixture": FreshnessRule("fixture", timedelta(minutes=self.settings.max_fixture_age_minutes), "critical", "FAIL", "FAIL"),
            "odds": FreshnessRule("odds", self.odds_max_age(phase), "critical", "FAIL", "FAIL"),
            "lineup": FreshnessRule("lineup", timedelta(minutes=self.settings.max_lineup_age_minutes), "conditional", "WARN", "WARN"),
            "availability": FreshnessRule("availability", timedelta(minutes=self.settings.max_availability_age_minutes), "optional", "WARN", "WARN"),
            "team_statistics": FreshnessRule("team_statistics", timedelta(hours=self.settings.max_team_stats_age_hours), "important", "WARN", "WARN"),
            "standings": FreshnessRule("standings", timedelta(hours=self.settings.max_standings_age_hours), "important", "WARN", "WARN"),
        }

    def evaluate(self, observed: dict[str, datetime | None], phase: str, now: datetime | None = None) -> dict:
        now = ensure_utc(now or utc_now(), "now")
        rows = []
        status = "PASS"
        for key, rule in self.rules(phase).items():
            value = observed.get(key)
            if value is None:
                item_status = rule.missing_behavior
                age_seconds = None
            else:
                value = ensure_utc(value, key)
                age = now - value
                age_seconds = int(age.total_seconds())
                item_status = "PASS" if age <= rule.max_age else rule.stale_behavior
            if item_status == "FAIL":
                status = "FAIL"
            elif item_status == "WARN" and status == "PASS":
                status = "PASS_WITH_WARNINGS"
            rows.append(
                {
                    "key": key,
                    "status": item_status,
                    "criticality": rule.criticality,
                    "max_age_seconds": int(rule.max_age.total_seconds()),
                    "age_seconds": age_seconds,
                }
            )
        return {"policy_version": self.version, "phase": phase, "status": status, "items": rows, "as_of": now.isoformat()}

