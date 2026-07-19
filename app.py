import argparse
import asyncio
import json
import sys
from datetime import timedelta
from decimal import Decimal
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
from v10.llm.budgets.manager import BudgetManager
from v10.llm.config import LLMRuntimeConfig
from v10.llm.evaluation.dataset import synthetic_candidate
from v10.llm.evaluation.runner import run_mock_evaluation
from v10.llm.demo import run_llm_shadow_demo
from v10.llm.evidence.packet_builder import CandidateEvidencePacketBuilder
from v10.llm.orchestrator import LLMOrchestrator
from v10.llm.providers.mock import MockLLMProvider
from v10.llm.providers.openai_responses import OpenAIResponsesProvider
from v10.llm.providers.replay import ReplayLLMProvider
from v10.llm.registry import LLMModelRegistry
from v10.llm.routing import ComplexityRouter
from sqlalchemy import select
from v10.operations.backtest_compare import compare_backtest_from_csv
from v10.operations.contracts import JobStatus
from v10.operations.experiments import DEFAULT_EXPERIMENT_KEY, ShadowExperimentRepository, dry_run_experiment_status
from v10.operations.jobs import ScheduledJobRepository, job_to_dict
from v10.operations.pipeline import PrematchShadowScanService, operational_shadow_demo_payload
from v10.operations.providers import MockPrematchProvider
from v10.operations.quota import ProviderQuotaManager
from v10.operations.scheduler import SchedulerDispatcher
from v10.operations.timeline import generate_prematch_jobs


def _print_json(data) -> None:
    print(json.dumps(data, ensure_ascii=True, indent=2, default=str))


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
        if args.backtest_command == "compare":
            report = compare_backtest_from_csv(
                args.source,
                start=args.from_date,
                end=args.to_date,
                limit=args.limit,
                include_market_baseline=args.include_market_baseline,
            )
            report["markets_requested"] = args.markets.split(",") if args.markets else []
            report["walk_forward"] = bool(args.walk_forward)
            report["report_path"] = args.report
            report["applied"] = bool(args.apply and not args.dry_run)
            if report["applied"]:
                settings = _db_settings()
                with session_scope(_session_factory(settings)) as session:
                    run = EvaluationRun(
                        evaluation_type="phase5_backtest_compare",
                        model_version_ids_json=[],
                        period_start=parse_utc(args.from_date) if args.from_date else None,
                        period_end=parse_utc(args.to_date) if args.to_date else None,
                        competitions_json=report.get("dataset", {}).get("competitions", []),
                        markets_json=report["markets_requested"],
                        configuration_json={"source": args.source, "limit": args.limit, "include_market_baseline": args.include_market_baseline},
                        dataset_fingerprint=report.get("dataset", {}).get("dataset_fingerprint", ""),
                        started_at=utc_now(),
                        finished_at=utc_now(),
                        status="COMPLETED",
                        metrics_json=report.get("metrics", {}),
                        artifact_paths_json=[],
                        notes="Phase 5 compare baseline marche vs modeles statistiques. No profit claim.",
                    )
                    session.add(run)
                    session.flush()
                    report["evaluation_run_id"] = run.id
            _print_json(report)
            return 0
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


