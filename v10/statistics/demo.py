from __future__ import annotations

from datetime import UTC, datetime, timedelta

from v10.odds import proportional_no_vig

from .backtest import WalkForwardConfig, walk_forward_backtest
from .dataset import TemporalDatasetBuilder
from .market import compare_1x2_market
from .metrics import multiclass_brier, multiclass_log_loss
from .training import predict_with_models, train_model
from .types import HistoricalMatch


def synthetic_matches() -> list[HistoricalMatch]:
    teams = ["North FC", "South FC", "East FC", "West FC", "River FC", "Metro FC"]
    strengths = {"North FC": 2, "South FC": 1, "East FC": 0, "West FC": -1, "River FC": 1, "Metro FC": -2}
    start = datetime(2024, 8, 1, tzinfo=UTC)
    matches = []
    idx = 0
    for season in ("2024", "2025", "2026"):
        for round_idx in range(10):
            for offset in range(0, len(teams), 2):
                home = teams[(offset + round_idx) % len(teams)]
                away = teams[(offset + round_idx + 3) % len(teams)]
                if home == away:
                    continue
                diff = strengths[home] - strengths[away]
                home_goals = max(0, 1 + (1 if diff > 0 else 0) + (round_idx + offset) % 2)
                away_goals = max(0, 1 + (1 if diff < -1 else 0) - (1 if diff > 2 else 0))
                matches.append(
                    HistoricalMatch(
                        match_id=f"synthetic:{idx}",
                        event_time=start + timedelta(days=idx * 4),
                        competition="SYN",
                        season=season,
                        home_team=home,
                        away_team=away,
                        home_goals=home_goals,
                        away_goals=away_goals,
                        odds_home=2.1,
                        odds_draw=3.4,
                        odds_away=3.2,
                        observed_at=start + timedelta(days=idx * 4),
                    )
                )
                idx += 1
    return matches


def run_statistical_demo() -> dict:
    history = synthetic_matches()
    future_fixture = HistoricalMatch(
        match_id="synthetic:future:1",
        event_time=datetime(2026, 12, 15, tzinfo=UTC),
        competition="SYN",
        season="2026",
        home_team="North FC",
        away_team="Metro FC",
        home_goals=2,
        away_goals=0,
        odds_home=2.15,
        odds_draw=3.55,
        odds_away=3.35,
        observed_at=datetime(2026, 12, 14, 12, tzinfo=UTC),
    )
    builder = TemporalDatasetBuilder()
    rows, dataset_report = builder.build(history)
    training_reports = {
        "elo_multiclass_v1": train_model("elo_multiclass_v1", rows),
        "poisson_independent_v1": train_model("poisson_independent_v1", rows),
        "dixon_coles_v1": train_model("dixon_coles_v1", rows),
        "ensemble_v1": train_model("ensemble_v1", rows),
    }
    prediction = predict_with_models(history, future_fixture)
    odds = {"home": 2.15, "draw": 3.55, "away": 3.35}
    market_fair = proportional_no_vig(odds)
    comparisons = compare_1x2_market(
        fixture_id=future_fixture.match_id,
        model_probabilities=prediction["ensemble"],
        odds=odds,
        odds_observed_at=future_fixture.observed_at.isoformat() if future_fixture.observed_at else "",
        bookmaker_count=3,
    )
    backtest = walk_forward_backtest(rows, WalkForwardConfig(train_size=45, test_size=15, step_size=15))
    labels = [str(row.labels["result"]) for row in rows[-10:]]
    naive_probs = [prediction["ensemble"] for _ in labels]
    return {
        "dataset": dataset_report.to_dict(),
        "training": training_reports,
        "fixture_id": future_fixture.match_id,
        "as_of": future_fixture.observed_at.isoformat(),
        "models": {
            key: value["probabilities_1x2"]
            for key, value in ((k, v) for k, v in prediction["models"].items())
        },
        "ensemble": prediction["ensemble"],
        "markets": prediction["models"]["dixon_coles_v1"]["markets"],
        "market_fair": market_fair,
        "comparisons": [row.__dict__ for row in comparisons],
        "candidate_count": sum(1 for row in comparisons if row.candidate_decision == "candidate"),
        "paper_only": True,
        "demo_metrics": {
            "illustrative_log_loss": multiclass_log_loss(naive_probs, labels) if labels else None,
            "illustrative_brier": multiclass_brier(naive_probs, labels) if labels else None,
        },
        "backtest": backtest,
        "warnings": ["synthetic_data_only", "no_profit_claim", "no_llm_used"],
        "lab_only": True,
        "can_influence_picks": False,
    }
