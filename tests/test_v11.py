from datetime import UTC, datetime, timedelta
import sqlite3
import json

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from v10.db.base import Base
from v10.statistics.demo import synthetic_matches
from v10.statistics.poisson import independent_poisson_distribution
from v11.contracts import Fixture, HistoryMatch, Quote, Snapshot
from v11.evaluation import chronological_evaluation, temperature
from v11.ledger import Ledger
from v11.markets import price, settle
from v11.models import PenaltyblogAdapter
from v11.service import analyze
from v11.sources import Collector, SourceError, odds_snapshot


NOW = datetime(2026, 10, 15, 12, tzinfo=UTC)


def snapshot(history=True):
    matches = [HistoryMatch(match_id=str(i), competition="test", home="A" if i%2 else "B",
                           away="B" if i%2 else "A", kickoff=NOW-timedelta(days=100-i),
                           result_observed_at=NOW-timedelta(days=100-i)+timedelta(hours=2),
                           home_goals=i%4, away_goals=i%3) for i in range(80)] if history else []
    return Snapshot(captured_at=NOW, provenance="synthetic", history=matches,
                    fixtures=[Fixture(fixture_id="test:1", source="synthetic", competition="test", home="A", away="B",
                                      kickoff=NOW+timedelta(hours=6), observed_at=NOW,
                                      quotes=[Quote(source="synthetic", bookmaker="Test book", market="match_winner",
                                                    selection=s, odds=o, observed_at=NOW, provider_updated_at=NOW)
                                              for s,o in (("home",2.2),("draw",3.4),("away",3.5))])])


@pytest.mark.parametrize("market,selection,line,h,a,kind,profit", [
    ("asian_handicap","home",-.25,1,1,"half_loss",-.5),
    ("asian_handicap","home",.25,1,1,"half_win",.5),
    ("asian_handicap","home",-1,2,1,"push",0),
    ("asian_handicap","home",-1.25,2,1,"half_loss",-.5),
    ("asian_handicap","away",.75,1,0,"half_loss",-.5),
    ("asian_handicap","away",1.25,1,0,"half_win",.5),
    ("total_goals","over",2.25,1,1,"half_loss",-.5),
    ("total_goals","under",2.25,1,1,"half_win",.5),
    ("total_goals","over",2.75,2,1,"half_win",.5),
    ("total_goals","under",2.75,2,1,"half_loss",-.5),
    ("match_winner","home",None,2,1,"win",1),
    ("match_winner","draw",None,2,1,"loss",-1),
    ("double_chance","1x",None,0,0,"win",1),
    ("both_teams_to_score","no",None,0,1,"win",1),
    ("correct_score","2:1",None,2,1,"win",1),
    ("draw_no_bet","home",None,0,0,"push",0),
])
def test_regulation_settlement(market, selection, line, h, a, kind, profit):
    result = settle(market, selection, 2, h, a, line)
    assert (result.status, result.profit_units) == (kind, profit)


@pytest.mark.parametrize("status", ["AET", "PEN", "PST", "SUSP", "ABD", "", "LIVE"])
def test_no_regulation_inference(status):
    assert settle("match_winner", "home", 2, 1, 0, status=status).profit_units is None


@pytest.mark.parametrize("line", [.1, float("nan"), float("inf")])
def test_bad_lines(line):
    with pytest.raises(ValueError): settle("asian_handicap", "home", 2, 1, 0, line)


def test_probability_and_ev_coherence():
    dist = independent_poisson_distribution(1.5, 1.1, 12, "test")
    home = price(dist, "match_winner", "home", 2.2)
    assert home["expected_value"] == pytest.approx(home["settlement_probabilities"]["win"]*2.2-1)
    for line in [-2.25,-1,-.75,-.25,0,.25,.75,1,2.25]:
        h = price(dist,"asian_handicap","home",2,line)
        a = price(dist,"asian_handicap","away",2,-line)
        assert sum(h["settlement_probabilities"].values()) == pytest.approx(1)
        assert h["expected_value"]+a["expected_value"] == pytest.approx(0)