def _cmd_scheduler(args) -> int:
    try:
        if args.scheduler_command == "tick":
            if args.dry_run and not _load_settings_or_error().database_url:
                _print_json({"status": "DRY_RUN", "database_configured": False, "jobs_due": 0, "message": "DATABASE_URL absent; aucun claim effectue.", "paper_only": True})
                return 0
            settings = _db_settings()
            dispatcher = SchedulerDispatcher(_session_factory(settings))
            report = dispatcher.tick(args.max_runtime_seconds, args.max_jobs, settings.scheduler_shutdown_margin_seconds, dry_run=args.dry_run)
            _print_json(report)
            return 0
        if args.scheduler_command in {"status", "due", "recover-leases"}:
            settings = _db_settings()
            with session_scope(_session_factory(settings)) as session:
                repo = ScheduledJobRepository(session)
                if args.scheduler_command == "status":
                    jobs = repo.list_jobs(limit=200)
                    counts: dict[str, int] = {}
                    for job in jobs:
                        counts[job.status] = counts.get(job.status, 0) + 1
                    _print_json({"jobs_by_status": counts, "sample": [job_to_dict(job) for job in jobs[:10]], "paper_only": True})
                elif args.scheduler_command == "due":
                    jobs = repo.list_due(utc_now(), limit=args.limit)
                    _print_json({"due": [job_to_dict(job) for job in jobs], "count": len(jobs), "paper_only": True})
                else:
                    _print_json(repo.recover_expired_leases(dry_run=args.dry_run))
            return 0
        raise RuntimeError("Commande scheduler inconnue.")
    except Exception as exc:
        print(f"Erreur scheduler: {exc}")
        return 1


def _cmd_jobs(args) -> int:
    try:
        settings = _db_settings()
        with session_scope(_session_factory(settings)) as session:
            repo = ScheduledJobRepository(session)
            if args.jobs_command == "list":
                rows = repo.list_jobs(status=args.status or None, limit=args.limit)
                _print_json({"jobs": [job_to_dict(row) for row in rows], "count": len(rows)})
            elif args.jobs_command == "inspect":
                row = repo.get(args.job_id)
                _print_json({"found": bool(row), "job": job_to_dict(row) if row else None})
            elif args.jobs_command == "retry":
                _print_json(repo.retry(args.job_id, dry_run=args.dry_run or not args.apply))
            elif args.jobs_command == "cancel":
                _print_json(repo.cancel(args.job_id, dry_run=args.dry_run or not args.apply))
            else:
                raise RuntimeError("Commande jobs inconnue.")
        return 0
    except Exception as exc:
        print(f"Erreur jobs: {exc}")
        return 1


def _cmd_fixtures(args) -> int:
    try:
        if args.fixtures_command == "discover":
            start = utc_now()
            fixtures = MockPrematchProvider(base_time=start).discover_fixtures(start, start + timedelta(days=args.days))
            _print_json({"fixtures": fixtures, "dry_run": True, "provider": "mock_provider", "network_called": False})
            return 0
        if args.fixtures_command == "schedule":
            event_time = parse_utc(args.event_time) if args.event_time else utc_now() + timedelta(days=1)
            specs = generate_prematch_jobs(args.fixture_id, event_time)
            if args.apply and not args.dry_run:
                settings = _db_settings()
                with session_scope(_session_factory(settings)) as session:
                    report = ScheduledJobRepository(session).enqueue_many(specs)
            else:
                report = {"inserted": 0, "ignored": 0, "dry_run": True, "jobs": [spec.to_dict() for spec in specs]}
            _print_json(report)
            return 0
        raise RuntimeError("Commande fixtures inconnue.")
    except Exception as exc:
        print(f"Erreur fixtures: {exc}")
        return 1


def _cmd_scan(args) -> int:
    try:
        if args.scan_command == "prematch":
            report = asyncio.run(PrematchShadowScanService().run_mock_scan(fixture_id=args.fixture_id, as_of=parse_utc(args.as_of) if args.as_of else utc_now(), mock_scenario="valid" if args.mock_llm else "insufficient"))
            _print_json(report)
            return 0
        if args.scan_command == "due":
            report = asyncio.run(PrematchShadowScanService().run_mock_scan(fixture_id="fixture_due_mock", as_of=utc_now(), mock_scenario="valid" if args.mock_llm else "insufficient"))
            report["source"] = "mock_due_scan"
            _print_json(report)
            return 0
        raise RuntimeError("Commande scan inconnue.")
    except Exception as exc:
        print(f"Erreur scan: {exc}")
        return 1


