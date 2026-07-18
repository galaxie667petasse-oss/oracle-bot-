import argparse
import json
import sys
from pathlib import Path

from v10.config import V10Settings, load_settings
from v10.db.migrations import db_doctor, downgrade_base, migration_status, upgrade_head
from v10.db.models import EvaluationRun, ModelVersion, Provider
from v10.db.repositories import FixtureRepository, OddsSnapshotRepository
from v10.db.stat_repositories import ModelRegistryRepository
from v10.db.session import create_engine_from_settings, create_session_factory, session_scope
from v10.demo import build_demo_payload, print_demo_summary
from v10.demo_postgres import print_persistence_demo, run_persistence_demo
from v10.legacy import discover_legacy_sources, legacy_import_source
from v10.quality_db import fixture_quality_from_db
from v10.replay.engine import replay_provider_file, replay_run
from v10.statistics.backtest import walk_forward_from_csv
from v10.statistics.demo import run_statistical_demo
from v10.statistics.training import build_dataset_from_csv, train_from_csv
from v10.time import parse_utc, utc_now
from sqlalchemy import select


def _print_json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _load_settings_or_error() -> V10Settings:
    try:
        return load_settings()
    except Exception as exc:
        raise RuntimeError(f"Configuration invalide: {exc}") from exc


def _doctor(json_output: bool = False) -> int:
    settings = _load_settings_or_error()
    report = settings.safe_report()
    report["project_root"] = str(Path.cwd())
    report["checks"] = {
        "main_py_present": Path("main.py").exists(),
        "dockerfile_present": Path("Dockerfile").exists(),
        "reports_ignored_expected": True,
        "external_data_ignored_expected": True,
    }
    if json_output:
        _print_json(report)
    else:
        print("Doctor Oracle V10")
        _print_json(report)
    return 0 if not report.get("errors") else 1


def _db_settings() -> V10Settings:
    settings = _load_settings_or_error()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL absent: configure PostgreSQL, ou utilise une commande de demo SQLite explicite.")
    return settings


def _session_factory(settings: V10Settings):
    engine = create_engine_from_settings(settings)
    return create_session_factory(engine)


def _cmd_db(args) -> int:
    try:
        settings = _db_settings()
        if args.db_command == "upgrade":
            report = upgrade_head(settings)
        elif args.db_command == "downgrade-base":
            report = downgrade_base(settings)
        elif args.db_command == "status":
            report = migration_status(settings)
        elif args.db_command == "doctor":
            report = db_doctor(settings)
        else:
            raise RuntimeError("Commande db inconnue.")
        _print_json(report)
        return 0
    except Exception as exc:
        print(f"Erreur DB: {exc}")
        return 1


def _cmd_legacy(args) -> int:
    if args.legacy_command == "discover":
        _print_json(discover_legacy_sources(root=args.root, max_bytes=args.max_bytes))
        return 0
    if args.legacy_command == "import":
        apply = bool(args.apply and not args.dry_run)
        if not apply:
            _print_json(legacy_import_source(None, args.source, apply=False, provider=args.provider, max_bytes=args.max_bytes))
            return 0
        try:
            settings = _db_settings()
            with session_scope(_session_factory(settings)) as session:
                report = legacy_import_source(
                    session,
                    args.source,
                    apply=True,
                    provider=args.provider,
                    observed_at=args.observed_at,
                    max_bytes=args.max_bytes,
                )
            _print_json(report)
            return 0 if not report.get("errors") else 1
        except Exception as exc:
            print(f"Erreur legacy import: {exc}")
            return 1
    print("Commande legacy inconnue.")
    return 1


