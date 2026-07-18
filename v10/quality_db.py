from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from v10.data_quality import evaluate_fixture_quality
from v10.db.models import Competition, Fixture, OddsSnapshot, Team
from v10.db.repositories import OddsSnapshotRepository
from v10.time import ensure_utc, utc_now


def fixture_quality_from_db(
    session: Session,
    fixture_id: str,
    now_utc: datetime | None = None,
    max_odds_age_seconds: int = 7200,
    min_bookmaker_count: int = 2,
) -> dict[str, Any]:
    now_utc = ensure_utc(now_utc or utc_now(), "now_utc")
    fixture = session.get(Fixture, fixture_id)
    if fixture is None:
        return {
            "status": "FAIL",
            "blockers": ["fixture_not_found"],
            "warnings": [],
            "missing_fields": ["fixture_id"],
            "lab_only": True,
            "can_influence_picks": False,
        }
    competition = session.get(Competition, fixture.competition_id)
    home = session.get(Team, fixture.home_team_id)
    away = session.get(Team, fixture.away_team_id)
    odds_rows = OddsSnapshotRepository(session).list_fixture_odds_at(fixture.id, now_utc)
    bookmaker_count = len({row.bookmaker_id for row in odds_rows})
    latest_observed = max((ensure_utc(row.observed_at) for row in odds_rows), default=None)
    markets = sorted({row.market_id for row in odds_rows})
    source_payload_count = session.scalar(
        select(func.count(func.distinct(OddsSnapshot.raw_payload_id))).where(
            OddsSnapshot.fixture_id == fixture.id,
            OddsSnapshot.raw_payload_id.is_not(None),
        )
    )
    report = evaluate_fixture_quality(
        {
            "fixture_id": fixture.id,
            "home_team": home.name if home else "",
            "away_team": away.name if away else "",
            "league": competition.name if competition else "",
            "kickoff_time": ensure_utc(fixture.event_time).isoformat(),
            "status": fixture.canonical_status,
            "recent_match_count": 5,
        },
        {
            "bookmaker_count": bookmaker_count,
            "odds_observed_at": latest_observed.isoformat() if latest_observed else "",
        },
        now_utc=now_utc,
        max_odds_age_seconds=max_odds_age_seconds,
        min_bookmaker_count=min_bookmaker_count,
    ).to_dict()
    report.update(
        {
            "fixture_id": fixture.id,
            "external_fixture_id": fixture.external_id,
            "bookmaker_count": bookmaker_count,
            "market_count": len(markets),
            "odds_snapshot_count": len(odds_rows),
            "latest_odds_observed_at": latest_observed.isoformat() if latest_observed else None,
            "source_payload_count": int(source_payload_count or 0),
        }
    )
    return report
