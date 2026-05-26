import csv
import tempfile
from pathlib import Path

import statistical_validation as sv


def write_csv(path: Path, fieldnames, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    negative = [-1.0 for _ in range(40)] + [0.8 for _ in range(10)]
    negative_ci = sv.estimate_roi_confidence_interval(negative)
    assert negative_ci["roi"] < 0

    noisy_positive = [1.0 for _ in range(51)] + [-1.0 for _ in range(49)]
    noisy_ci = sv.estimate_roi_confidence_interval(noisy_positive)
    assert noisy_ci["roi"] > 0
    assert noisy_ci["ci_low"] < 0

    big_positive = [0.08 for _ in range(1500)]
    big_ci = sv.estimate_roi_confidence_interval(big_positive)
    assert big_ci["roi"] > 0
    assert big_ci["ci_low"] > 0
    big_boot = sv.bootstrap_roi(big_positive, n_boot=200)
    assert big_boot["p05"] > 0

    adjusted = sv.multiple_testing_adjustment([0.001, 0.02, 0.2])
    assert adjusted[0] <= 0.01
    assert adjusted[1] <= 0.05
    assert adjusted[2] == 0.2

    assert sv.sample_size_needed(0.02) == 9604
    mc = sv.monte_carlo_roi(edge=0.01, odds_mean=2.0, n_picks=100, n_sims=50)
    assert mc["p50"] is not None
    dd = sv.max_drawdown_simulation([1.0, -1.0, -1.0, 1.0], n_sims=20)
    assert dd["observed"] >= 2.0

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = root / "oracle_db.json"
        db.write_text("{}", encoding="utf-8")
        before = db.read_text(encoding="utf-8")

        rows = []
        for index in range(320):
            rows.append({
                "strategy_name": "negative",
                "odds": "2.0",
                "result": "loss" if index < 220 else "win",
            })
        for index in range(1200):
            rows.append({
                "strategy_name": "positive",
                "odds": "2.0",
                "result": "win" if index < 660 else "loss",
            })
        path = root / "features.csv"
        write_csv(path, ["strategy_name", "odds", "result"], rows)
        report = sv.build_statistical_report(str(path), strategy_column="strategy_name")
        assert report["status"] == "disponible"
        assert report["summary"]["n_picks"] == len(rows)
        assert report["by_strategy"]["negative"]["roi_observed"] < 0
        assert report["by_strategy"]["positive"]["roi_observed"] > 0
        assert report["by_strategy"]["positive"]["bootstrap_roi"]["p05"] > 0
        assert report["by_strategy"]["positive"]["p_value_adjusted"] is not None

        json_path = root / "reports" / "statistical_validation.json"
        html_path = root / "reports" / "statistical_validation.html"
        sv.write_json(report, str(json_path))
        sv.write_html(report, str(html_path))
        assert json_path.exists()
        assert html_path.exists()
        assert db.read_text(encoding="utf-8") == before

    print("test_statistical_validation ok")


if __name__ == "__main__":
    main()
