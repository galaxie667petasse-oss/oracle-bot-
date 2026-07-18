import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from v10.agents import AgentFinding, mock_agent_findings
from v10.candidates import evaluate_candidate
from v10.config import load_settings
from v10.data_quality import FAIL, PASS, STALE, evaluate_fixture_quality
from v10.demo import build_demo_payload
from v10.odds import (
    clv_odds_pct,
    expected_value_per_unit,
    overround,
    parse_decimal_odds,
    proportional_no_vig,
)
from v10.risk import PaperRiskConfig, capped_paper_fraction, full_kelly_fraction
from v10.settlement import settle_market


def test_odds_normalization_and_ev():
    fair = proportional_no_vig({"home": 2.2, "draw": 3.4, "away": 3.3})
    assert round(sum(fair.values()), 8) == 1.0
    assert overround({"home": 2.2, "draw": 3.4, "away": 3.3}) > 1.0
    assert round(expected_value_per_unit(0.50, 2.20), 6) == 0.10
    assert round(clv_odds_pct(2.20, 2.00), 6) == 0.1
    try:
        parse_decimal_odds(1.0)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid odds accepted")


def test_settlement_markets():
    assert settle_market("match_winner", "home", 2.26, 1, 0).profit_units == 1.26
    assert settle_market("match_winner", "away", 2.26, 1, 0).result_status == "loss"
    assert settle_market("match_winner", "draw", 3.1, 1, 1).result_status == "win"
    assert settle_market("draw_no_bet", "home", 1.8, 1, 1).result_status == "push"
    assert settle_market("total_goals", "over", 1.9, 2, 1, line=2.5).result_status == "win"
    assert settle_market("both_teams_to_score", "yes", 1.7, 2, 1).result_status == "win"
    assert settle_market("match_winner", "home", 2.0, None, 1).settlement_status == "pending_result"


def test_quality_candidate_and_risk():
    now = datetime(2026, 8, 1, 12, tzinfo=timezone.utc)
    fixture = {
        "fixture_id": "f1",
        "home_team": "A",
        "away_team": "B",
        "league": "L",
        "kickoff_time": "2026-08-01T20:00:00+00:00",
        "recent_match_count": 6,
    }
    market = {"bookmaker_count": 3, "odds_observed_at": "2026-08-01T11:55:00+00:00"}
    report = evaluate_fixture_quality(fixture, market, now_utc=now)
    assert report.status == PASS
    candidate = evaluate_candidate("f1", "match_winner", "home", 2.2, 0.5, 0.43, 0.47, 0.54, report.status, 3)
    assert candidate.decision == "candidate"
    stale = evaluate_fixture_quality(fixture, {"bookmaker_count": 3, "odds_observed_at": "2026-08-01T08:00:00+00:00"}, now_utc=now)
    assert stale.status == STALE
    failed = evaluate_fixture_quality({**fixture, "away_team": "A"}, market, now_utc=now)
    assert failed.status == FAIL
    assert full_kelly_fraction(0.5, 2.2) > 0
    capped = capped_paper_fraction(0.5, 2.2, 0.04, config=PaperRiskConfig(max_signal_fraction=0.005))
    assert capped["paper_only"] is True
    assert capped["fraction"] <= 0.005


def test_agent_contract_and_demo():
    payload = build_demo_payload()
    assert payload["network_used"] is False
    assert payload["telegram_sent"] is False
    assert payload["final_judge"]["decision"] == "WATCH"
    findings = mock_agent_findings(payload["candidate"], "2026-08-01T10:00:00+00:00")
    assert len(findings) == 12
    AgentFinding.from_mapping(findings[0])
    bad = dict(findings[0])
    bad["verdict"] = "MAYBE"
    try:
        AgentFinding.from_mapping(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid agent finding accepted")


def test_config_safe_report_redacts_values():
    env = {
        "API_FOOTBALL_KEY": "secret_value",
        "OPENAI_API_KEY": "other_secret",
        "REAL_MONEY_ACTIONS_ENABLED": "false",
        "OPENAI_MODEL_FAST": "configured-model-name",
    }
    settings = load_settings(env)
    report = settings.safe_report(env)
    text = json.dumps(report)
    assert "secret_value" not in text
    assert "other_secret" not in text
    assert report["secrets_present"]["API_FOOTBALL_KEY"] is True
    assert report["openai_models_configured"]["fast"] is True


def test_app_cli_demo_json_and_secret_scan():
    output = subprocess.check_output([sys.executable, "app.py", "demo", "end-to-end", "--json"], text=True)
    payload = json.loads(output)
    assert payload["demo"] == "v10_end_to_end_offline"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".env.example").write_text("API_FOOTBALL_KEY=replace_me\n", encoding="utf-8")
        code = subprocess.call([sys.executable, "scripts/secret_scan.py", "--root", str(root)])
        assert code == 0
        (root / ".env").write_text("API_FOOTBALL_KEY=real-looking-value\n", encoding="utf-8")
        code = subprocess.call([sys.executable, "scripts/secret_scan.py", "--root", str(root)])
        assert code == 1


def main():
    old = dict(os.environ)
    try:
        test_odds_normalization_and_ev()
        test_settlement_markets()
        test_quality_candidate_and_risk()
        test_agent_contract_and_demo()
        test_config_safe_report_redacts_values()
        test_app_cli_demo_json_and_secret_scan()
        print("test_v10_foundation ok")
    finally:
        os.environ.clear()
        os.environ.update(old)


if __name__ == "__main__":
    main()
