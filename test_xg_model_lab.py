import csv
import tempfile
from pathlib import Path

import benchmark_governance
import xg_model_lab
from decision_policy import classify_strategy


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
        dates = [
            "2024-10-01",
            "2024-10-08",
            "2024-10-15",
            "2024-12-05",
            "2024-12-12",
            "2025-01-05",
            "2025-01-12",
            "2025-01-19",
        ]
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
                "odds": "1.90",
                "implied_probability": "0.526",
                "no_vig_probability": "0.52",
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


def main():
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

        report = xg_model_lab.build_xg_model_report(str(feature_path))
        assert report["rows_with_rolling_xg"] == 8
        assert report["splits"]["test"] == 3
        assert any("Echantillon test inferieur" in note for note in report.get("notes", []))
        decision = classify_strategy(report.get("governance_metrics", {}))
        assert decision["score"] <= 39 or decision["status"] in {"fragile / test absent", "echantillon faible"}

        benchmark = benchmark_governance.build_benchmark(str(root / "missing_features.csv"), db=synthetic_db(), xg_lab_path=str(feature_path))
        assert benchmark["summary"]["xg_lab_available"] is True
        assert any(entry["name"] == "epl_fbref_2024_2025_rolling_xg_lab" for entry in benchmark["registry"])
        xg_entry = next(entry for entry in benchmark["registry"] if entry["name"] == "epl_fbref_2024_2025_rolling_xg_lab")
        assert xg_entry["robustness_score"] <= 39
        assert xg_entry["decision"] != "candidate"

        assert oracle_db.read_text(encoding="utf-8") == before_db
        assert matches_csv.read_text(encoding="utf-8") == before_matches

    print("test_xg_model_lab ok")


if __name__ == "__main__":
    main()
