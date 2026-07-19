from __future__ import annotations

from datetime import timedelta
from time import perf_counter
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from v10.db.models import JobAttempt, ScheduledJob
from v10.time import ensure_utc, utc_now

from .contracts import JobExecutionResult, JobStatus, ScheduledJobSpec


class ScheduledJobRepository:
    def __init__(self, session: Session):
        self.session = session

    def enqueue(self, spec: ScheduledJobSpec) -> tuple[ScheduledJob, bool]:
        existing = self.session.scalar(select(ScheduledJob).where(ScheduledJob.idempotency_key == spec.idempotency_key))
        if existing:
            return existing, False
        row = ScheduledJob(
            job_type=spec.job_type.value,
            fixture_id=spec.fixture_id,
            candidate_id=spec.candidate_id,
            provider_key=spec.provider_key,
            priority=spec.priority,
            due_at=spec.due_at,
            not_before=spec.due_at,
            expires_at=None,
            status=JobStatus.PENDING.value,
            idempotency_key=spec.idempotency_key,
            payload_json=spec.payload,
            max_attempts=spec.max_attempts,
        )
        self.session.add(row)
        try:
            self.session.flush()
            return row, True
        except IntegrityError:
            self.session.rollback()
            existing = self.session.scalar(select(ScheduledJob).where(ScheduledJob.idempotency_key == spec.idempotency_key))
            if existing:
                return existing, False
            raise

    def enqueue_many(self, specs: list[ScheduledJobSpec]) -> dict[str, Any]:
        inserted = 0
        ignored = 0
        ids = []
        for spec in specs:
            row, created = self.enqueue(spec)
            ids.append(row.id)
            inserted += int(created)
            ignored += int(not created)
        return {"inserted": inserted, "ignored": ignored, "job_ids": ids}

    def list_due(self, now=None, limit: int = 50) -> list[ScheduledJob]:
        now = ensure_utc(now or utc_now(), "now")
        stmt = (
            select(ScheduledJob)
            .where(
                ScheduledJob.status.in_([JobStatus.PENDING.value, JobStatus.RETRY.value]),
                ScheduledJob.due_at <= now,
                or_(ScheduledJob.not_before.is_(None), ScheduledJob.not_before <= now),
                or_(ScheduledJob.expires_at.is_(None), ScheduledJob.expires_at > now),
            )
            .order_by(ScheduledJob.priority, ScheduledJob.due_at, ScheduledJob.created_at)
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def claim_due(self, owner: str, now=None, limit: int = 50, lease_seconds: int = 300) -> list[ScheduledJob]:
        now = ensure_utc(now or utc_now(), "now")
        stmt = (
            select(ScheduledJob)
            .where(
                ScheduledJob.status.in_([JobStatus.PENDING.value, JobStatus.RETRY.value]),
                ScheduledJob.due_at <= now,
                or_(ScheduledJob.not_before.is_(None), ScheduledJob.not_before <= now),
                or_(ScheduledJob.expires_at.is_(None), ScheduledJob.expires_at > now),
            )
            .order_by(ScheduledJob.priority, ScheduledJob.due_at, ScheduledJob.created_at)
            .limit(limit)
        )
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)
        jobs = list(self.session.scalars(stmt))
        lease_expires_at = now + timedelta(seconds=lease_seconds)
        for job in jobs:
            job.status = JobStatus.CLAIMED.value
            job.lease_owner = owner
            job.lease_acquired_at = now
            job.lease_expires_at = lease_expires_at
        self.session.flush()
        return jobs

    def start_attempt(self, job: ScheduledJob, worker_id: str, now=None) -> JobAttempt:
        now = ensure_utc(now or utc_now(), "now")
        job.status = JobStatus.RUNNING.value
        job.attempt_count += 1
        attempt = JobAttempt(
            job_id=job.id,
            attempt_number=job.attempt_count,
            worker_id=worker_id,
            started_at=now,
            status=JobStatus.RUNNING.value,
        )
        self.session.add(attempt)
        self.session.flush()
        return attempt

    def finish_attempt(self, job: ScheduledJob, attempt: JobAttempt, result: JobExecutionResult, started_perf: float) -> None:
        now = utc_now()
        attempt.finished_at = now
        attempt.status = result.status.value
        attempt.duration_ms = int((perf_counter() - started_perf) * 1000)
        attempt.result_summary_json = result.summary
        attempt.retry_reason = result.retry_reason
        job.last_error_code = result.error_code
        job.last_error_summary = result.error_summary[:500]
        if result.status == JobStatus.SUCCEEDED:
            job.status = JobStatus.SUCCEEDED.value
            job.lease_owner = None
            job.lease_acquired_at = None
            job.lease_expires_at = None
        elif result.status == JobStatus.RETRY and job.attempt_count < job.max_attempts:
            job.status = JobStatus.RETRY.value
            job.not_before = now + timedelta(minutes=min(60, 2**max(job.attempt_count - 1, 0)))
            job.lease_owner = None
            job.lease_expires_at = None
        elif result.status == JobStatus.SKIPPED:
            job.status = JobStatus.SKIPPED.value
            job.lease_owner = None
            job.lease_expires_at = None
        else:
            job.status = JobStatus.FAILED.value
            job.lease_owner = None
            job.lease_expires_at = None
        self.session.flush()

    def recover_expired_leases(self, now=None, dry_run: bool = True) -> dict[str, Any]:
        now = ensure_utc(now or utc_now(), "now")
        rows = list(
            self.session.scalars(
                select(ScheduledJob).where(
                    ScheduledJob.status.in_([JobStatus.CLAIMED.value, JobStatus.RUNNING.value]),
                    ScheduledJob.lease_expires_at.is_not(None),
                    ScheduledJob.lease_expires_at < now,
                )
            )
        )
        recovered = []
        if not dry_run:
            for row in rows:
                row.status = JobStatus.RETRY.value if row.attempt_count < row.max_attempts else JobStatus.FAILED.value
                row.lease_owner = None
                row.lease_acquired_at = None
                row.lease_expires_at = None
                row.last_error_code = "lease_expired"
                row.last_error_summary = "Lease expire: job repris par le prochain tick."
                recovered.append(row.id)
            self.session.flush()
        return {"expired": len(rows), "recovered": len(recovered), "dry_run": dry_run, "job_ids": [row.id for row in rows]}

    def list_jobs(self, status: str | None = None, limit: int = 100) -> list[ScheduledJob]:
        stmt = select(ScheduledJob).order_by(ScheduledJob.due_at.desc()).limit(limit)
        if status:
            stmt = select(ScheduledJob).where(ScheduledJob.status == status).order_by(ScheduledJob.due_at.desc()).limit(limit)
        return list(self.session.scalars(stmt))

    def get(self, job_id: str) -> ScheduledJob | None:
        return self.session.get(ScheduledJob, job_id)

    def retry(self, job_id: str, dry_run: bool = True) -> dict[str, Any]:
        row = self.get(job_id)
        if row is None:
            return {"found": False, "dry_run": dry_run}
        if not dry_run:
            row.status = JobStatus.RETRY.value
            row.not_before = utc_now()
            row.lease_owner = None
            row.lease_expires_at = None
            self.session.flush()
        return {"found": True, "job_id": job_id, "status": row.status, "dry_run": dry_run}

    def cancel(self, job_id: str, dry_run: bool = True) -> dict[str, Any]:
        row = self.get(job_id)
        if row is None:
            return {"found": False, "dry_run": dry_run}
        if not dry_run:
            row.status = JobStatus.CANCELLED.value
            row.lease_owner = None
            row.lease_expires_at = None
            self.session.flush()
        return {"found": True, "job_id": job_id, "status": row.status, "dry_run": dry_run}


def job_to_dict(job: ScheduledJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "job_type": job.job_type,
        "fixture_id": job.fixture_id,
        "candidate_id": job.candidate_id,
        "provider": job.provider_key,
        "priority": job.priority,
        "due_at": job.due_at.isoformat(),
        "status": job.status,
        "attempt_count": job.attempt_count,
        "lease_owner": job.lease_owner,
        "lease_expires_at": job.lease_expires_at.isoformat() if job.lease_expires_at else None,
        "idempotency_key": job.idempotency_key,
        "payload": job.payload_json,
    }

