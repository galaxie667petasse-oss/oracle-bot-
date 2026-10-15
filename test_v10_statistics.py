import json
import math
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import inspect

from v10.config import V10Settings
from v10.db.migrations import downgrade_base, migration_status, upgrade_head
from v10.statistics.calibration import PlattCalibrator, TemperatureScaler
from v10.statistics.dataset import TemporalDatasetBuilder
from v10.statistics.demo import synthetic_matches
from v10.statistics.dixon_coles import DixonColesModel, dixon_coles_log_likelihood, tau
from v10.statistics.elo import EloConfig, EloModel, expected_score, margin_multiplier
from v10.statistics.ensemble import EnsembleWeights, combine_probabilities, learn_weights_grid
from v10.statistics.markets import derive_1x2, derive_all_markets
from v10.statistics.poisson import PoissonModel, independent_poisson_distribution
from v10.statistics.training import predict_with_models, train_model
from v10.statistics.types import HistoricalMatch, TemporalContext


def make_match(idx, home="A", away="B", hg=1, ag=0, days=0):
    return HistoricalMatch(
        match_id=f"m{idx}",
        event_time=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=days),
        competition="T",
        season="2024",
        home_team=home,
        away_team=away,
        home_goals=hg,
        away_goals=ag,
        observed_at=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=days),
    )


def test_elo_core_behaviour():
    assert abs(expected_score(1500, 1500) - 0.5) < 1e-9
    assert expected_score(1550, 1500) > 0.5
    model = EloModel(EloConfig(k_factor=20, home_advantage=0))
    before_sum = model.rating("A") + model.rating("B")
    model.update(make_match(1, hg=3, ag=0))
    after_sum = model.rating("A") + model.rating("B")
    assert abs(before_sum - after_sum) < 1e-9
    assert model.rating("A") > 1500
    surprise = EloModel(EloConfig(k_factor=20, home_advantage=0))
    surprise.state.ratings["A"] = 1700
    surprise.state.ratings["B"] = 1300
    before = surprise.rating("B")
    surprise.update(make_match(2, hg=0, ag=1))
    assert surprise.rating("B") - before > 10
    draw_model = EloModel(EloConfig(k_factor=20, home_advantage=0))
    draw_model.update(make_match(3, hg=1, ag=1))
    assert abs(draw_model.rating("A") - 1500) < 1e-9
    assert margin_multiplier(8, 0) <= 1.8
    gap_before_regression = abs(model.rating("A") - 1500)
    model.regress_new_season()
    assert abs(model.rating("A") - 1500) < gap_before_regression


def test_poisson_distribution_and_markets():
    dist = independent_poisson_distribution(1.5, 1.0, 10, "test")
    assert abs(dist.total_mass() - 1.0) < 1e-9
    assert dist.tail_mass >= 0
    markets = derive_all_markets(dist)
    assert abs(sum(markets["match_winner"].values()) - 1.0) < 1e-9
    assert markets["double_chance"]["1x"] == markets["match_winner"]["home"] + markets["match_winner"]["draw"]
    assert 0 <= markets["draw_no_bet"]["push"] <= 1
    assert markets["over_under_1_5"]["over"] >= markets["over_under_2_5"]["over"]
    assert markets["over_under_2_5"]["over"] >= markets["over_under_3_5"]["over"]
    assert abs(sum(markets["both_teams_to_score"].values()) - 1.0) < 1e-9
    model = PoissonModel().fit([make_match(i, home="A", away="B", hg=2, ag=1, days=i) for i in range(12)])
    pred = model.predict("A", "B")
    assert pred.score_distribution.expected_home_goals > 0
    assert not math.isnan(pred.probabilities_1x2["home"])


def test_dixon_coles_tau_and_likelihood():
    assert tau(0, 0, 1.2, 1.0, -0.1) != 1.0
    assert tau(0, 1, 1.2, 1.0, -0.1) != 1.0
    assert tau(1, 0, 1.2, 1.0, -0.1) != 1.0
    assert tau(1, 1, 1.2, 1.0, -0.1) != 1.0
    assert tau(2, 2, 1.2, 1.0, -0.1) == 1.0
    try:
        tau(0, 0, 1.0, 1.0, 1.2)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid rho accepted")
    matches = [make_match(i, home="A", away="B", hg=i % 3, ag=(i + 1) % 2, days=i) for i in range(40)]
    model = DixonColesModel().fit(matches)
    assert math.isfinite(model.log_likelihood)
    assert math.isfinite(dixon_coles_log_likelihood(matches, model, model.rho))
    assert model.predict("A", "B").score_distribution.total_mass() > 0.999