def _cmd_providers(args) -> int:
    try:
        if args.providers_command == "health":
            _print_json({"providers": [{"provider": "api_football", "status": "not_called", "network_called": False}, {"provider": "the_odds_api", "status": "not_called", "network_called": False}], "paper_only": True})
            return 0
        if args.providers_command == "quotas":
            decision = ProviderQuotaManager().allow_request(None, "fixtures_under_24_hours")
            _print_json({"quotas": [], "decision": decision.__dict__, "limits_invented": False})
            return 0
        raise RuntimeError("Commande providers inconnue.")
    except Exception as exc:
        print(f"Erreur providers: {exc}")
        return 1


def _cmd_experiments(args) -> int:
    try:
        key = args.key or DEFAULT_EXPERIMENT_KEY
        if args.experiments_command == "create":
            if args.apply and not args.dry_run:
                settings = _db_settings()
                with session_scope(_session_factory(settings)) as session:
                    experiment, created = ShadowExperimentRepository(session).get_or_create(key, apply=True)
                    _print_json({"experiment_id": experiment.id if experiment else None, "created": created, "applied": True})
            else:
                _print_json(dry_run_experiment_status(key))
            return 0
        settings = _db_settings()
        with session_scope(_session_factory(settings)) as session:
            report = ShadowExperimentRepository(session).report(key)
        _print_json(report)
        return 0
    except Exception as exc:
        print(f"Erreur experiments: {exc}")
        return 1
    except Exception as exc:
        print(f"Erreur backtest: {exc}")
        return 1


def _llm_config() -> LLMRuntimeConfig:
    return LLMRuntimeConfig.from_settings(_load_settings_or_error())


def _candidate_from_id(candidate_id: str) -> dict:
    case_id = candidate_id.replace("cand_", "") if candidate_id.startswith("cand_") else "valid"
    candidate = synthetic_candidate(case_id if case_id in {"deterministic_reject", "hard_veto", "insufficient", "shadow_accept", "stale_odds", "negative_ev"} else "valid")
    candidate["candidate_id"] = candidate_id
    return candidate