def _cmd_replay(args) -> int:
    if args.replay_command == "provider":
        apply = bool(args.apply and not args.dry_run)
        if not apply:
            report = replay_provider_file(
                None,
                args.file,
                args.provider,
                observed_at=args.observed_at or utc_now(),
                endpoint=args.endpoint or None,
                apply=False,
            )
            _print_json(report)
            return 0 if not report.get("errors") else 1
        try:
            settings = _db_settings()
            with session_scope(_session_factory(settings)) as session:
                report = replay_provider_file(
                    session,
                    args.file,
                    args.provider,
                    observed_at=args.observed_at or utc_now(),
                    endpoint=args.endpoint or None,
                    apply=True,
                )
            _print_json(report)
            return 0 if not report.get("errors") else 1
        except Exception as exc:
            print(f"Erreur replay provider: {exc}")
            return 1
    if args.replay_command == "run":
        try:
            settings = _db_settings()
            with session_scope(_session_factory(settings)) as session:
                report = replay_run(session, args.run_id)
            _print_json(report)
            return 0 if not report.get("errors") else 1
        except Exception as exc:
            print(f"Erreur replay run: {exc}")
            return 1
    print("Commande replay inconnue.")
    return 1


def _cmd_quality(args) -> int:
    try:
        settings = _db_settings()
        with session_scope(_session_factory(settings)) as session:
            report = fixture_quality_from_db(session, args.fixture_id, now_utc=parse_utc(args.as_of) if args.as_of else None)
        _print_json(report)
        return 0 if report.get("status") not in {"FAIL", "CONFLICTING"} else 1
    except Exception as exc:
        print(f"Erreur quality: {exc}")
        return 1


def _odds_row(row) -> dict:
    return {
        "id": row.id,
        "fixture_id": row.fixture_id,
        "bookmaker_id": row.bookmaker_id,
        "market_id": row.market_id,
        "selection_key": row.selection_key,
        "line_value": str(row.line_value) if row.line_value is not None else None,
        "decimal_odds": str(row.decimal_odds),
        "observed_at": row.observed_at.isoformat(),
        "raw_payload_id": row.raw_payload_id,
    }


def _cmd_odds(args) -> int:
    try:
        settings = _db_settings()
        with session_scope(_session_factory(settings)) as session:
            repo = OddsSnapshotRepository(session)
            fixture_id = args.fixture_id
            if args.external_fixture_id:
                provider = session.scalar(select(Provider).where(Provider.key == args.provider))
                if provider is None:
                    raise RuntimeError("provider introuvable")
                fixture = FixtureRepository(session).get_by_external(provider.id, args.fixture_id)
                if fixture is None:
                    raise RuntimeError("fixture externe introuvable")
                fixture_id = fixture.id
            if args.odds_command == "latest":
                rows = repo.get_latest_odds_as_of(fixture_id, args.market, parse_utc(args.as_of) if args.as_of else utc_now())
            elif args.odds_command == "history":
                rows = repo.list_odds_between(
                    fixture_id,
                    parse_utc(args.from_time),
                    parse_utc(args.to_time) if args.to_time else utc_now(),
                )
            else:
                raise RuntimeError("Commande odds inconnue.")
        _print_json({"rows": [_odds_row(row) for row in rows], "count": len(rows), "lab_only": True, "can_influence_picks": False})
        return 0
    except Exception as exc:
        print(f"Erreur odds: {exc}")
        return 1


def _cmd_dataset(args) -> int:
    try:
        if args.dataset_command != "build":
            raise RuntimeError("Commande dataset inconnue.")
        rows, report = build_dataset_from_csv(args.source, start=args.from_date, end=args.to_date, limit=args.limit)
        report["dry_run"] = not bool(args.apply and not args.dry_run)
        report["sample_rows"] = [row.to_dict() for row in rows[: args.preview_rows]]
        if args.apply and not args.dry_run:
            settings = _db_settings()
            with session_scope(_session_factory(settings)) as session:
                run = EvaluationRun(
                    evaluation_type="dataset_build",
                    model_version_ids_json=[],
                    period_start=parse_utc(args.from_date) if args.from_date else None,
                    period_end=parse_utc(args.to_date) if args.to_date else None,
                    competitions_json=report.get("competitions", []),
                    markets_json=[],
                    configuration_json={"source": args.source, "limit": args.limit},
                    dataset_fingerprint=report["dataset_fingerprint"],
                    started_at=utc_now(),
                    finished_at=utc_now(),
                    status="COMPLETED",
                    metrics_json={"rows_included": report["rows_included"], "rows_excluded": report["rows_excluded"]},
                    artifact_paths_json=[],
                    notes="Dataset build metadata only; features are reconstructible from source fingerprint.",
                )
                session.add(run)
                session.flush()
                report["evaluation_run_id"] = run.id
        _print_json(report)
        return 0
    except Exception as exc:
        print(f"Erreur dataset: {exc}")
        return 1


