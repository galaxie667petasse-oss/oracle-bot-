import csv
import tempfile
from pathlib import Path

import model_trainer
from feature_builder import FEATURE_COLUMNS
from model_trainer import (
    build_training_report,
    choose_threshold_on_validation,
    edge_simulation,
    fit_feature_transformer,
    read_feature_rows,
    temporal_split,
)


def make_row(date, result, odds, no_vig, market_type="h2h", competition="TRAIN", **extra):
    row = {column: "" for column in FEATURE_COLUMNS}
    row.update({
        "date": date,
        "year": date[:4],
        "period_bucket": "modern_2015_2019",
        "market_type": market_type,
        "pari": "Victoire Alpha" if market_type == "h2h" else "Plus de 2.5 buts",
        "result": result,
        "target_win": 1 if result == "win" else 0,
        "odds": odds,
        "odds_bucket": "mid",
        "implied_probability": round(1 / odds, 6),
        "no_vig_probability": no_vig,
        "market_margin": 0.02,
        "fair_odds_market": round(1 / no_vig, 4),
        "ev_market_baseline": round(no_vig * odds - 1, 6),
        "elo_diff": 80 if result == "win" else -20,
        "elo_abs_diff": 80 if result == "win" else 20,
        "elo_bucket": "elo_home_modere" if result == "win" else "elo_equilibre",
        "form3_diff": 2 if result == "win" else -1,
        "form5_diff": 3 if result == "win" else -2,
        "is_h2h": 1 if market_type == "h2h" else 0,
        "is_total": 1 if market_type == "total" else 0,
        "is_favorite": 1 if odds < 2 else 0,
        "is_mid_odds": 1,
        "is_home_pick": 1 if market_type == "h2h" else 0,
        "is_over": 1 if market_type == "total" else 0,
        "shots_diff": 5 if result == "win" else -4,
        "total_shots": 22,
        "target_diff": 2 if result == "win" else -2,
        "total_target": 8,
        "corners_diff": 1,
        "total_corners": 10,
        "both_teams_scored": 1,
        "home_team_goals_for_avg5": 1.4 if result == "win" else 0.8,
        "home_team_goals_against_avg5": 0.7 if result == "win" else 1.6,
        "away_team_goals_for_avg5": 1.0,
        "away_team_goals_against_avg5": 1.2,
        "home_team_btts_rate5": 0.4,
        "away_team_btts_rate5": 0.6,
        "home_team_over25_rate5": 0.5,
        "away_team_over25_rate5": 0.5,
        "competition": competition,
    })
    row.update(extra)
    return row


def write_csv(path, rows):
    with Path(path).open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FEATURE_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    rows = [
        make_row("2019-01-01", "win", 1.8, 0.55),
        make_row("2020-01-01", "loss", 2.2, 0.45),
        make_row("2021-01-01", "win", 1.7, 0.57),
        make_row("2022-01-01", "loss", 2.4, 0.42),
        make_row("2023-01-01", "win", 1.9, 0.52, competition="VALID"),
        make_row("2023-02-01", "loss", 2.1, 0.48, competition="VALID"),
        make_row("2024-01-01", "loss", 1.8, 0.54, competition="TEST_ONLY"),
        make_row("2024-02-01", "win", 2.0, 0.50, competition="TEST_ONLY"),
        make_row("2024-03-01", "win", 1.9, 0.52, market_type="total", competition="TEST_ONLY"),
    ]

    splits = temporal_split(rows)
    assert len(splits["train"]) == 4
    assert len(splits["validation"]) == 2
    assert len(splits["test"]) == 3

    if model_trainer.np is not None:
        transformer = fit_feature_transformer(splits["train"])
        assert "TRAIN" in transformer.categories["competition"]
        assert "TEST_ONLY" not in transformer.categories["competition"]
        empty = edge_simulation([], model_trainer.np.asarray([], dtype=model_trainer.np.float32))
        assert all(stat["picks"] == 0 for stat in empty.values())

    validation_sim = {
        0.01: {"picks": 300, "roi": 1.0},
        0.02: {"picks": 300, "roi": 4.0},
        0.03: {"picks": 20, "roi": 50.0},
        0.05: {"picks": 0, "roi": 0.0},
    }
    threshold, reason = choose_threshold_on_validation(validation_sim)
    assert threshold == 0.02
    assert "validation" in reason

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "features.csv"
        write_csv(path, rows)
        loaded = read_feature_rows(str(path))
        assert len(loaded) == len(rows)
        report = build_training_report(str(path))
        assert report.get("splits", {}).get("train") == 4
        assert report.get("splits", {}).get("validation") == 2
        assert report.get("splits", {}).get("test") == 3
        assert report.get("excluded_post_match_features")
        assert any(item["name"] == "Baseline sans rolling" for item in report.get("feature_sets", []))
        assert any(item["name"] == "Modele avec rolling pre-match" for item in report.get("feature_sets", []))
        baseline = next(item for item in report["feature_sets"] if item["name"] == "Baseline sans rolling")
        rolling = next(item for item in report["feature_sets"] if item["name"] == "Modele avec rolling pre-match")
        assert "shots_diff" not in baseline["numeric_features"]
        assert "home_team_goals_for_avg5" not in baseline["numeric_features"]
        assert "home_team_goals_for_avg5" in rolling["numeric_features"]
        if model_trainer.np is not None:
            assert "models" in report
        allow_report = build_training_report(str(path), allow_post_match_features=True)
        allow_baseline = next(item for item in allow_report["feature_sets"] if item["name"] == "Baseline sans rolling")
        assert allow_report["excluded_post_match_features"] == []
        assert "shots_diff" in allow_baseline["numeric_features"]
        market_report = build_training_report(str(path), market="total")
        assert market_report.get("error") or market_report.get("splits", {}).get("test") == 1

    print("test_model_trainer ok")


if __name__ == "__main__":
    main()
