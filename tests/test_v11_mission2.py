from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from tests.test_v11 import NOW, snapshot
from v11.api import create_app, get_ledger
from v11.ledger import Ledger
from scripts.v11_publication_audit import findings_for


def test_private_app_security_and_web_models(tmp_path, monkeypatch):
    app = create_app()
    ledger = Ledger(tmp_path / "private.sqlite3")
    ledger.add_snapshot(snapshot().model_dump(mode="json"))
    app.dependency_overrides[get_ledger] = lambda: ledger
    monkeypatch.setenv("INTERNAL_API_TOKEN", "ci-test-only")
    monkeypatch.setattr("v11.api.utc_now", lambda: NOW)
    auth = {"Authorization": "Bearer ci-test-only"}
    with TestClient(app) as client:
        for path in ("/metrics", "/api/v10/jobs", "/docs", "/openapi.json"):
            assert client.get(path).status_code == 404
        for headers in ({}, {"Authorization": "ci-test-only"}, {"Authorization": "Bearer wrong"}):
            response = client.get("/api/v11/history", headers=headers)
            assert response.status_code == 401
            assert response.headers["cache-control"] == "no-store"
        shell = client.get("/v11")
        assert "unsafe-inline" not in shell.headers["content-security-policy"]
        assert "<script src=" in shell.text
        assert client.get("/v11-assets/mobile.js").status_code == 200
        assert client.get("/v11-assets/not-allowed").status_code == 404
        report = client.post("/api/v11/analyze", params={"day": str(NOW.date())}, headers=auth).json()
        fixture = report["fixtures"][0]
        attempted = {m["model_key"] for m in fixture["models"]} | {m["model"] for m in fixture["model_errors"]}
        assert {"penaltyblog_poisson_v1", "penaltyblog_dixon_coles_v1", "penaltyblog_bivariate_poisson_v1"} <= attempted
        assert len([m for m in attempted if not m.startswith("penaltyblog")]) == 3
        assert len(fixture["missing_bookmakers"]) == 5
        assert fixture["decision"] == "ABSTAIN"
        elo = next(m for m in fixture["models"] if m["model_key"] == "elo_multiclass_v1")
        elo_quote = next(q for q in fixture["comparisons"] if q["model"] == "elo_multiclass_v1")
        assert elo_quote["expected_value"] == pytest.approx(elo["probabilities_1x2"][elo_quote["selection"]]*elo_quote["odds"]-1)
        performance = client.get("/api/v11/performance", params={"model": "poisson_independent_v1"}, headers=auth)
        assert performance.status_code == 200 and performance.json()["roi_simulated"] is None
        baseline = client.post("/api/v11/analyze", params={"day": str(NOW.date()), "include_penaltyblog": False}, headers=auth).json()
        assert len(baseline["fixtures"][0]["models"]) == 3
        monkeypatch.delenv("INTERNAL_API_TOKEN")
        assert client.get("/api/v11/history", headers=auth).status_code == 503


def test_publication_guard_catches_prior_blob_privacy_without_echoing_values():
    profile_path = "/".join(["C:", "Users", "private-person", "project"])
    hits = findings_for("docs/example.md", profile_path.encode())
    assert hits[0]["kind"] == "user_profile_path"
    assert "private-person" not in str(hits)
    assert findings_for("variable/store.sqlite3", b"database")[0]["kind"] == "private_local_file"
    assert not findings_for("v11/example.py", b"print('safe')")


def test_apply_provider_results_explicit_identity_and_idempotence(tmp_path, monkeypatch):
    from v11.results import apply_results
    from v11.service import analyze
    ledger = Ledger(tmp_path / "results.sqlite3")
    ledger.add_snapshot(snapshot().model_dump(mode="json"))
    prediction = analyze(ledger, NOW.date(), NOW)["fixtures"][0]
    kickoff = prediction["kickoff"]
    observed = NOW + timedelta(hours=8)
    envelope = {"provider": "api_football", "fetched_at": observed.isoformat(), "payload": {"errors": [], "response": [{
        "fixture": {"id": 7, "date": kickoff, "status": {"short": "FT"}},
        "league": {"id": 61}, "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
        "goals": {"home": 2, "away": 1}}]}}
    mapping = {"test:1": "api_football:7"}
    first = apply_results(ledger, envelope, mapping, observed)
    assert first["status"] == "PASS" and len(first["outcome_ids"]) == 1
    assert apply_results(ledger, envelope, mapping, observed) == first
    assert len(ledger.history()[0]["outcomes"]) == 1
    envelope["payload"]["response"][0]["teams"]["home"]["name"] = "Wrong team"
    with pytest.raises(ValueError, match="identity"):
        apply_results(ledger, envelope, mapping, observed)
    assert len(ledger.history()[0]["outcomes"]) == 1
    envelope["payload"]["response"][0]["fixture"]["status"]["short"] = "AET"
    assert apply_results(ledger, envelope, mapping, observed)["status"] == "PARTIAL"
    envelope["payload"]["response"][0]["fixture"]["status"]["short"] = "FT"
    envelope["payload"]["response"][0]["teams"]["home"]["name"] = "A"
    import json
    from v11.__main__ import main
    monkeypatch.setattr("v11.__main__.utc_now", lambda: observed)
    raw = tmp_path / "result.json"
    config = tmp_path / "mapping.json"
    raw.write_text(json.dumps(envelope), encoding="utf-8")
    config.write_text(json.dumps({"fixtures": mapping}), encoding="utf-8")
    assert main(["--ledger", str(ledger.path), "apply-results", "--file", str(raw), "--mapping", str(config)]) == 0
    assert len(ledger.history()[0]["outcomes"]) == 1
