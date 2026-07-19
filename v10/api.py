from __future__ import annotations

import hmac
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from v10.config import load_settings
from v10.db.migrations import migration_status
from v10.db.models import (
    OperationalAlert,
    ProviderHealth,
    ProviderQuotaUsage,
    ScheduledJob,
    SchedulerRun,
    ScanRun,
    ShadowDecisionRecord,
    ShadowExperiment,
    ShadowExperimentDecision,
)
from v10.db.session import create_engine_from_settings, create_session_factory, database_health, session_scope


app = FastAPI(title="Oracle Football Bot V10", version="10.5-shadow")


def _settings():
    return load_settings()


def _require_internal_token(authorization: str | None = Header(default=None)) -> bool:
    settings = _settings()
    if not settings.dashboard_require_auth:
        return True
    if settings.internal_api_token:
        token = (authorization or "").removeprefix("Bearer ").strip()
        if hmac.compare_digest(token, settings.internal_api_token):
            return True
        raise HTTPException(status_code=401, detail="internal token required")
    if settings.app_env.lower() in {"prod", "production", "staging"}:
        raise HTTPException(status_code=403, detail="INTERNAL_API_TOKEN required in non-local env")
    return True


def _db_counts() -> dict[str, Any]:
    settings = _settings()
    if not settings.database_url:
        return {"database_configured": False, "counts": {}}
    engine = create_engine_from_settings(settings)
    session_factory = create_session_factory(engine)
    try:
        with session_scope(session_factory) as session:
            counts = {
                "jobs": session.scalar(select(func.count()).select_from(ScheduledJob)) or 0,
                "scheduler_runs": session.scalar(select(func.count()).select_from(SchedulerRun)) or 0,
                "scan_runs": session.scalar(select(func.count()).select_from(ScanRun)) or 0,
                "experiments": session.scalar(select(func.count()).select_from(ShadowExperiment)) or 0,
                "experiment_decisions": session.scalar(select(func.count()).select_from(ShadowExperimentDecision)) or 0,
                "alerts": session.scalar(select(func.count()).select_from(OperationalAlert)) or 0,
            }
        return {"database_configured": True, "counts": counts}
    finally:
        engine.dispose()


@app.get("/health/live")
def live() -> dict[str, Any]:
    return {"status": "ok", "service": "oracle-v10", "lab_only": True}


@app.get("/health/ready")
def ready() -> dict[str, Any]:
    settings = _settings()
    if not settings.database_url:
        return {"status": "degraded", "database": "not_configured", "providers_do_not_affect_readiness": True}
    engine = create_engine_from_settings(settings)
    try:
        health = database_health(engine)
    finally:
        engine.dispose()
    try:
        migrations = migration_status(settings)
    except Exception as exc:
        migrations = {"status": "error", "error": str(exc)}
    status = "ok" if health.get("status") == "ok" and migrations.get("up_to_date") else "degraded"
    return {"status": status, "database_health": health, "migration_status": migrations, "providers_do_not_affect_readiness": True}


@app.get("/health/deep")
def deep(_: bool = Depends(_require_internal_token)) -> dict[str, Any]:
    report = _db_counts()
    report.update({"status": "ok" if report["database_configured"] else "degraded", "llm_paid_calls": False, "telegram_sent": False})
    return report


@app.get("/metrics")
def metrics() -> dict[str, Any]:
    report = _db_counts()
    counts = report.get("counts", {})
    return {
        "jobs_total": counts.get("jobs", 0),
        "scheduler_runs_total": counts.get("scheduler_runs", 0),
        "shadow_experiment_decisions_total": counts.get("experiment_decisions", 0),
        "alerts_total": counts.get("alerts", 0),
        "paid_openai_calls_total": 0,
        "telegram_sends_total": 0,
    }


def _list_table(model, limit: int = 50) -> list[dict[str, Any]]:
    settings = _settings()
    if not settings.database_url:
        return []
    engine = create_engine_from_settings(settings)
    session_factory = create_session_factory(engine)
    try:
        with session_scope(session_factory) as session:
            rows = list(session.scalars(select(model).limit(limit)))
            return [{key: str(value) if not isinstance(value, (str, int, float, bool, type(None), dict, list)) else value for key, value in row.__dict__.items() if not key.startswith("_")} for row in rows]
    finally:
        engine.dispose()


@app.get("/api/v10/jobs")
def jobs(_: bool = Depends(_require_internal_token)) -> list[dict[str, Any]]:
    return _list_table(ScheduledJob)


@app.get("/api/v10/scheduler/runs")
def scheduler_runs(_: bool = Depends(_require_internal_token)) -> list[dict[str, Any]]:
    return _list_table(SchedulerRun)


@app.get("/api/v10/scans")
def scans(_: bool = Depends(_require_internal_token)) -> list[dict[str, Any]]:
    return _list_table(ScanRun)


@app.get("/api/v10/providers/health")
def providers_health(_: bool = Depends(_require_internal_token)) -> list[dict[str, Any]]:
    return _list_table(ProviderHealth)


@app.get("/api/v10/providers/quotas")
def providers_quotas(_: bool = Depends(_require_internal_token)) -> list[dict[str, Any]]:
    return _list_table(ProviderQuotaUsage)


@app.get("/api/v10/fixtures/upcoming")
def upcoming(_: bool = Depends(_require_internal_token)) -> dict[str, Any]:
    return {"fixtures": [], "source": "database_query_pending_provider_ingestion", "read_only": True}


@app.get("/api/v10/candidates")
def candidates(_: bool = Depends(_require_internal_token)) -> dict[str, Any]:
    return {"candidates": [], "shadow_only": True, "statistical_model_validated_for_signals": False}


@app.get("/api/v10/shadow-decisions")
def shadow_decisions(_: bool = Depends(_require_internal_token)) -> list[dict[str, Any]]:
    return _list_table(ShadowDecisionRecord)


@app.get("/api/v10/experiments")
def experiments(_: bool = Depends(_require_internal_token)) -> list[dict[str, Any]]:
    return _list_table(ShadowExperiment)


@app.get("/api/v10/performance")
def performance(_: bool = Depends(_require_internal_token)) -> dict[str, Any]:
    return {"status": "insufficient_evidence", "statistical_model_validated_for_signals": False, "no_profit_claim": True}


@app.get("/api/v10/llm/costs")
def llm_costs(_: bool = Depends(_require_internal_token)) -> dict[str, Any]:
    return {"real_cost_usd": "0.00000000", "paid_calls": 0, "shadow_only": True}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(_: bool = Depends(_require_internal_token)) -> str:
    counts = _db_counts().get("counts", {})
    rows = "".join(f"<tr><th>{key}</th><td>{value}</td></tr>" for key, value in counts.items())
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Oracle V10 Shadow Ops</title>
<style>body{{font-family:system-ui;margin:24px;max-width:920px}}table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #ddd;padding:8px;text-align:left}}.banner{{padding:12px;background:#eef6f8;border-left:4px solid #227c89}}</style></head>
<body><h1>Oracle V10 Shadow Ops</h1><div class="banner">Read-only. Paper-only. Aucun Telegram, aucune mise, aucun appel OpenAI payant par defaut.</div>
<h2>Compteurs</h2><table>{rows}</table></body></html>"""