def test_prediction_outcome_backup_restore(tmp_path):
    ledger=Ledger(tmp_path/"ledger.sqlite3")
    key=ledger.add_snapshot(snapshot().model_dump(mode="json"))
    assert key == ledger.add_snapshot(snapshot().model_dump(mode="json"))
    report=analyze(ledger,NOW.date(),NOW)
    pred=report["fixtures"][0]
    assert pred["decision"] == "ABSTAIN" and len(pred["models"]) == 3
    assert pred["comparisons"] and pred["market_baselines"]
    assert all(c["uncertainty"] is None for c in pred["comparisons"])
    before=ledger.history()[0]
    with ledger.connect() as db:
        for table in ("snapshots","predictions"):
            with pytest.raises(sqlite3.IntegrityError): db.execute(f"UPDATE {table} SET payload='{{}}'")
        with pytest.raises(sqlite3.IntegrityError): db.execute("DELETE FROM predictions")
    oid=ledger.add_outcome(pred["id"],2,1,NOW+timedelta(hours=9),"synthetic_test")
    assert oid == ledger.add_outcome(pred["id"],2,1,NOW+timedelta(hours=9),"synthetic_test")
    after=ledger.history()[0]
    assert {k:v for k,v in before.items() if k!="outcomes"} == {k:v for k,v in after.items() if k!="outcomes"}
    assert len(after["outcomes"])==1
    with ledger.connect() as db:
        with pytest.raises(sqlite3.IntegrityError): db.execute("UPDATE outcomes SET payload='{}'")
        with pytest.raises(sqlite3.IntegrityError): db.execute("DELETE FROM outcomes")
    ledger.backup(tmp_path/"restore.sqlite3")
    assert Ledger(tmp_path/"restore.sqlite3").history()==ledger.history()
    assert ledger.verify()["hashes_ok"]


def test_fail_closed_history_and_stale_quotes(tmp_path):
    raw=snapshot(False).model_dump(mode="json")
    raw["fixtures"][0]["quotes"][0]["provider_updated_at"]=(NOW-timedelta(days=1)).isoformat()
    ledger=Ledger(tmp_path/"l.sqlite3");ledger.add_snapshot(raw)
    f=analyze(ledger,NOW.date(),NOW)["fixtures"][0]
    assert not f["models"] and not f["comparisons"] and f["rejected_quotes"]
    assert "insufficient_team_history" in f["reasons"]
    assert analyze(ledger,NOW.date(),NOW+timedelta(days=1))["fixtures"][0]["reasons"]==["not_prematch"]


def test_future_results_excluded(tmp_path):
    raw=snapshot().model_dump(mode="json")
    raw["history"][0]["result_observed_at"]=(NOW+timedelta(days=1)).isoformat()
    with pytest.raises(ValueError): Snapshot.model_validate(raw)
    raw=snapshot().model_dump(mode="json")
    raw["fixtures"][0]["observed_at"]="2026-10-15T12:00:00"
    with pytest.raises(ValueError): Snapshot.model_validate(raw)


@pytest.mark.parametrize("kind", list(PenaltyblogAdapter.classes))
def test_real_penaltyblog_library(kind):
    pytest.importorskip("penaltyblog")
    from v10.statistics.types import HistoricalMatch
    rng=np.random.default_rng(11)
    teams=["A","B","C","D","E","F"]
    matches=[]
    for i in range(360):
        h,a=rng.choice(teams,2,replace=False)
        matches.append(HistoricalMatch(str(i),NOW-timedelta(days=400-i),"synthetic","2026",str(h),str(a),
                                       int(rng.poisson(1.6)),int(rng.poisson(1.2))))
    model=PenaltyblogAdapter(kind).fit(matches)
    p=model.predict(matches[0].home_team,matches[0].away_team)
    assert sum(p.probabilities_1x2.values()) == pytest.approx(1)
    assert p.score_distribution.total_mass()==pytest.approx(1)
    assert p.diagnostics["library_version"]=="1.6.2"


def test_degenerate_dixon_coles_grid_is_rejected():
    pytest.importorskip("penaltyblog")
    matches=synthetic_matches()
    model=PenaltyblogAdapter("dixon_coles").fit(matches)
    with pytest.raises(ValueError,match="negative probabilities"):
        model.predict(matches[0].home_team,matches[0].away_team)