def _cmd_llm(args) -> int:
    try:
        config = _llm_config()
        registry = LLMModelRegistry(config)
        if args.llm_command == "doctor":
            report = config.safe_report()
            report["openai_sdk_installed"] = _openai_sdk_version()
            report["paid_call_possible_without_allow_paid"] = config.can_call_paid(False)
            _print_json(report)
            return 0
        if args.llm_command == "models":
            _print_json(registry.availability_report())
            return 0
        if args.llm_command == "budget" and args.budget_command == "status":
            manager = BudgetManager(config.daily_budget_usd, config.scan_budget_usd, config.fixture_budget_usd)
            _print_json(manager.status())
            return 0
        if args.llm_command == "prompts" and args.prompts_command == "validate":
            prompt_root = Path("prompts")
            files = sorted(str(path) for path in prompt_root.rglob("*.md")) if prompt_root.exists() else []
            _print_json({"prompt_files": files, "valid": bool(files), "lab_only": True, "can_influence_picks": False})
            return 0
        if args.llm_command == "cache" and args.cache_command == "status":
            from v10.llm.cache.repository import InMemoryLLMCache

            _print_json(InMemoryLLMCache().status())
            return 0
        if args.llm_command == "plan":
            packet = CandidateEvidencePacketBuilder().build(_candidate_from_id(args.candidate_id), utc_now())
            plan = ComplexityRouter().plan(packet, portfolio_candidate_count=2, top_finalist=True)
            _print_json({"candidate_id": args.candidate_id, "packet_hash": packet.packet_hash, "plan": plan.__dict__, "paid_calls": False})
            return 0
        if args.llm_command == "analyze":
            if args.replay:
                provider = ReplayLLMProvider(args.replay)
            elif args.mock or not args.allow_paid:
                provider = MockLLMProvider(scenario=args.mock_scenario)
            else:
                provider = OpenAIResponsesProvider(config, api_key=_load_settings_or_error().openai_api_key)
            budget = BudgetManager(
                Decimal(str(args.max_cost_usd)) if args.allow_paid else Decimal("0"),
                Decimal(str(args.max_cost_usd)) if args.allow_paid else Decimal("0"),
                Decimal(str(args.max_cost_usd)) if args.allow_paid else Decimal("0"),
            )
            orchestrator = LLMOrchestrator(config, provider, budget=budget)
            result = asyncio.run(orchestrator.analyze_candidate(_candidate_from_id(args.candidate_id), utc_now(), allow_paid=args.allow_paid, portfolio_candidate_count=2, top_finalist=True))
            result["shadow"] = bool(args.shadow)
            result["paid_calls_allowed_cli"] = bool(args.allow_paid)
            _print_json(result)
            return 0
        if args.llm_command == "evaluate":
            report = asyncio.run(run_mock_evaluation())
            if args.ablation:
                from v10.llm.evaluation.ablation import ABLATION_CONFIGS

                report["ablation_configs"] = ABLATION_CONFIGS
            _print_json(report)
            return 0
        if args.llm_command == "benchmark-routing":
            cases = ["cand_valid", "cand_negative_ev", "cand_stale_odds", "cand_shadow_accept", "cand_insufficient"]
            plans = []
            for candidate_id in cases:
                packet = CandidateEvidencePacketBuilder().build(_candidate_from_id(candidate_id), utc_now())
                plans.append({"candidate_id": candidate_id, "plan": ComplexityRouter().plan(packet, portfolio_candidate_count=2, top_finalist=True).__dict__})
            _print_json({"plans": plans, "paid_calls": False, "lab_only": True, "can_influence_picks": False})
            return 0
        if args.llm_command == "smoke":
            if not args.allow_paid:
                _print_json({"status": "BLOCKED", "reason": "--allow-paid requis", "paid_call_executed": False})
                return 0
            if not config.can_call_paid(True):
                _print_json({"status": "BLOCKED", "reason": "LLM flags et budget positifs requis", "paid_call_executed": False})
                return 0
            _print_json({"status": "READY_BUT_NOT_EXECUTED_BY_DEFAULT", "tier": args.tier, "paid_call_executed": False})
            return 0
        raise RuntimeError("Commande llm inconnue.")
    except Exception as exc:
        print(f"Erreur llm: {exc}")
        return 1


def _cmd_decision(args) -> int:
    if args.decision_command == "review":
        packet = CandidateEvidencePacketBuilder().build(_candidate_from_id(args.candidate_id), utc_now())
        plan = ComplexityRouter().plan(packet, portfolio_candidate_count=1, top_finalist=True)
        _print_json({"candidate_id": args.candidate_id, "packet_hash": packet.packet_hash, "plan": plan.__dict__, "review_status": "PLANNED_ONLY", "paid_calls": False})
        return 0
    print("Commande decision inconnue.")
    return 1


