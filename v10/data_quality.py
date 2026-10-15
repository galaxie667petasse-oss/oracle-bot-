from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


PASS = "PASS"
PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
FAIL = "FAIL"
STALE = "STALE"
CONFLICTING = "CONFLICTING"


@dataclass(frozen=True)
class QualityReport:
    status: str
    completeness_score: float
    blockers: list[str]
    warnings: list[str]
    missing_fields: list[str]
    observed_at: str
    lab_only: bool = True
    can_influence_picks: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def evaluate_fixture_quality(
    fixture: Mapping[str, Any],
    market: Mapping[str, Any],
    now_utc: datetime | None = None,
    max_odds_age_seconds: int = 7200,
    min_bookmaker_count: int = 2,
    min_recent_matches: int = 5,
) -> QualityReport:
    now_utc = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    blockers: list[str] = []
    warnings: list[str] = []
    missing: list[str] = []
    required = ["fixture_id", "home_team", "away_team", "league", "kickoff_time"]
    for key in required:
        if not str(fixture.get(key, "")).strip():
            missing.append(key)
    if missing:
        blockers.append("missing_required_fixture_fields")
    if str(fixture.get("home_team", "")).strip().lower() == str(fixture.get("away_team", "")).strip().lower():
        blockers.append("home_away_identity_conflict")
    fixture_status = str(fixture.get("status", "scheduled")).strip().lower()
    if fixture_status in {"postponed", "cancelled", "abandoned", "suspended"}:
        blockers.append(f"fixture_status_{fixture_status}")
    if fixture.get("provider_conflict"):
        return QualityReport(CONFLICTING, 0.0, ["provider_conflict"], warnings, missing, now_utc.isoformat())
    bookmaker_count = int(float(market.get("bookmaker_count") or 0))
    if bookmaker_count < min_bookmaker_count:
        blockers.append("insufficient_bookmaker_count")
    odds_observed_at = _parse_datetime(market.get("odds_observed_at"))
    if odds_observed_at is None:
        blockers.append("odds_observed_at_missing")
    else:
        age = (now_utc - odds_observed_at).total_seconds()
        if age > max_odds_age_seconds:
            warnings.append("odds_stale")
    recent_matches = int(float(fixture.get("recent_match_count") or 0))
    if recent_matches < min_recent_matches:
        warnings.append("recent_history_low")
    components = 6
    penalties = len(blockers) * 2 + len(warnings) + len(missing)
    score = max(0.0, min(1.0, (components - penalties) / components))
    if blockers:
        status = FAIL
    elif "odds_stale" in warnings:
        status = STALE
    elif warnings:
        status = PASS_WITH_WARNINGS
    else:
        status = PASS
    return QualityReport(status, round(score, 4), blockers, warnings, missing, now_utc.isoformat())