def test_chronological_calibration_and_same_time_grouping():
    matches=[]
    for i in range(180):
        kickoff=NOW+timedelta(days=i//2)
        matches.append(HistoryMatch(match_id=str(i),competition="test",home="A" if i%2 else "B",away="B" if i%2 else "A",
                                    kickoff=kickoff,result_observed_at=kickoff+timedelta(hours=2),home_goals=i%4,away_goals=i%3))
    r=chronological_evaluation(matches,train_min=40,test_size=13,calibration_size=30)
    ids=[i for fold in r["folds"] for i in fold["test_ids"]]
    assert len(ids)==len(set(ids)) and r["prediction_count"]>0
    assert all(datetime.fromisoformat(f["training_result_cutoff"])<datetime.fromisoformat(f["decision_at"]) for f in r["folds"])
    assert r["roi"] is None and r["clv"] is None and not r["can_influence_picks"]
    assert temperature({"home":.5,"draw":.3,"away":.2},1)==pytest.approx({"home":.5,"draw":.3,"away":.2})
    quotes={row["match_id"]:[Quote(source="synthetic",bookmaker="test",market="match_winner",selection=s,odds=o,
                                  observed_at=datetime.fromisoformat(row["decision_at"]),
                                  provider_updated_at=datetime.fromisoformat(row["decision_at"]))
                             for s,o in (("home",2.1),("draw",3.3),("away",3.5))] for row in r["observations"]}
    market_report=chronological_evaluation(matches,train_min=40,test_size=13,calibration_size=30,archived_quotes=quotes)
    assert market_report["paired_market_comparisons"]
    assert all(p["count"]==market_report["prediction_count"] for p in market_report["paired_market_comparisons"])
    # Changing a first-fold test result cannot change that fold's forecasts.
    first_ids=set(r["folds"][0]["test_ids"])
    target=next(m for m in matches if m.match_id in first_ids)
    changed=[m.model_copy(update={"home_goals":8,"away_goals":0}) if m.match_id==target.match_id else m for m in matches]
    altered=chronological_evaluation(changed,train_min=40,test_size=13,calibration_size=30)
    before={row["match_id"]:row["predictions"] for row in r["observations"] if row["match_id"] in first_ids}
    after={row["match_id"]:row["predictions"] for row in altered["observations"] if row["match_id"] in first_ids}
    assert before==after


def test_cache_quota_no_network_and_secret_redaction(tmp_path):
    engine=create_engine("sqlite:///"+str(tmp_path/"cache.sqlite3"))
    Base.metadata.create_all(engine)
    calls=[]
    def reply(request):
        calls.append(request)
        return httpx.Response(200,json=[],headers={"x-requests-remaining":"1"})
    with Session(engine) as session:
        c=Collector(session,{"the_odds_api":"unit-test-key"},True,1,httpx.MockTransport(reply))
        first=c.fetch("the_odds_api",{"sport":"soccer_france_ligue_one"},NOW)
        second=c.fetch("the_odds_api",{"sport":"soccer_france_ligue_one"},NOW)
        assert not first["cache_hit"] and second["cache_hit"] and len(calls)==1
        assert calls[0].url.params["bookmakers"]=="betclic_fr,winamax_fr,unibet_fr,pmu_fr,netbet_fr"
        assert "regions" not in calls[0].url.params
        session.commit()
        with pytest.raises(SourceError): c.fetch("the_odds_api",{"sport":"soccer_epl"},NOW)
        offline=Collector(session,{},False,1,httpx.MockTransport(reply))
        with pytest.raises(SourceError): offline.fetch("the_odds_api",{"sport":"soccer_epl"},NOW)
    assert len(calls)==1
    engine.dispose()


def test_api_authenticated_import_analyze_history(tmp_path,monkeypatch):
    from v10.api import app
    from v11.api import get_ledger
    ledger=Ledger(tmp_path/"api.sqlite3")
    app.dependency_overrides[get_ledger]=lambda:ledger
    monkeypatch.setenv("INTERNAL_API_TOKEN","private-test-token")
    monkeypatch.setattr("v11.api.utc_now",lambda:NOW)
    try:
        with TestClient(app) as client:
            assert client.get("/v11").status_code==200
            assert client.get("/api/v11/history").status_code==401
            headers={"Authorization":"Bearer private-test-token"}
            assert client.post("/api/v11/snapshots",json=snapshot().model_dump(mode="json"),headers=headers).status_code==200
            report=client.post("/api/v11/analyze",params={"day":str(NOW.date())},headers=headers)
            assert report.status_code==200 and report.json()["fixtures"][0]["comparisons"]
            assert len(client.get("/api/v11/history",headers=headers).json())==1
            monkeypatch.delenv("INTERNAL_API_TOKEN")
            assert client.get("/api/v11/status").status_code==503
    finally:
        app.dependency_overrides.clear()


def test_paper_roi_clv_uses_sealed_prices_and_same_book(tmp_path):
    from v11.paper import paper_report
    ledger=Ledger(tmp_path/"paper.sqlite3")
    ledger.add_snapshot(snapshot().model_dump(mode="json"))
    pred=analyze(ledger,NOW.date(),NOW)["fixtures"][0]
    # Select a fixed model/threshold before attaching the synthetic outcome.
    model="poisson_independent_v1"
    ledger.add_outcome(pred["id"],2,1,NOW+timedelta(hours=8),"synthetic_test")
    initial=paper_report(ledger.history(),model,0)
    assert len(initial["rows"])==1 and initial["roi_simulated"] is not None
    chosen=initial["rows"][0]
    close=Quote(source="synthetic",bookmaker=chosen["bookmaker"],market="match_winner",
                selection=chosen["selection"],odds=chosen["odds"]-.1,
                observed_at=NOW+timedelta(hours=5,minutes=50),provider_updated_at=NOW+timedelta(hours=5,minutes=49))
    report=paper_report(ledger.history(),model,0,{pred["fixture_id"]:[close]})
    assert report["mean_clv_odds_ratio"]==pytest.approx(chosen["odds"]/close.odds-1)
    assert report["roi_day_bootstrap_95"] is None
    wrong=close.model_copy(update={"bookmaker":"other_book"})
    assert paper_report(ledger.history(),model,0,{pred["fixture_id"]:[wrong]})["mean_clv_odds_ratio"] is None
    assert paper_report([],model)["roi_simulated"] is None


def test_provider_http_failures_are_redacted_and_accounted(tmp_path):
    from v10.db.models import ProviderQuotaUsage
    from sqlalchemy import select
    engine=create_engine("sqlite:///"+str(tmp_path/"errors.sqlite3")); Base.metadata.create_all(engine)
    with Session(engine) as session:
        c=Collector(session,{"the_odds_api":"do-not-leak"},True,1,
                    httpx.MockTransport(lambda r:httpx.Response(429,json={"error":"do-not-leak"},headers={"x-requests-remaining":"0"})))
        with pytest.raises(SourceError,match="provider_http_429") as error:
            c.fetch("the_odds_api",{"sport":"soccer_epl"},NOW)
        assert "do-not-leak" not in str(error.value)
        assert session.scalar(select(ProviderQuotaUsage)).failures==1
    engine.dispose()


def test_timestamped_odds_normalization_preserves_lines():
    payload=[{"id":"event", "sport_key":"soccer_test", "commence_time":(NOW+timedelta(hours=3)).isoformat(),
              "home_team":"A","away_team":"B","bookmakers":[{"key":"test_book","title":"Test Book",
                "last_update":NOW.isoformat(),"markets":[{"key":"totals","outcomes":[
                    {"name":"Over","point":2.25,"price":2.0},{"name":"Under","point":2.25,"price":1.9}]}]}]}]
    s=odds_snapshot(payload,NOW,"synthetic")
    assert s.fixtures[0].fixture_id=="the_odds_api:event"
    assert all(q.line==2.25 and q.provider_updated_at==NOW for q in s.fixtures[0].quotes)
    old=NOW-timedelta(hours=2)
    payload[0]["bookmakers"][0]["markets"][0]["last_update"]=old.isoformat()
    assert all(q.provider_updated_at==old for q in odds_snapshot(payload,NOW,"synthetic").fixtures[0].quotes)


@pytest.mark.parametrize("market,selection,line", [("double_chance","oops",None),("correct_score","-1:2",None),
    ("total_goals","over",-1),("match_winner","home",1),("asian_handicap","away",None)])
def test_invalid_market_is_never_silently_a_loss(market,selection,line):
    with pytest.raises(ValueError): settle(market,selection,2,1,0,line)


def test_collection_cli_migrates_isolated_cache_and_blocks_offline(tmp_path,capsys):
    from v11.__main__ import main
    target=tmp_path/"raw.json"
    cache=tmp_path/"cache.sqlite3"
    code=main(["collect","--provider","api_football","--day","2026-10-15",
               "--output",str(target),"--cache-db",str(cache)])
    assert code==2 and not target.exists()
    assert '"error_type": "SourceError"' in capsys.readouterr().out
    with sqlite3.connect(cache) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0]=="20260719_0004"


