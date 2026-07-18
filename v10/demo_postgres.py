import json
import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from v10.config import V10Settings, load_settings
from v10.db.migrations import upgrade_head
from v10.db.models import Fixture, OddsSnapshot
from v10.db.repositories import FixtureRepository, OddsSnapshotRepository
from v10.db.session import create_engine_from_settings, create_session_factory, session_scope
from v10.quality_db import fixture_quality_from_db
from v10.replay.engine import replay_provider_file, replay_run
from v10.time import parse_utc


def _fixture_path(name: str) -> str:
    return str(Path("tests") / "fixtures" / "providers" / "api_football" / name)


def run_persistence_demo(database_url: str | None = None) -> dict[str, Any]:
    temp_dir = None
    engine = None
    settings = load_settings()
    postgres_tested = False
    sqlite_used = False
    if database_url:
        settings = V10Settings(DATABASE_URL=database_url)
        postgres_tested = settings.sqlalchemy_url().startswith("postgresql+")
    elif settings.database_url:
        postgres_tested = settings.sqlalchemy_url().startswith("postgresql+")
    else:
        temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(temp_dir.name) / "oracle_v10_demo.sqlite"
        settings = V10Settings(DATABASE_URL=f"sqlite:///{db_path.as_posix()}")
        sqlite_used = True
    try:
        migration = upgrade_head(settings)
        engine = create_engine_from_settings(settings)
        session_factory = create_session_factory(engine)
        observed_1 = "2026-06-01T10:00:00+00:00"
        observed_2 = "2026-06-01T11:00:00+00:00"
        with session_scope(session_factory) as session:
            fixtures_report = replay_provider_file(
                session,
                _fixture_path("fixtures_sample.json"),
                "api_football",
                observed_at=observed_1,
                apply=True,
            )
            odds_report_1 = replay_provider_file(
                session,
                _fixture_path("odds_sample.json"),
                "api_football",
                observed_at=observed_1,
                apply=True,
            )
            duplicate_report = replay_provider_file(
                session,
                _fixture_path("odds_sample.json"),
                "api_football",
                observed_at=observed_1,
                apply=True,
            )
            replay_summary = replay_run(session, odds_report_1["ingestion_run_id"])
            odds_report_2 = replay_provider_file(
                session,
                _fixture_path("odds_sample_changed.json"),
                "api_football",
                observed_at=observed_2,
                apply=True,
            )
            fixture = session.scalar(select(Fixture).where(Fixture.external_id == "91001"))
            if fixture is None:
                raise RuntimeError("demo fixture missing after replay")
            history = OddsSnapshotRepository(session).list_odds_between(
                fixture.id,
                parse_utc("2026-06-01T09:00:00+00:00"),
                parse_utc("2026-06-01T12:00:00+00:00"),
            )
            latest_before_change = OddsSnapshotRepository(session).get_latest_odds_as_of(
                fixture.id,
                "match_winner",
                parse_utc("2026-06-01T10:30:00+00:00"),
            )
            latest_after_change = OddsSnapshotRepository(session).get_latest_odds_as_of(
                fixture.id,
                "match_winner",
                parse_utc("2026-06-01T11:30:00+00:00"),
            )
            state_as_of = FixtureRepository(session).get_fixture_state_as_of(fixture.id, parse_utc("2026-06-01T10:30:00+00:00"))
            quality = fixture_quality_from_db(session, fixture.id, now_utc=parse_utc("2026-06-01T11:30:00+00:00"))
            odds_count = session.scalar(select(func.count()).select_from(OddsSnapshot))
            fixture_count = session.scalar(select(func.count()).select_from(Fixture))
            before_home = max((row for row in latest_before_change if row.selection_key == "home"), key=lambda row: row.decimal_odds)
            after_home = max((row for row in latest_after_change if row.selection_key == "home"), key=lambda row: row.decimal_odds)
            report = {
                "migration": migration,
                "postgres_tested": postgres_tested,
                "sqlite_used": sqlite_used,
                "fixtures_report": fixtures_report,
                "odds_report_1": odds_report_1,
                "duplicate_report": duplicate_report,
                "replay_run": replay_summary,
                "odds_report_2": odds_report_2,
                "fixture_id": fixture.id,
                "fixture_count": fixture_count,
                "odds_snapshot_count": odds_count,
                "history_count": len(history),
                "as_of_before_change_home_odds": str(before_home.decimal_odds),
                "as_of_after_change_home_odds": str(after_home.decimal_odds),
                "fixture_state_as_of": {
                    **state_as_of,
                    "event_time": state_as_of["event_time"].isoformat(),
                    "as_of": state_as_of["as_of"].isoformat(),
                }
                if state_as_of
                else None,
                "quality": quality,
                "lab_only": True,
                "can_influence_picks": False,
            }
        return json.loads(json.dumps(report, default=str))
    finally:
        if engine is not None:
            engine.dispose()
        if temp_dir is not None:
            temp_dir.cleanup()


def print_persistence_demo(report: dict[str, Any]) -> None:
    print("Demo V10 persistence end-to-end")
    print(f"- PostgreSQL teste: {report.get('postgres_tested')}")
    print(f"- SQLite utilise: {report.get('sqlite_used')}")
    print(f"- Migration head: {report.get('migration', {}).get('up_to_date')}")
    print(f"- Fixtures: {report.get('fixture_count')}")
    print(f"- Odds snapshots: {report.get('odds_snapshot_count')}")
    print(f"- Historique odds: {report.get('history_count')}")
    print(f"- As-of avant modification home odds: {report.get('as_of_before_change_home_odds')}")
    print(f"- As-of apres modification home odds: {report.get('as_of_after_change_home_odds')}")
    print(f"- Qualite fixture: {(report.get('quality') or {}).get('status')}")
    print("- Aucun reseau. Aucun Telegram. Aucune mise.")
