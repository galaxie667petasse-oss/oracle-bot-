from __future__ import annotations

import os
from datetime import timedelta
from time import perf_counter
from typing import Callable

from sqlalchemy.orm import Session, sessionmaker

from v10.db.locks import AdvisoryLockManager
from v10.db.models import SchedulerRun
from v10.time import utc_now

from .contracts import JobExecutionResult, JobStatus
from .jobs import ScheduledJobRepository

JobHandler = Callable[[Session, object], JobExecutionResult]


def default_job_handler(session: Session, job: object) -> JobExecutionResult:
    return JobExecutionResult(
        status=JobStatus.SUCCEEDED,
        summary={"handled_by": "default_noop_handler", "paper_only": True, "llm_calls": 0, "telegram_sent": False},
    )


class SchedulerDispatcher:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        worker_id: str | None = None,
        handlers: dict[str, JobHandler] | None = None,
    ):
        self.session_factory = session_factory
        self.worker_id = worker_id or f"scheduler-{os.getpid()}"
        self.handlers = handlers or {}

    def tick(self, max_runtime_seconds: int = 240, max_jobs: int = 50, shutdown_margin_seconds: int = 20, dry_run: bool = False) -> dict:
        start = perf_counter()
        now = utc_now()
        deadline = now + timedelta(seconds=max_runtime_seconds)
        with self.session_factory() as session:
            lock = AdvisoryLockManager(session, "v10_scheduler_dispatcher", owner=self.worker_id)
            acquired = lock.acquire()
            if not acquired:
                session.rollback()
                return {"status": "SKIPPED", "reason": "global_lock_already_held", "jobs_claimed": 0, "dry_run": dry_run}
            try:
                run = SchedulerRun(started_at=now, deadline_at=deadline, status="DRY_RUN" if dry_run else "RUNNING", heartbeat_at=now)
                if not dry_run:
                    session.add(run)
                    session.flush()
                repo = ScheduledJobRepository(session)
                due = repo.list_due(now, max_jobs) if dry_run else repo.claim_due(self.worker_id, now, max_jobs, lease_seconds=max_runtime_seconds)
                report = {
                    "scheduler_run_id": run.id,
                    "status": "DRY_RUN" if dry_run else "RUNNING",
                    "jobs_due": len(due),
                    "jobs_claimed": 0 if dry_run else len(due),
                    "jobs_completed": 0,
                    "jobs_retried": 0,
                    "jobs_failed": 0,
                    "jobs_skipped": 0,
                    "exit_reason": "completed",
                    "dry_run": dry_run,
                    "paper_only": True,
                }
                if dry_run:
                    report["jobs"] = [{"id": job.id, "job_type": job.job_type, "due_at": job.due_at.isoformat(), "status": job.status} for job in due]
                    lock.release()
                    session.rollback()
                    return report
                for job in due:
                    remaining = max_runtime_seconds - (perf_counter() - start)
                    if remaining <= shutdown_margin_seconds:
                        job.status = JobStatus.RETRY.value
                        job.lease_owner = None
                        job.lease_expires_at = None
                        report["exit_reason"] = "shutdown_margin_reached"
                        break
                    attempt = repo.start_attempt(job, self.worker_id)
                    attempt_start = perf_counter()
                    handler = self.handlers.get(job.job_type, default_job_handler)
                    try:
                        result = handler(session, job)
                    except Exception as exc:
                        result = JobExecutionResult(
                            status=JobStatus.RETRY,
                            summary={"error": str(exc), "job_type": job.job_type},
                            retry_reason="handler_exception",
                            error_code=exc.__class__.__name__,
                            error_summary=str(exc),
                        )
                    repo.finish_attempt(job, attempt, result, attempt_start)
                    if result.status == JobStatus.SUCCEEDED:
                        report["jobs_completed"] += 1
                    elif result.status == JobStatus.RETRY:
                        report["jobs_retried"] += 1
                    elif result.status == JobStatus.SKIPPED:
                        report["jobs_skipped"] += 1
                    else:
                        report["jobs_failed"] += 1
                run.jobs_claimed = report["jobs_claimed"]
                run.jobs_completed = report["jobs_completed"]
                run.jobs_retried = report["jobs_retried"]
                run.jobs_failed = report["jobs_failed"]
                run.exit_reason = report["exit_reason"]
                run.status = "SUCCEEDED" if report["jobs_failed"] == 0 else "PARTIAL"
                run.heartbeat_at = utc_now()
                run.finished_at = utc_now()
                report["status"] = run.status
                lock.release()
                session.commit()
                return report
            except Exception:
                lock.release()
                session.rollback()
                raise