def test_mixed_artificial_and_real_paper_evidence_refused():
    from v11.paper import paper_report
    with pytest.raises(ValueError,match="separately"):
        paper_report([{"provenance":"synthetic"},{"provenance":"real_provider"}],"poisson_independent_v1")


def test_duplicate_quote_and_malformed_provider_refused():
    raw=snapshot().model_dump(mode="json")
    raw["fixtures"][0]["quotes"].append(raw["fixtures"][0]["quotes"][0])
    with pytest.raises(ValueError,match="duplicate quote"): Snapshot.model_validate(raw)
    for payload in ({},["bad"],[{"bookmakers":["bad"]}]):
        with pytest.raises(ValueError): odds_snapshot(payload,NOW,"synthetic")


def test_consolidated_provider_payloads_to_models_without_backdated_results(tmp_path,monkeypatch):
    from v11.sources import build_snapshot
    sample=snapshot()
    odds={"provider":"the_odds_api","fetched_at":NOW.isoformat(),"payload":[{
        "id":"e1","sport_key":"soccer_test","commence_time":sample.fixtures[0].kickoff.isoformat(),
        "home_team":"A","away_team":"B","bookmakers":[{"key":"betclic_fr","last_update":NOW.isoformat(),
           "markets":[{"key":"h2h","outcomes":[{"name":"A","price":2.2},{"name":"Draw","price":3.4},{"name":"B","price":3.5}]}]}]}]}
    results={"provider":"api_football","fetched_at":NOW.isoformat(),"payload":{"errors":[],"response":[{
        "fixture":{"id":m.match_id,"date":m.kickoff.isoformat(),"status":{"short":"FT"}},
        "league":{"id":61,"name":"Test League"},"teams":{"home":{"name":m.home},"away":{"name":m.away}},
        "goals":{"home":m.home_goals,"away":m.away_goals}} for m in sample.history]}}
    mapping={"api_football:61":"soccer_test"}
    combined=build_snapshot(odds,[results],mapping,provenance="synthetic")
    assert len(combined.history)==80
    assert all(m.result_observed_at==NOW for m in combined.history)
    assert combined.source_references["competition_map_sha256"]
    ledger=Ledger(tmp_path/"combined.sqlite3");ledger.add_snapshot(combined.model_dump(mode="json"))
    pred=analyze(ledger,NOW.date(),NOW)["fixtures"][0]
    assert len(pred["models"])==3 and len(pred["comparisons"])==6 and pred["decision"]=="ABSTAIN"
    with pytest.raises(ValueError,match="mapping"):
        build_snapshot(odds,[results],{"api_football:61":"unobserved_competition"},provenance="synthetic")
    results["payload"]["response"][0]["fixture"]["status"]["short"]="AET"
    assert len(build_snapshot(odds,[results],mapping,provenance="synthetic").history)==79
    from v11.__main__ import main
    monkeypatch.setattr("v11.__main__.utc_now",lambda:NOW)
    for name,payload in (("odds",odds),("results",results),("mapping",{"competitions":mapping})):
        (tmp_path/(name+".json")).write_text(json.dumps(payload),encoding="utf-8")
    assert main(["--ledger",str(tmp_path/"cli.sqlite3"),"build-snapshot","--odds-file",str(tmp_path/"odds.json"),
                 "--results-file",str(tmp_path/"results.json"),"--mapping",str(tmp_path/"mapping.json"),
                 "--output",str(tmp_path/"consolidated.json"),"--provenance","synthetic"])==0
    assert len(Snapshot.model_validate_json((tmp_path/"consolidated.json").read_text()).history)==79
