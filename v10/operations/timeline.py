from __future__ import annotations

from datetime import datetime, timedelta

from v10.time import ensure_utc

from .contracts import JobType, PrematchPhase, ScheduledJobSpec


def _spec(job_type: JobType, fixture_id: str, event_time: datetime, due_at: datetime, phase: PrematchPhase, priority: int) -> ScheduledJobSpec:
    return ScheduledJobSpec(
        job_type=job_type,
        fixture_id=fixture_id,
        due_at=due_at,
        priority=priority,
        phase=phase.value,
        payload={"event_time": event_time.isoformat(), "phase": phase.value, "paper_only": True},
    )


def prematch_phase(event_time: datetime, now: datetime) -> str:
    event_time = ensure_utc(event_time, "event_time")
    now = ensure_utc(now, "now")
    minutes = (event_time - now).total_seconds() / 60
    if minutes > 72 * 60:
        return PrematchPhase.FAR.value
    if minutes > 24 * 60:
        return PrematchPhase.T72.value
    if minutes > 6 * 60:
        return PrematchPhase.T24.value
    if minutes > 90:
        return PrematchPhase.T6.value
    if minutes > 30:
        return PrematchPhase.T90.value
    if minutes > 10:
        return PrematchPhase.T30.value
    if minutes >= 0:
        return PrematchPhase.T10.value
    return PrematchPhase.RESULT_CHECK.value


def generate_prematch_jobs(fixture_id: str, event_time: datetime, now: datetime | None = None) -> list[ScheduledJobSpec]:
    event_time = ensure_utc(event_time, "event_time")
    jobs: list[ScheduledJobSpec] = []

    def add(offset: timedelta, phase: PrematchPhase, job_types: list[JobType], priority: int) -> None:
        due_at = event_time + offset
        for job_type in job_types:
            jobs.append(_spec(job_type, fixture_id, event_time, due_at, phase, priority))

    add(-timedelta(hours=72), PrematchPhase.T72, [JobType.REFRESH_FIXTURE, JobType.REFRESH_ODDS], 80)
    add(
        -timedelta(hours=24),
        PrematchPhase.T24,
        [
            JobType.REFRESH_FIXTURE,
            JobType.REFRESH_ODDS,
            JobType.REFRESH_TEAM_STATISTICS,
            JobType.REFRESH_STANDINGS,
            JobType.BUILD_FEATURES,
            JobType.GENERATE_PREDICTIONS,
        ],
        60,
    )
    add(
        -timedelta(hours=6),
        PrematchPhase.T6,
        [JobType.REFRESH_ODDS, JobType.REFRESH_CONTEXT, JobType.REFRESH_AVAILABILITY, JobType.BUILD_FEATURES, JobType.GENERATE_PREDICTIONS, JobType.GENERATE_CANDIDATES],
        45,
    )
    add(
        -timedelta(minutes=90),
        PrematchPhase.T90,
        [JobType.REFRESH_ODDS, JobType.REFRESH_AVAILABILITY, JobType.REFRESH_LINEUPS, JobType.GENERATE_PREDICTIONS, JobType.GENERATE_CANDIDATES, JobType.RUN_LLM_SHADOW_REVIEW],
        30,
    )
    add(
        -timedelta(minutes=30),
        PrematchPhase.T30,
        [JobType.REFRESH_ODDS, JobType.REFRESH_LINEUPS, JobType.GENERATE_PREDICTIONS, JobType.GENERATE_CANDIDATES, JobType.RUN_LLM_SHADOW_REVIEW],
        20,
    )
    add(
        -timedelta(minutes=10),
        PrematchPhase.T10,
        [JobType.REFRESH_FIXTURE, JobType.REFRESH_ODDS, JobType.REFRESH_LINEUPS, JobType.GENERATE_CANDIDATES, JobType.RUN_LLM_SHADOW_REVIEW],
        10,
    )
    add(-timedelta(seconds=30), PrematchPhase.NEAR_CLOSE, [JobType.CAPTURE_NEAR_CLOSE_ODDS], 5)
    add(timedelta(hours=3), PrematchPhase.RESULT_CHECK, [JobType.REFRESH_RESULTS, JobType.SETTLE_SIGNALS], 15)
    add(timedelta(hours=6), PrematchPhase.RECONCILIATION, [JobType.RECONCILE_RESULTS, JobType.CALCULATE_CLV], 30)
    add(timedelta(hours=24), PrematchPhase.RECONCILIATION, [JobType.REFRESH_RESULTS, JobType.RECONCILE_RESULTS, JobType.GENERATE_DAILY_REPORT], 60)
    return sorted(jobs, key=lambda item: (item.due_at, item.priority, item.job_type.value))


def reschedule_for_event_time_change(fixture_id: str, old_event_time: datetime, new_event_time: datetime) -> dict:
    old = [job.to_dict() for job in generate_prematch_jobs(fixture_id, old_event_time)]
    new = [job.to_dict() for job in generate_prematch_jobs(fixture_id, new_event_time)]
    return {
        "fixture_id": fixture_id,
        "old_event_time": ensure_utc(old_event_time).isoformat(),
        "new_event_time": ensure_utc(new_event_time).isoformat(),
        "cancel_old_jobs": [job["idempotency_key"] for job in old],
        "create_new_jobs": new,
        "invalidate_candidates": True,
        "invalidate_llm_reviews": True,
        "paper_only": True,
    }

