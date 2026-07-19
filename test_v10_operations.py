import asyncio
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from v10.api import app
from v10.config import V10Settings, load_settings
from v10.db.migrations import downgrade_base, migration_status, upgrade_head
from v10.db.models import ScheduledJob
from v10.db.session import create_engine_from_settings, create_session_factory, session_scope
from v10.llm.providers.batch import BatchItem, OpenAIBatchEvaluationService
from v10.llm.providers.openai_responses import OpenAIResponsesProvider
from v10.llm.config import LLMRuntimeConfig
from v10.operations.closing import classify_near_close, select_near_close
from v10.operations.contracts import JobStatus, JobType, ScheduledJobSpec
from v10.operations.experiments import DEFAULT_EXPERIMENT_KEY, ShadowExperimentRepository
from v10.operations.freshness import PrematchFreshnessPolicy
from v10.operations.jobs import ScheduledJobRepository
from v10.operations.material_changes import MaterialChangeDetector
from v10.operations.pipeline import PrematchShadowScanService, operational_shadow_demo_payload
from v10.operations.provider_cache import ProviderCache, provider_cache_key
from v10.operations.quota import ProviderQuotaManager
from v10.operations.scheduler import SchedulerDispatcher
from v10.operations.timeline import generate_prematch_jobs, prematch_phase, reschedule_for_event_time_change
from v10.time import utc_now


def make_db(tmp: str):
    settings = V10Settings(DATABASE_URL=f"sqlite:///{Path(tmp, 'ops.sqlite').as_posix()}")
    assert upgrade_head(settings)["current_revision"] == "20260719_0004"
    engine = create_engine_from_settings(settings)
    return settings, engine, create_session_factory(engine)


def test_timeline_freshness_material_change_and_near_close():
    now = datetime(2026, 7, 19, 12, tzinfo=UTC)
    kickoff = now + timedelta(hours=24)
    jobs = generate_prematch_jobs("fixture_1", kickoff)
    assert {job.job_type for job in jobs} >= {JobType.REFRESH_ODDS, JobType.RUN_LLM_SHADOW_REVIEW, JobType.CAPTURE_NEAR_CLOSE_ODDS, JobType.SETTLE_SIGNALS}
    assert prematch_phase(kickoff, now) == "T24"
    changed = reschedule_for_event_time_change("fixture_1", kickoff, kickoff + timedelta(hours=3))
    assert changed["invalidate_llm_reviews"] is True

    freshness = PrematchFreshnessPolicy(load_settings({})).evaluate({"fixture": now, "odds": now - timedelta(minutes=25)}, "T90", now)
    assert freshness["status"] == "FAIL"
    material = MaterialChangeDetector().detect({"decimal_odds": 2.0}, {"decimal_odds": 2.1})
    assert material["material"] is True

    assert classify_near_close(kickoff, kickoff + timedelta(seconds=1))[0] == "REJECTED_FUTURE_ODDS"
    line = select_near_close(kickoff, [{"id": "ok", "decimal_odds": "2.25", "observed_at": (kickoff - timedelta(minutes=4)).isoformat()}])
    assert line.quality == "EXACT_OR_VERY_NEAR"


def test_scheduler_jobs_leases_cache_quota_and_experiments():
    with tempfile.TemporaryDirectory() as tmp:
        settings, engine, factory = make_db(tmp)
        try:
            due_at = utc_now() - timedelta(minutes=1)
            with session_scope(factory) as session:
                repo = ScheduledJobRepository(session)
                spec = ScheduledJobSpec(JobType.DISCOVER_FIXTURES, due_at=due_at, provider_key="mock")
                first, created = repo.enqueue(spec)
                second, duplicate = repo.enqueue(spec)
                assert created is True
                assert duplicate is False
                assert first.id == second.id
                cache = ProviderCache(session)
                key = provider_cache_key("mock", "fixtures", {"days": 3})
                cache.put("mock", "fixtures", {"days": 3}, {"ok": True}, phase="T24", now=due_at)
                assert cache.get(key, now=due_at)["stale"] is False
                quota = ProviderQuotaManager().record_headers(session, "mock", "fixtures", {"x-ratelimit-remaining": "4"})
                assert quota["estimated_remaining"] == 4
                experiment, created_exp = ShadowExperimentRepository(session).get_or_create(DEFAULT_EXPERIMENT_KEY)
                assert experiment is not None
                assert created_exp is True

            dispatcher = SchedulerDispatcher(factory, worker_id="test-worker")
            dry = dispatcher.tick(max_runtime_seconds=30, max_jobs=5, dry_run=True)
            assert dry["status"] == "DRY_RUN"
            report = dispatcher.tick(max_runtime_seconds=30, max_jobs=5, dry_run=False)
            assert report["jobs_completed"] == 1
            with session_scope(factory) as session:
                row = session.get(ScheduledJob, first.id)
                assert row.status == JobStatus.SUCCEEDED.value
                row.status = JobStatus.RUNNING.value
                row.lease_owner = "dead-worker"
                row.lease_expires_at = due_at - timedelta(minutes=1)
                session.flush()
                recovered = ScheduledJobRepository(session).recover_expired_leases(now=due_at, dry_run=False)
                assert recovered["recovered"] == 1
        finally:
            engine.dispose()
        assert downgrade_base(settings)["current_revision"] is None


