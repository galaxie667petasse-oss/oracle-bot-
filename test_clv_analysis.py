import csv
import tempfile
from pathlib import Path

import clv_analysis


def write_csv(path: Path, fieldnames, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = root / "oracle_db.json"
        db.write_text("{}", encoding="utf-8")
        before = db.read_text(encoding="utf-8")

        fieldnames = ["date", "market_type", "strategy_name", "odds", "closing_odds", "result"]
        positive_path = root / "features_positive.csv"
        write_csv(positive_path, fieldnames, [{
            "date": "2024-01-01",
            "market_type": "h2h",
            "strategy_name": "s1",
            "odds": "2.10",
            "closing_odds": "2.00",
            "result": "win",
        }])
        positive = clv_analysis.analyze_clv(str(positive_path))
        assert positive["status"] == "disponible"
        assert positive["summary"]["clv_mean"] > 0
        assert positive["summary"]["clv_prob_edge_mean"] > 0

        negative_path = root / "features_negative.csv"
        write_csv(negative_path, fieldnames, [{
            "date": "2024-01-01",
            "market_type": "h2h",
            "strategy_name": "s1",
            "odds": "1.90",
            "closing_odds": "2.00",
            "result": "loss",
        }])
        negative = clv_analysis.analyze_clv(str(negative_path))
        assert negative["summary"]["clv_mean"] < 0
        assert negative["verdict"] == "CLV negatif"

        grouped_path = root / "features_grouped.csv"
        write_csv(grouped_path, fieldnames, [
            {"date": "2024-01-01", "market_type": "h2h", "strategy_name": "s1", "odds": "2.10", "closing_odds": "2.00", "result": "win"},
            {"date": "2024-01-02", "market_type": "total", "strategy_name": "s2", "odds": "1.80", "closing_odds": "1.90", "result": "loss"},
        ])
        grouped = clv_analysis.analyze_clv(str(grouped_path))
        assert grouped["groups"]["by_market"]["h2h"]["n"] == 1
        assert grouped["groups"]["by_market"]["total"]["n"] == 1
        assert grouped["groups"]["by_strategy"]["s1"]["clv_mean"] > 0

        absent_path = root / "features_no_closing.csv"
        write_csv(absent_path, ["date", "market_type", "odds"], [{"date": "2024-01-01", "market_type": "h2h", "odds": "2.00"}])
        absent = clv_analysis.analyze_clv(str(absent_path))
        assert absent["status"] == "indisponible"
        assert "Closing odds indisponibles" in absent["message"]

        pinnacle_path = root / "features_pinnacle.csv"
        write_csv(pinnacle_path, ["date", "market_type", "odds", "C_PHB", "is_home_pick", "odds_source"], [{
            "date": "2025-08-01",
            "market_type": "h2h",
            "odds": "2.10",
            "C_PHB": "2.00",
            "is_home_pick": "1",
            "odds_source": "Pinnacle",
        }])
        pinnacle = clv_analysis.analyze_clv(str(pinnacle_path))
        assert any("Pinnacle" in warning for warning in pinnacle["warnings"])

        json_path = root / "reports" / "clv_report.json"
        html_path = root / "reports" / "clv_report.html"
        clv_analysis.write_json(grouped, str(json_path))
        clv_analysis.write_html(grouped, str(html_path))
        assert json_path.exists()
        assert html_path.exists()
        assert db.read_text(encoding="utf-8") == before

    print("test_clv_analysis ok")


if __name__ == "__main__":
    main()
