import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

from v10.config import V10Settings, load_settings, mask_database_url
from v10.db.locks import AdvisoryLockManager
from v10.db.migrations import downgrade_base, migration_status, upgrade_head
from v10.db.models import Fixture, OddsSnapshot, Provider, RawApiPayload
from v10.db.repositories import FixtureRepository, OddsSnapshotRepository
from v10.db.session import create_engine_from_settings, create_session_factory, session_scope
from v10.hashing import content_hash, odds_snapshot_fingerprint
from v10.legacy import discover_legacy_sources, legacy_import_source
from v10.normalization.api_football import normalize_fixtures_payload, normalize_odds_payload
from v10.normalization.schemas import CanonicalOddsObservation
from v10.normalization.status import canonical_status
from v10.quality_db import fixture_quality_from_db
from v10.replay.engine import load_json_limited, replay_provider_file, replay_run
from v10.time import parse_utc, utc_now


def fixture_path(name: str) -> str:
    return str(Path("tests") / "fixtures" / "providers" / "api_football" / name)


def make_settings(tmp: str) -> V10Settings:
    return V10Settings(DATABASE_URL=f"sqlite:///{Path(tmp, 'phase2.sqlite').as_posix()}")


def migrate(tmp: str):
    settings = make_settings(tmp)
    up = upgrade_head(settings)
    assert up["up_to_date"] is True
    engine = create_engine_from_settings(settings)
    return settings, engine, create_session_factory(engine)


def test_config_masking_and_dangerous_real_money_rejected():
    settings = load_settings({"DATABASE_URL": "postgresql://user:password@localhost:5432/oracle", "REAL_MONEY_ACTIONS_ENABLED": "false"})
    report = settings.safe_report({"DATABASE_URL": "postgresql://user:password@localhost:5432/oracle"})
    assert "password" not in json.dumps(report)
    assert mask_database_url(settings.database_url).startswith("postgresql://***@localhost")
    try:
        load_settings({"REAL_MONEY_ACTIONS_ENABLED": "true"})
    except Exception:
        pass
    else:
        raise AssertionError("dangerous real money config accepted")


def test_hashes_are_stable_and_temporal_policy_is_explicit():
    a = {"b": 2, "a": [3, 1]}
    b = {"a": [3, 1], "b": 2}
    assert content_hash(a) == content_hash(b)
    observed = datetime(2026, 6, 1, 10, tzinfo=timezone.utc)
    fp1 = odds_snapshot_fingerprint("fx", "bk", "m", "home", None, Decimal("2.10"), observed)
    fp2 = odds_snapshot_fingerprint("fx", "bk", "m", "home", None, Decimal("2.20"), observed)
    fp3 = odds_snapshot_fingerprint("fx", "bk", "m", "home", None, Decimal("2.10"), datetime(2026, 6, 1, 11, tzinfo=timezone.utc))
    assert fp1 != fp2
    assert fp1 != fp3


def test_migrations_upgrade_downgrade_upgrade():
    with tempfile.TemporaryDirectory() as tmp:
        settings = make_settings(tmp)
        assert upgrade_head(settings)["up_to_date"] is True
        status = migration_status(settings)
        assert status["current_revision"] == "20260719_0004"
        assert downgrade_base(settings)["current_revision"] is None
        assert upgrade_head(settings)["up_to_date"] is True


def test_normalization_status_decimal_and_invalid_odds():
    payload = load_json_limited(fixture_path("fixtures_sample.json"))
    report = normalize_fixtures_payload(payload, "2026-06-01T10:00:00+00:00")
    assert report.fixtures[0].canonical_status == "SCHEDULED"
    assert canonical_status("FT") == "FINISHED"
    odds_payload = load_json_limited(fixture_path("odds_sample.json"))
    odds_report = normalize_odds_payload(odds_payload, "2026-06-01T10:00:00+00:00")
    assert len(odds_report.odds) == 8
    assert isinstance(odds_report.odds[0].decimal_odds, Decimal)
    try:
        CanonicalOddsObservation(
            provider_key="api_football",
            external_fixture_id="1",
            bookmaker_name="Book",
            market_key="match_winner",
            selection_key="home",
            decimal_odds="1.00",
            original_odds="1.00",
            observed_at="2026-06-01T10:00:00+00:00",
        )
    except Exception:
        pass
    else:
        raise AssertionError("invalid odds accepted")
    try:
        parse_utc("2026-06-01T10:00:00")
    except ValueError:
        pass
    else:
        raise AssertionError("naive datetime accepted")


