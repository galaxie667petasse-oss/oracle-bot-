import json
from datetime import datetime, timezone
from typing import Any

from .agents import mock_agent_findings
from .candidates import CandidateThresholds, evaluate_candidate
from .data_quality import evaluate_fixture_quality
from .final_judge import deterministic_final_judge
from .odds import clv_odds_pct, proportional_no_vig
from .risk import capped_paper_fraction
from .settlement import settle_market


def build_demo_payload() -> dict[str, Any]:
    observed_at = "2026-08-01T10:00:00+00:00"
    now = datetime(2026, 8, 1, 10, 5, tzinfo=timezone.utc)
    fixture = {
        "fixture_id": "demo-fixture-001",
        "home_team": "Ghana Demo",
        "away_team": "Panama Demo",
        "league": "World Demo Cup",
        "kickoff_time": "2026-08-01T18:00:00+00:00",
        "status": "scheduled",
        "recent_match_count": 8,
    }
    odds = {"home": 2.20, "draw": 3.40, "away": 3.30}
    fair = proportional_no_vig(odds)
    market = {
        "bookmaker_count": 4,
        "odds_observed_at": observed_at,
        "best_bookmaker": "DemoBook",
        "market_key": "match_winner",
    }
    quality = evaluate_fixture_quality(fixture, market, now_utc=now)
    candidate = evaluate_candidate(
        fixture_id=fixture["fixture_id"],
        market_key="match_winner",
        selection_key="home",
        decimal_odds=odds["home"],
        p_model=0.50,
        p_market_fair=fair["home"],
        uncertainty_low=0.47,
        uncertainty_high=0.54,
        data_quality_status=quality.status,
        bookmaker_count=market["bookmaker_count"],
        thresholds=CandidateThresholds(),
    ).to_dict()
    candidate["odds_observed_at"] = observed_at
    candidate["uncertainty_low"] = 0.47
    candidate["uncertainty_high"] = 0.54
    findings = mock_agent_findings(candidate, observed_at=observed_at)
    judge = deterministic_final_judge(candidate, findings)
    risk = capped_paper_fraction(
        candidate["p_model"],
        candidate["decimal_odds"],
        candidate["uncertainty_width"],
    )
    settlement = settle_market("match_winner", "home", odds["home"], 2, 1, fixture_status="FT").to_dict()
    closing_odds = 2.05
    telegram_preview = "\n".join(
        [
            "ORACLE V10 SHADOW LAB - PREVIEW",
            "Match : Ghana Demo - Panama Demo",
            "Decision : " + judge["decision"],
            "Marche : match_winner home",
            "Cote : 2.20 DemoBook",
            f"P modele : {candidate['p_model']:.2%}",
            f"P marche fair : {candidate['p_market_fair']:.2%}",
            f"EV : {candidate['expected_value_per_unit']:.3f}u",
            "Statut : paper betting uniquement, aucune mise.",
        ]
    )
    return {
        "schema_version": "1.0",
        "demo": "v10_end_to_end_offline",
        "fixture": fixture,
        "market_fair_probabilities": fair,
        "quality_report": quality.to_dict(),
        "candidate": candidate,
        "agents": findings,
        "final_judge": judge,
        "risk": risk,
        "telegram_preview": telegram_preview,
        "settlement": settlement,
        "closing_odds": closing_odds,
        "clv_odds_pct": round(clv_odds_pct(odds["home"], closing_odds), 6),
        "lab_only": True,
        "can_influence_picks": False,
        "network_used": False,
        "telegram_sent": False,
    }


def print_demo_summary(payload: dict[str, Any]) -> None:
    candidate = payload["candidate"]
    settlement = payload["settlement"]
    print("Demo V10 end-to-end offline")
    print(f"- Fixture: {payload['fixture']['fixture_id']}")
    print(f"- Data quality: {payload['quality_report']['status']}")
    print(f"- Candidate: {candidate['decision']} EV={candidate['expected_value_per_unit']} edge={candidate['edge_probability_points']}")
    print(f"- Final judge: {payload['final_judge']['decision']}")
    print(f"- Telegram: preview uniquement, aucun envoi")
    print(f"- Settlement fictif: {settlement['result_status']} profit={settlement['profit_units']}u")
    print(f"- CLV odds pct: {payload['clv_odds_pct']}")
    print("- Aucune mise. Laboratoire local uniquement.")


def main(argv: list[str] | None = None) -> int:
    argv = argv or []
    payload = build_demo_payload()
    if "--json" in argv:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_demo_summary(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