def _cmd_model(args) -> int:
    try:
        if args.model_command == "train":
            apply = bool(args.apply and not args.dry_run)
            report = train_from_csv(args.model, path=args.source, start=args.from_date, end=args.to_date, limit=args.limit)
            report["applied"] = False
            if apply:
                settings = _db_settings()
                with session_scope(_session_factory(settings)) as session:
                    version = ModelRegistryRepository(session).create_version(
                        model_key=args.model,
                        dataset_fingerprint=report["dataset"]["dataset_fingerprint"],
                        match_count=report["match_count"],
                        training_metrics={"training_count": report["training_count"]},
                        validation_metrics=report["metrics"],
                        artifact=report["artifact"],
                        competitions=report["dataset"].get("competitions", []),
                        status="DRAFT",
                    )
                    report["model_version_id"] = version.id
                    report["applied"] = True
            _print_json(report)
            return 0
        if args.model_command == "activate":
            if not args.apply:
                _print_json({"model_version_id": args.model_version_id, "applied": False, "message": "--apply requis pour activer"})
                return 0
            settings = _db_settings()
            with session_scope(_session_factory(settings)) as session:
                row = ModelRegistryRepository(session).activate(args.model_version_id)
                _print_json({"model_version_id": row.id, "status": row.status, "applied": True})
            return 0
        if args.model_command == "reproduce":
            settings = _db_settings()
            with session_scope(_session_factory(settings)) as session:
                row = session.get(ModelVersion, args.model_version_id)
                if row is None:
                    raise RuntimeError("model version introuvable")
                _print_json(
                    {
                        "model_version_id": row.id,
                        "dataset_fingerprint": row.dataset_fingerprint,
                        "status": "NOT_RETRAINED_LOCALLY",
                        "message": "Reproduction complete necessite la meme source historique et sera stricte en phase suivante.",
                        "lab_only": True,
                        "can_influence_picks": False,
                    }
                )
            return 0
        raise RuntimeError("Commande model inconnue.")
    except Exception as exc:
        print(f"Erreur model: {exc}")
        return 1


def _cmd_predict(args) -> int:
    report = {
        "fixture_id": args.fixture_id,
        "as_of": args.as_of,
        "dry_run": True,
        "status": "REQUIRES_ACTIVE_MODEL_AND_FIXTURE_DB",
        "message": "La prediction fixture DB sera activee apres entrainement/persistence de modeles actifs; la demo statistique couvre l'inference offline.",
        "lab_only": True,
        "can_influence_picks": False,
    }
    _print_json(report)
    return 0