def _openai_sdk_version() -> str:
    try:
        import openai  # type: ignore

        return str(getattr(openai, "__version__", "unknown"))
    except Exception:
        return "not_installed"


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
    backtest_compare = backtest_sub.add_parser("compare")
    backtest_compare.add_argument("--from", dest="from_date", default="")
    backtest_compare.add_argument("--to", dest="to_date", default="")
    backtest_compare.add_argument("--markets", default="1x2,ou25,btts")
    backtest_compare.add_argument("--source", default="data/MATCHES.csv")
    backtest_compare.add_argument("--limit", type=int, default=5000)
    backtest_compare.add_argument("--walk-forward", action="store_true")
    backtest_compare.add_argument("--include-market-baseline", action="store_true")
    backtest_compare.add_argument("--report", default="")
    backtest_compare.add_argument("--dry-run", action="store_true")
    backtest_compare.add_argument("--apply", action="store_true")

    scheduler = sub.add_parser("scheduler")
    scheduler_sub = scheduler.add_subparsers(dest="scheduler_command")
    scheduler_tick = scheduler_sub.add_parser("tick")
    scheduler_tick.add_argument("--max-runtime-seconds", type=int, default=240)
    scheduler_tick.add_argument("--max-jobs", type=int, default=50)
    scheduler_tick.add_argument("--dry-run", action="store_true")
    scheduler_sub.add_parser("status")
    scheduler_due = scheduler_sub.add_parser("due")
    scheduler_due.add_argument("--limit", type=int, default=50)
    scheduler_recover = scheduler_sub.add_parser("recover-leases")
    scheduler_recover.add_argument("--dry-run", action="store_true")
    scheduler_recover.add_argument("--apply", action="store_true")

    jobs = sub.add_parser("jobs")
    jobs_sub = jobs.add_subparsers(dest="jobs_command")
    jobs_list = jobs_sub.add_parser("list")
    jobs_list.add_argument("--status", default="")
    jobs_list.add_argument("--limit", type=int, default=100)
    jobs_inspect = jobs_sub.add_parser("inspect")
    jobs_inspect.add_argument("--job-id", required=True)
    jobs_retry = jobs_sub.add_parser("retry")
    jobs_retry.add_argument("--job-id", required=True)
    jobs_retry.add_argument("--dry-run", action="store_true")
    jobs_retry.add_argument("--apply", action="store_true")
    jobs_cancel = jobs_sub.add_parser("cancel")
    jobs_cancel.add_argument("--job-id", required=True)
    jobs_cancel.add_argument("--dry-run", action="store_true")
    jobs_cancel.add_argument("--apply", action="store_true")

    fixtures = sub.add_parser("fixtures")
    fixtures_sub = fixtures.add_subparsers(dest="fixtures_command")
    fixtures_discover = fixtures_sub.add_parser("discover")
    fixtures_discover.add_argument("--days", type=int, default=3)
    fixtures_discover.add_argument("--dry-run", action="store_true")
    fixtures_schedule = fixtures_sub.add_parser("schedule")
    fixtures_schedule.add_argument("--fixture-id", required=True)
    fixtures_schedule.add_argument("--event-time", default="")
    fixtures_schedule.add_argument("--dry-run", action="store_true")
    fixtures_schedule.add_argument("--apply", action="store_true")

    scan = sub.add_parser("scan")
    scan_sub = scan.add_subparsers(dest="scan_command")
    scan_prematch = scan_sub.add_parser("prematch")
    scan_prematch.add_argument("--fixture-id", required=True)
    scan_prematch.add_argument("--as-of", default="")
    scan_prematch.add_argument("--mock-llm", action="store_true")
    scan_prematch.add_argument("--dry-run", action="store_true")
    scan_due = scan_sub.add_parser("due")
    scan_due.add_argument("--mock-llm", action="store_true")
    scan_due.add_argument("--dry-run", action="store_true")

    providers = sub.add_parser("providers")
    providers_sub = providers.add_subparsers(dest="providers_command")
    providers_sub.add_parser("health")
    providers_sub.add_parser("quotas")

    experiments = sub.add_parser("experiments")
    experiments_sub = experiments.add_subparsers(dest="experiments_command")
    experiments_create = experiments_sub.add_parser("create")
    experiments_create.add_argument("--key", default=DEFAULT_EXPERIMENT_KEY)
    experiments_create.add_argument("--dry-run", action="store_true")
    experiments_create.add_argument("--apply", action="store_true")
    experiments_status = experiments_sub.add_parser("status")
    experiments_status.add_argument("--key", default=DEFAULT_EXPERIMENT_KEY)
    experiments_report = experiments_sub.add_parser("report")
    experiments_report.add_argument("--key", default=DEFAULT_EXPERIMENT_KEY)

    llm = sub.add_parser("llm")
    llm_sub = llm.add_subparsers(dest="llm_command")
    llm_sub.add_parser("doctor")
    llm_sub.add_parser("models")
    llm_budget = llm_sub.add_parser("budget")
    llm_budget_sub = llm_budget.add_subparsers(dest="budget_command")
    llm_budget_sub.add_parser("status")
    llm_prompts = llm_sub.add_parser("prompts")
    llm_prompts_sub = llm_prompts.add_subparsers(dest="prompts_command")
    llm_prompts_sub.add_parser("validate")
    llm_cache = llm_sub.add_parser("cache")
    llm_cache_sub = llm_cache.add_subparsers(dest="cache_command")
    llm_cache_sub.add_parser("status")
    llm_plan = llm_sub.add_parser("plan")
    llm_plan.add_argument("--candidate-id", required=True)
    llm_analyze = llm_sub.add_parser("analyze")
    llm_analyze.add_argument("--candidate-id", required=True)
    llm_analyze.add_argument("--mock", action="store_true")
    llm_analyze.add_argument("--mock-scenario", default="valid")
    llm_analyze.add_argument("--replay", default="")
    llm_analyze.add_argument("--shadow", action="store_true")
    llm_analyze.add_argument("--allow-paid", action="store_true")
    llm_analyze.add_argument("--max-cost-usd", type=float, default=0.0)
    llm_eval = llm_sub.add_parser("evaluate")
    llm_eval.add_argument("--dataset", default="tests/fixtures/llm_eval")
    llm_eval.add_argument("--mock", action="store_true")
    llm_eval.add_argument("--ablation", action="store_true")
    llm_bench = llm_sub.add_parser("benchmark-routing")
    llm_bench.add_argument("--dataset", default="tests/fixtures/llm_eval")
    llm_bench.add_argument("--mock", action="store_true")
    llm_smoke = llm_sub.add_parser("smoke")
    llm_smoke.add_argument("--tier", default="fast")
    llm_smoke.add_argument("--allow-paid", action="store_true")
    llm_smoke.add_argument("--max-cost-usd", type=float, default=0.0)

    decision = sub.add_parser("decision")
    decision_sub = decision.add_subparsers(dest="decision_command")
    decision_review = decision_sub.add_parser("review")
    decision_review.add_argument("--candidate-id", required=True)

    demo = sub.add_parser("demo")
    demo_sub = demo.add_subparsers(dest="demo_command")
    e2e = demo_sub.add_parser("end-to-end")
    e2e.add_argument("--json", action="store_true")
    pg = demo_sub.add_parser("postgres-end-to-end")
    pg.add_argument("--json", action="store_true")
    pg.add_argument("--database-url", default="")
    stats = demo_sub.add_parser("statistical-end-to-end")
    stats.add_argument("--json", action="store_true")
    llm_demo = demo_sub.add_parser("llm-shadow-end-to-end")
    llm_demo.add_argument("--mock", action="store_true")
    llm_demo.add_argument("--json", action="store_true")
    operational_demo = demo_sub.add_parser("operational-shadow-end-to-end")
    operational_demo.add_argument("--mock", action="store_true")
    operational_demo.add_argument("--json", action="store_true")
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
        if args.command == "backtest" and args.backtest_command in {"run", "compare"}:
            return _cmd_backtest(args)
        if args.command == "scheduler":
            return _cmd_scheduler(args)
        if args.command == "jobs":
            return _cmd_jobs(args)
        if args.command == "fixtures":
            return _cmd_fixtures(args)
        if args.command == "scan":
            return _cmd_scan(args)
        if args.command == "providers":
            return _cmd_providers(args)
        if args.command == "experiments":
            return _cmd_experiments(args)
        if args.command == "llm":
            return _cmd_llm(args)
        if args.command == "decision":
            return _cmd_decision(args)
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
        if args.command == "demo" and args.demo_command == "llm-shadow-end-to-end":
            report = asyncio.run(run_llm_shadow_demo())
            _print_json(report)
            return 0
        if args.command == "demo" and args.demo_command == "operational-shadow-end-to-end":
            report = asyncio.run(operational_shadow_demo_payload())
            _print_json(report)
            return 0
        print("Commande inconnue. Utiliser: app doctor | app db status | app scheduler tick | app replay provider | app demo operational-shadow-end-to-end")
        return 1
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
