"""V11 router mounted on the existing FastAPI application, private by default."""
from __future__ import annotations

import hmac
import os
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from v10.time import utc_now
from v11.contracts import Snapshot
from v11.ledger import Ledger
from v11.service import analyze


def require_token(authorization: str | None = Header(default=None)):
    token = os.getenv("INTERNAL_API_TOKEN", "")
    if not token:
        raise HTTPException(503, "INTERNAL_API_TOKEN required for V11")
    if not (authorization or "").startswith("Bearer "):
        raise HTTPException(401, "Bearer authentication required")
    supplied = authorization[len("Bearer "):]
    if not hmac.compare_digest(token.encode(), supplied.encode()):
        raise HTTPException(401, "authentication required")


def get_ledger() -> Ledger:
    return Ledger(os.getenv("ORACLE_V11_LEDGER", "variable/oracle-v11.sqlite3"))


router = APIRouter(prefix="/api/v11", dependencies=[Depends(require_token)])


@router.get("/status")
def status(ledger: Ledger = Depends(get_ledger)):
    return {"version": "11.0.0-research", "mode": "research_only", "network_from_web": False,
            "can_influence_picks": False, "ledger": ledger.verify(),
            "sources": {name: {"key_present": bool(os.getenv(env)), "live_verified": False}
                        for name, env in (("api_football", "API_FOOTBALL_KEY"), ("the_odds_api", "THE_ODDS_API_KEY"))}}


@router.post("/snapshots")
def ingest(snapshot: Snapshot, ledger: Ledger = Depends(get_ledger)):
    if snapshot.captured_at > utc_now():
        raise HTTPException(422, "future snapshot")
    return {"snapshot_id": ledger.add_snapshot(snapshot.model_dump(mode="json"))}


@router.post("/analyze")
def analyze_date(day: date, include_penaltyblog: bool = True, ledger: Ledger = Depends(get_ledger)):
    try:
        return analyze(ledger, day, utc_now(), include_penaltyblog)
    except ValueError:
        raise HTTPException(422, "invalid or future source snapshot") from None


@router.get("/history")
def history(ledger: Ledger = Depends(get_ledger)):
    return ledger.history()


@router.get("/performance")
def performance(model: str, ledger: Ledger = Depends(get_ledger)):
    from v11.paper import paper_report
    try:
        return {**paper_report(ledger.history(500), model), "history_window_limit": 500}
    except ValueError:
        raise HTTPException(422, "evaluate evidence provenances separately") from None


def install(app):
    app.include_router(router)

    @app.middleware("http")
    async def private_response_headers(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(("/api/v11", "/v11")):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/v11-assets/{name}", include_in_schema=False)
    def assets(name: str):
        if name not in {"mobile.js", "mobile.css"}:
            raise HTTPException(404, "asset not found")
        return FileResponse(Path(__file__).with_name(name))

    @app.get("/v11", response_class=HTMLResponse)
    def mobile():
        # Public shell only; every data route requires a token. Never persist it.
        return HTMLResponse(Path(__file__).with_name("mobile.html").read_text(encoding="utf-8"), headers={
            "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


def create_app() -> FastAPI:
    """Private V11 serving entrypoint; keeps legacy V10 routes in their own app."""
    app = FastAPI(title="Oracle V11 private research", docs_url=None, redoc_url=None, openapi_url=None)
    install(app)

    @app.get("/health/live")
    def live():
        return {"status": "ok", "service": "oracle-v11", "can_influence_picks": False}

    return app


app = create_app()