def _cmd_backtest(args) -> int:
    try:
        report = walk_forward_from_csv(args.source, start=args.from_date, end=args.to_date, limit=args.limit)
        report["markets_requested"] = args.markets.split(",") if args.markets else []
        report["applied"] = False
        if args.apply and not args.dry_run:
            settings = _db_settings()
            with session_scope(_session_factory(settings)) as session:
                run = EvaluationRun(
                    evaluation_type="walk_forward_backtest",
                    model_version_ids_json=[],
                    period_start=parse_utc(args.from_date) if args.from_date else None,
                    period_end=parse_utc(args.to_date) if args.to_date else None,
                    competitions_json=report.get("dataset", {}).get("competitions", []),
                    markets_json=report["markets_requested"],
                    configuration_json={"source": args.source, "limit": args.limit},
                    dataset_fingerprint=report.get("dataset", {}).get("dataset_fingerprint", ""),
                    started_at=utc_now(),
                    finished_at=utc_now(),
                    status="COMPLETED",
                    metrics_json=report.get("metrics", {}),
                    artifact_paths_json=[],
                    notes="Deterministic V10 walk-forward dry/paper evaluation.",
                )
                session.add(run)
                session.flush()
                report["evaluation_run_id"] = run.id
                report["applied"] = True
        _print_json(report)
        return 0
    except Exception as exc:
        print(f"Erreur backtest: {exc}")
        return 1


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="CLI locale additive Oracle V10.")
    sub = parser.add_subparsers(dest="command")

    doctor = sub.add_parser("doctor")
    doctor.add_argument("--json", action="store_true")

    cfg = sub.add_parser("config")
    cfg_sub = cfg.add_subparsers(dest="config_command")
    cfg_sub.add_parser("validate")

    db = sub.add_parser("db")
    db_sub = db.add_subparsers(dest="db_command")
    db_sub.add_parser("upgrade")
    db_sub.add_parser("status")
    db_sub.add_parser("doctor")
    db_sub.add_parser("downgrade-base")

    legacy = sub.add_parser("legacy")
    legacy_sub = legacy.add_subparsers(dest="legacy_command")
    discover = legacy_sub.add_parser("discover")
    discover.add_argument("--root", default=".")
    discover.add_argument("--max-bytes", type=int, default=5_000_000)
    legacy_import = legacy_sub.add_parser("import")
    legacy_import.add_argument("--source", required=True)
    legacy_import.add_argument("--provider", default="")
    legacy_import.add_argument("--observed-at", default="")
    legacy_import.add_argument("--max-bytes", type=int, default=5_000_000)
    legacy_import.add_argument("--dry-run", action="store_true")
    legacy_import.add_argument("--apply", action="store_true")

    replay = sub.add_parser("replay")
    replay_sub = replay.add_subparsers(dest="replay_command")
    replay_provider = replay_sub.add_parser("provider")
    replay_provider.add_argument("--file", required=True)
    replay_provider.add_argument("--provider", required=True)
    replay_provider.add_argument("--endpoint", default="")
    replay_provider.add_argument("--observed-at", default="")
    replay_provider.add_argument("--dry-run", action="store_true")
    replay_provider.add_argument("--apply", action="store_true")
    replay_run_parser = replay_sub.add_parser("run")
    replay_run_parser.add_argument("--run-id", required=True)

    quality = sub.add_parser("quality")
    quality_sub = quality.add_subparsers(dest="quality_command")
    fixture_quality = quality_sub.add_parser("fixture")
    fixture_quality.add_argument("--fixture-id", required=True)
    fixture_quality.add_argument("--as-of", default="")
    fixture_quality.add_argument("--json", action="store_true")

    odds = sub.add_parser("odds")
    odds_sub = odds.add_subparsers(dest="odds_command")
    latest = odds_sub.add_parser("latest")
    latest.add_argument("--fixture-id", required=True)
    latest.add_argument("--external-fixture-id", action="store_true")
    latest.add_argument("--provider", default="api_football")
    latest.add_argument("--market", default="all")
    latest.add_argument("--as-of", default="")
    history = odds_sub.add_parser("history")
    history.add_argument("--fixture-id", required=True)
    history.add_argument("--external-fixture-id", action="store_true")
    history.add_argument("--provider", default="api_football")
    history.add_argument("--from-time", default="1970-01-01T00:00:00+00:00")
    history.add_argument("--to-time", default="")

    dataset = sub.add_parser("dataset")
    dataset_sub = dataset.add_subparsers(dest="dataset_command")
    dataset_build = dataset_sub.add_parser("build")
    dataset_build.add_argument("--from", dest="from_date", default="")
    dataset_build.add_argument("--to", dest="to_date", default="")
    dataset_build.add_argument("--source", default="data/MATCHES.csv")
    dataset_build.add_argument("--limit", type=int, default=None)
    dataset_build.add_argument("--preview-rows", type=int, default=2)
    dataset_build.add_argument("--dry-run", action="store_true")
    dataset_build.add_argument("--apply", action="store_true")

    model = sub.add_parser("model")
    model_sub = model.add_subparsers(dest="model_command")
    model_train = model_sub.add_parser("train")
    model_train.add_argument("--model", required=True)
    model_train.add_argument("--from", dest="from_date", default="")
    model_train.add_argument("--to", dest="to_date", default="")
    model_train.add_argument("--source", default="data/MATCHES.csv")
    model_train.add_argument("--limit", type=int, default=500)
    model_train.add_argument("--dry-run", action="store_true")
    model_train.add_argument("--apply", action="store_true")
    model_activate = model_sub.add_parser("activate")
    model_activate.add_argument("--model-version-id", required=True)
    model_activate.add_argument("--apply", action="store_true")
    model_reproduce = model_sub.add_parser("reproduce")
    model_reproduce.add_argument("--model-version-id", required=True)

    predict = sub.add_parser("predict")
    predict_sub = predict.add_subparsers(dest="predict_command")
    predict_fixture = predict_sub.add_parser("fixture")
    predict_fixture.add_argument("--fixture-id", required=True)
    predict_fixture.add_argument("--as-of", required=True)
    predict_fixture.add_argument("--dry-run", action="store_true")
    predict_fixture.add_argument("--apply", action="store_true")

    backtest = sub.add_parser("backtest")
    backtest_sub = backtest.add_subparsers(dest="backtest_command")
    backtest_run = backtest_sub.add_parser("run")
    backtest_run.add_argument("--from", dest="from_date", default="")
    backtest_run.add_argument("--to", dest="to_date", default="")
    backtest_run.add_argument("--markets", default="1x2,ou25,btts")
    backtest_run.add_argument("--source", default="data/MATCHES.csv")
    backtest_run.add_argument("--limit", type=int, default=240)
    backtest_run.add_argument("--dry-run", action="store_true")
    backtest_run.add_argument("--apply", action="store_true")

    demo = sub.add_parser("demo")
    demo_sub = demo.add_subparsers(dest="demo_command")
    e2e = demo_sub.add_parser("end-to-end")
    e2e.add_argument("--json", action="store_true")
    pg = demo_sub.add_parser("postgres-end-to-end")
    pg.add_argument("--json", action="store_true")
    pg.add_argument("--database-url", default="")
    stats = demo_sub.add_parser("statistical-end-to-end")
    stats.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "doctor":
            return _doctor(json_output=args.json)
        if args.command == "config" and args.config_command == "validate":
            return _doctor(json_output=True)
        if args.command == "db":
            return _cmd_db(args)
        if args.command == "legacy":
            return _cmd_legacy(args)
        if args.command == "replay":
            return _cmd_replay(args)
        if args.command == "quality" and args.quality_command == "fixture":
            return _cmd_quality(args)
        if args.command == "odds":
            return _cmd_odds(args)
        if args.command == "dataset" and args.dataset_command == "build":
            return _cmd_dataset(args)
        if args.command == "model":
            return _cmd_model(args)
        if args.command == "predict" and args.predict_command == "fixture":
            return _cmd_predict(args)
        if args.command == "backtest" and args.backtest_command == "run":
            return _cmd_backtest(args)
        if args.command == "demo" and args.demo_command == "end-to-end":
            payload = build_demo_payload()
            if args.json:
                _print_json(payload)
            else:
                print_demo_summary(payload)
            return 0
        if args.command == "demo" and args.demo_command == "postgres-end-to-end":
            report = run_persistence_demo(database_url=args.database_url or None)
            if args.json:
                _print_json(report)
            else:
                print_persistence_demo(report)
            return 0
        if args.command == "demo" and args.demo_command == "statistical-end-to-end":
            report = run_statistical_demo()
            if args.json:
                _print_json(report)
            else:
                _print_json(report)
            return 0
        print("Commande inconnue. Utiliser: app doctor | app db status | app replay provider | app demo end-to-end | app demo statistical-end-to-end")
        return 1
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
