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

        preview_path = root / "features_preview.csv"
        write_csv(
            preview_path,
            ["date", "market_type", "pari", "odds", "closing_odds", "clv_percent", "clv_available", "is_home_pick", "is_away_pick", "is_draw", "is_over", "result"],
            [
                {"date": "2024-01-01", "market_type": "h2h", "pari": "Victoire A", "odds": "2.10", "closing_odds": "2.00", "clv_percent": "0.05", "clv_available": "True", "is_home_pick": "1", "is_away_pick": "0", "is_draw": "0", "is_over": "0", "result": "win"},
                {"date": "2024-01-02", "market_type": "h2h", "pari": "Victoire B", "odds": "4.20", "closing_odds": "4.00", "clv_percent": "0.05", "clv_available": "True", "is_home_pick": "0", "is_away_pick": "1", "is_draw": "0", "is_over": "0", "result": "loss"},
                {"date": "2024-01-03", "market_type": "draw", "pari": "Nul", "odds": "3.20", "closing_odds": "", "clv_percent": "", "clv_available": "False", "is_home_pick": "0", "is_away_pick": "0", "is_draw": "1", "is_over": "0", "result": "loss"},
                {"date": "2024-01-04", "market_type": "total", "pari": "Plus de 2.5", "odds": "1.90", "closing_odds": "", "clv_percent": "", "clv_available": "False", "is_home_pick": "0", "is_away_pick": "0", "is_draw": "0", "is_over": "1", "result": "win"},
            ],
        )
        partial = clv_analysis.analyze_clv(str(preview_path))
        assert partial["status"] == "partiel"
        assert partial["clv_scope"] == "partial_h2h_home_away"
        assert partial["rows_total"] == 4
        assert partial["rows_with_closing"] == 2
        assert partial["coverage_global"] == 50.0
        assert partial["groups"]["by_market"]["h2h"]["n"] == 2
        assert "draw" not in partial["groups"]["by_market"]
        assert "total" not in partial["groups"]["by_market"]
        assert partial["coverage_by_market_side"]["h2h_draw"]["with_clv"] == 0

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