def test_replay_idempotence_temporal_as_of_quality_and_locks():
    with tempfile.TemporaryDirectory() as tmp:
        settings, engine, session_factory = migrate(tmp)
        try:
            with session_scope(session_factory) as session:
                first = replay_provider_file(session, fixture_path("fixtures_sample.json"), "api_football", observed_at="2026-06-01T10:00:00+00:00", apply=True)
                odds = replay_provider_file(session, fixture_path("odds_sample.json"), "api_football", observed_at="2026-06-01T10:00:00+00:00", apply=True)
                duplicate = replay_provider_file(session, fixture_path("odds_sample.json"), "api_football", observed_at="2026-06-01T10:00:00+00:00", apply=True)
                assert first["fixtures"] == 1
                assert odds["odds"] == 8
                assert duplicate["ignored"] >= odds["odds"]
                fixture = session.scalar(select(Fixture).where(Fixture.external_id == "91001"))
                assert fixture is not None
                assert session.scalar(select(func.count()).select_from(RawApiPayload)) == 2
                before_count = session.scalar(select(func.count()).select_from(OddsSnapshot))
                changed = replay_provider_file(session, fixture_path("odds_sample_changed.json"), "api_football", observed_at="2026-06-01T11:00:00+00:00", apply=True)
                after_count = session.scalar(select(func.count()).select_from(OddsSnapshot))
                assert after_count > before_count
                assert changed["odds"] == 5
                before = OddsSnapshotRepository(session).get_latest_odds_as_of(fixture.id, "match_winner", parse_utc("2026-06-01T10:30:00+00:00"))
                after = OddsSnapshotRepository(session).get_latest_odds_as_of(fixture.id, "match_winner", parse_utc("2026-06-01T11:30:00+00:00"))
                assert [str(row.decimal_odds) for row in before if row.selection_key == "home" and row.raw_payload_id == odds["raw_payload_id"]]
                assert any(str(row.decimal_odds) == "2.2400" for row in after if row.selection_key == "home")
                state = FixtureRepository(session).get_fixture_state_as_of(fixture.id, parse_utc("2026-06-01T10:30:00+00:00"))
                assert state["canonical_status"] == "SCHEDULED"
                quality = fixture_quality_from_db(session, fixture.id, now_utc=parse_utc("2026-06-01T11:30:00+00:00"))
                assert quality["status"] == "PASS"
                replayed = replay_run(session, odds["ingestion_run_id"])
                assert replayed["raw_payloads"] == 1
                lock = AdvisoryLockManager(session, "phase2:test")
                assert lock.acquire() is True
                second = AdvisoryLockManager(session, "phase2:test")
                assert second.acquire() is False
                lock.release()
                assert second.acquire() is True
                second.release()
        finally:
            engine.dispose()


def test_legacy_discover_import_dry_run_and_too_large():
    report = discover_legacy_sources(root=".", max_bytes=1000)
    assert report["total_found"] >= 1
    dry = legacy_import_source(None, fixture_path("odds_sample.json"), apply=False, provider="api_football")
    assert dry["dry_run"] is True
    assert dry["objects"] == 1
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "large.json"
        path.write_text("[" + ("0," * 2000) + "0]", encoding="utf-8")
        too_large = legacy_import_source(None, str(path), apply=False, max_bytes=100)
        assert too_large["skipped"] is True


def test_cli_replay_dry_run_and_persistence_demo():
    dry = subprocess.check_output(
        [
            sys.executable,
            "app.py",
            "replay",
            "provider",
            "--file",
            fixture_path("odds_sample.json"),
            "--provider",
            "api_football",
            "--dry-run",
            "--observed-at",
            "2026-06-01T10:00:00+00:00",
        ],
        text=True,
    )
    assert json.loads(dry)["dry_run"] is True
    # Exercise the SQLite fallback regardless of the CI PostgreSQL setting.
    # The separate CI replay smoke test exercises explicit PostgreSQL.
    sqlite_demo_env = dict(os.environ)
    sqlite_demo_env["DATABASE_URL"] = ""
    demo = subprocess.check_output(
        [sys.executable, "app.py", "demo", "postgres-end-to-end", "--json"],
        text=True,
        env=sqlite_demo_env,
    )
    payload = json.loads(demo)
    assert payload["postgres_tested"] is False
    assert payload["sqlite_used"] is True
    assert payload["as_of_before_change_home_odds"] == "2.1000"
    assert payload["as_of_after_change_home_odds"] == "2.2400"


def main():
    old = dict(os.environ)
    try:
        test_config_masking_and_dangerous_real_money_rejected()
        test_hashes_are_stable_and_temporal_policy_is_explicit()
        test_migrations_upgrade_downgrade_upgrade()
        test_normalization_status_decimal_and_invalid_odds()
        test_replay_idempotence_temporal_as_of_quality_and_locks()
        test_legacy_discover_import_dry_run_and_too_large()
        test_cli_replay_dry_run_and_persistence_demo()
        print("test_v10_persistence ok")
    finally:
        os.environ.clear()
        os.environ.update(old)


if __name__ == "__main__":
    main()
