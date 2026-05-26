import csv
import tempfile
from pathlib import Path

import benchmark_governance
import xg_model_lab


def write_rows(path: Path) -> None:
    fieldnames = [
        "date",
        "home",
        "away",
        "market_type",
        "pari",
        "result",
        "target_win",
        "odds",
        "implied_probability",
        "no_vig_probability",
        "market_margin",
        "elo_diff",
        "elo_abs_diff",
        "form3_diff",
        "form5_diff",
        *xg_model_lab.XG_FEATURES,
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        dates = (
            [f"2021-09-{(idx % 28) + 1:02d}" for idx in range(40)]
            + [f"2023-09-{(idx % 28) + 1:02d}" for idx in range(40)]
            + [f"2024-09-{(idx % 28) + 1:02d}" for idx in range(40)]
        )
        for index, date in enumerate(dates):
            win = index % 2 == 0
            row = {
                "date": date,
                "home": f"Home {index}",
                "away": f"Away {index}",
                "market_type": "h2h",
                "pari": "Victoire Home",
                "result": "win" if win else "loss",
                "target_win": "1" if win else "0",
                "odds": "2.00",
                "implied_probability": "0.50",
                "no_vig_probability": "0.50",
                "market_margin": "0.02",
                "elo_diff": str(20 + index),
                "elo_abs_diff": str(20 + index),
                "form3_diff": str(index - 3),
                "form5_diff": str(index - 2),
            }
            for feature in xg_model_lab.XG_FEATURES:
                row[feature] = "1.0"
            row["xg_diff_avg3"] = str(0.2 if win else -0.2)
            row["xg_diff_avg5"] = str(0.1 if win else -0.1)
            writer.writerow(row)


def synthetic_db():
    return {"scans": {"empty": {"picks": [], "candidates": []}}}


def fake_train_predict(_fit_rows, predict_rows, features):
    has_xg = "xg_diff_avg3" in features
    if has_xg:
        return [0.70 if row.get("result") == "win" else 0.30 for row in predict_rows]
    return [0.52 for _row in predict_rows]


def main():
    original_train_predict = xg_model_lab.train_predict
    original_sklearn_available = xg_model_lab.sklearn_available
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        feature_path = root / "reports" / "xg.csv"
        oracle_db = root / "oracle_db.json"
        matches_csv = root / "data" / "MATCHES.csv"
        oracle_db.write_text("{}", encoding="utf-8")
        matches_csv.parent.mkdir(parents=True, exist_ok=True)
        matches_csv.write_text("date,home,away\n", encoding="utf-8")
        before_db = oracle_db.read_text(encoding="utf-8")
        before_matches = matches_csv.read_text(encoding="utf-8")
        write_rows(feature_path)

        xg_model_lab.train_predict = fake_train_predict
        xg_model_lab.sklearn_available = lambda: True
        report = xg_model_lab.build_xg_model_report(str(feature_path))
        assert report["rows_with_rolling_xg"] == 120
        assert report["splits"]["fit"] == 40
        assert report["splits"]["validation"] == 40
        assert report["splits"]["test"] == 40
        assert report["split_unique_matches"]["test"] == 40
        assert report["comparison"]["delta_brier_xg_vs_without_xg"] < 0
        assert report["verdict"]["promotion_allowed"] is False
        assert "CLV absente" in report["verdict"]["rejection_reasons"]
        assert "sample edge test inferieur a 1000" in report["verdict"]["rejection_reasons"]

        negative_verdict = xg_model_lab.build_verdict({
            "comparison": {
                "delta_brier_xg_vs_without_xg": -0.01,
                "delta_log_loss_xg_vs_without_xg": -0.01,
                "delta_brier_xg_vs_market": -0.01,
                "delta_log_loss_xg_vs_market": -0.01,
            }
        }, {"selected_test": {"picks": 1200, "roi": -0.1}})
        assert negative_verdict["xg_improves_brier"] is True
        assert negative_verdict["edge_test_positive"] is False
        assert negative_verdict["promotion_allowed"] is False
        assert "observation technique" in negative_verdict["governance_note"]

        json_path = root / "reports" / "xg_model.json"
        html_path = root / "reports" / "xg_model.html"
        xg_model_lab.write_json(report, str(json_path))
        xg_model_lab.write_html(report, str(html_path))
        assert json_path.exists()
        assert html_path.exists()

        xg_model_lab.sklearn_available = lambda: False
        no_sklearn = xg_model_lab.build_xg_model_report(str(feature_path))
        assert "sklearn indisponible" in no_sklearn["error"]

        benchmark = benchmark_governance.build_benchmark(str(root / "missing_features.csv"), db=synthetic_db(), xg_lab_path=str(feature_path))
        assert benchmark["summary"]["xg_lab_available"] is True
        assert any(entry["type"] == "external_lab" for entry in benchmark["registry"])
        xg_entry = next(entry for entry in benchmark["registry"] if entry["type"] == "external_lab" and "rolling_xg" in entry["name"])
        assert xg_entry["decision"] != "candidate"

        assert oracle_db.read_text(encoding="utf-8") == before_db
        assert matches_csv.read_text(encoding="utf-8") == before_matches

    xg_model_lab.train_predict = original_train_predict
    xg_model_lab.sklearn_available = original_sklearn_available
    print("test_xg_model_lab ok")


if __name__ == "__main__":
    main()