def test_openai_batch_payload_openai_provider_no_call_and_api_health():
    service = OpenAIBatchEvaluationService()
    text = service.create_jsonl([BatchItem("case-1", "gpt-5.6-luna", {"input": [{"role": "user", "content": "ping"}]})])
    assert service.validate_jsonl(text)["valid"] is True
    assert service.reconcile_results(text, '{"custom_id":"case-1","response":{}}\n')["matched"] == 1

    provider = OpenAIResponsesProvider(LLMRuntimeConfig(), api_key="")
    payload = provider.build_responses_payload(
        __import__("v10.llm.contracts", fromlist=["StructuredRequest"]).StructuredRequest(
            request_id="req",
            candidate_id="cand",
            fixture_id="fix",
            tier="FAST",
            panel_or_agent="luna",
            model="gpt-5.6-luna",
            reasoning_effort="low",
            schema_name="agent_finding",
            prompt_version="v1",
            packet_hash="hash",
            input_payload={"evidence": []},
        )
    )
    assert payload["text"]["format"]["strict"] is True

    client = TestClient(app)
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200
    assert client.get("/metrics").json()["paid_openai_calls_total"] == 0


def test_pipeline_demo_and_cli_operational_commands():
    payload = asyncio.run(operational_shadow_demo_payload())
    assert payload["telegram_sent"] is False
    assert payload["bookmaker_action"] is False
    assert payload["near_close"]["quality"] == "EXACT_OR_VERY_NEAR"
    assert payload["scenarios"]["post_kickoff_odds_rejected"]["quality"] == "MISSING"

    demo = json.loads(subprocess.check_output([sys.executable, "app.py", "demo", "operational-shadow-end-to-end", "--mock", "--json"], text=True))
    assert demo["costs"]["real_openai_calls"] == 0
    tick = json.loads(subprocess.check_output([sys.executable, "app.py", "scheduler", "tick", "--dry-run"], text=True))
    assert tick.get("dry_run") is True or tick.get("jobs_claimed", 0) == 0
    discover = json.loads(subprocess.check_output([sys.executable, "app.py", "fixtures", "discover", "--days", "3", "--dry-run"], text=True))
    assert discover["network_called"] is False
    scan = json.loads(subprocess.check_output([sys.executable, "app.py", "scan", "prematch", "--fixture-id", "fixture_demo", "--mock-llm", "--dry-run"], text=True))
    assert scan["scan"]["paid_calls"] is False


def test_settings_safety_defaults_phase5():
    settings = load_settings({})
    assert settings.dry_run is True
    assert settings.paper_betting_enabled is True
    assert settings.real_money_actions_enabled is False
    assert settings.llm_enabled is False
    assert settings.llm_shadow_only is True
    assert settings.llm_allow_paid_calls is False
    assert settings.telegram_enabled is False
    assert settings.telegram_disable_send is True
    assert settings.statistical_model_validated_for_signals is False
    assert settings.railway_allow_deploy is False


def main():
    test_timeline_freshness_material_change_and_near_close()
    test_scheduler_jobs_leases_cache_quota_and_experiments()
    test_openai_batch_payload_openai_provider_no_call_and_api_health()
    test_pipeline_demo_and_cli_operational_commands()
    test_settings_safety_defaults_phase5()


if __name__ == "__main__":
    main()