def test_temporal_dataset_does_not_use_future():
    matches = [make_match(1, "A", "B", 1, 0, 0), make_match(2, "A", "C", 0, 3, 10)]
    rows, report = TemporalDatasetBuilder().build(matches)
    assert report.rows_included == 2
    first, second = rows
    assert first.features["home_team_matches"] == 0
    assert second.features["home_team_matches"] == 1
    old_features = dict(first.features)
    matches.append(make_match(3, "A", "D", 9, 0, 20))
    rows2, _ = TemporalDatasetBuilder().build(matches)
    assert rows2[0].features == old_features
    TemporalContext(
        fixture_id="x",
        decision_as_of=datetime(2024, 1, 2, tzinfo=UTC),
        data_cutoff=datetime(2024, 1, 2, tzinfo=UTC),
        training_cutoff=datetime(2024, 1, 1, tzinfo=UTC),
    )


def test_calibration_and_ensemble():
    probs = [0.1, 0.2, 0.8, 0.9] * 20
    labels = [0, 0, 1, 1] * 20
    result = PlattCalibrator().fit(probs, labels, min_samples=10)
    assert result.status in {"VALIDATED", "REJECTED_DEGRADED"}
    small = PlattCalibrator().fit([0.5], [1], min_samples=10)
    assert small.status == "FALLBACK_UNCALIBRATED"
    multi = [{"home": 0.5, "draw": 0.25, "away": 0.25}, {"home": 0.2, "draw": 0.3, "away": 0.5}] * 20
    scaler = TemperatureScaler()
    temp = scaler.fit(multi, ["home", "away"] * 20, min_samples=10)
    assert temp.parameters["temperature"] > 0
    weights = EnsembleWeights({"a": 0.5, "b": 0.5})
    combined = combine_probabilities({"a": {"home": 0.5, "draw": 0.3, "away": 0.2}, "b": {"home": 0.4, "draw": 0.3, "away": 0.3}}, weights)
    assert abs(sum(combined.values()) - 1.0) < 1e-9
    learned, metrics = learn_weights_grid(
        [{"a": {"home": 0.6, "draw": 0.2, "away": 0.2}, "b": {"home": 0.3, "draw": 0.3, "away": 0.4}}] * 8,
        ["home"] * 8,
        ["a", "b"],
        step=0.5,
    )
    learned.validate()
    assert metrics["sample_count"] == 8


def test_training_prediction_and_demo_cli():
    rows, _ = TemporalDatasetBuilder().build(synthetic_matches())
    assert train_model("elo_multiclass_v1", rows)["match_count"] == len(rows)
    assert train_model("poisson_independent_v1", rows)["artifact"]["converged"] is True
    assert train_model("dixon_coles_v1", rows)["artifact"]["converged"] is True
    fixture = make_match(99, "North FC", "Metro FC", 2, 0, 999)
    pred = predict_with_models([row.match for row in rows], fixture)
    assert abs(sum(pred["ensemble"].values()) - 1.0) < 1e-9
    output = subprocess.check_output([sys.executable, "app.py", "demo", "statistical-end-to-end", "--json"], text=True)
    payload = json.loads(output)
    assert payload["lab_only"] is True
    assert payload["warnings"]
    assert "ensemble" in payload


def test_statistical_migration_tables():
    with tempfile.TemporaryDirectory() as tmp:
        settings = V10Settings(DATABASE_URL=f"sqlite:///{Path(tmp, 'stats.sqlite').as_posix()}")
        up = upgrade_head(settings)
        assert up["current_revision"] == "20260719_0004"
        from v10.db.session import create_engine_from_settings

        engine = create_engine_from_settings(settings)
        try:
            names = set(inspect(engine).get_table_names())
            assert "v10_model_definitions" in names
            assert "v10_statistical_predictions" in names
        finally:
            engine.dispose()
        assert downgrade_base(settings)["current_revision"] is None


def main():
    test_elo_core_behaviour()
    test_poisson_distribution_and_markets()
    test_dixon_coles_tau_and_likelihood()
    test_temporal_dataset_does_not_use_future()
    test_calibration_and_ensemble()
    test_training_prediction_and_demo_cli()
    test_statistical_migration_tables()
    print("test_v10_statistics ok")


if __name__ == "__main__":
    main()
