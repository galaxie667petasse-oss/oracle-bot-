import csv
import tempfile
from pathlib import Path

import historical_clv_backtester
from historical_clv_importer import OUTPUT_COLUMNS


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "reports" / "historical_clv.csv"
        source.parent.mkdir(parents=True, exist_ok=True)
        with source.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerow({"match_date": "2024-01-01", "league": "EPL", "bookmaker": "Book", "market_type": "h2h", "side": "home", "opening_odds": "2.0", "closing_odds": "1.9", "clv_percent": "0.052631", "result": "home", "profit_unit": "1.0", "is_valid": "True"})
            writer.writerow({"match_date": "2024-01-02", "league": "EPL", "bookmaker": "Book", "market_type": "h2h", "side": "away", "opening_odds": "2.5", "closing_odds": "2.6", "clv_percent": "-0.038461", "result": "home", "profit_unit": "-1.0", "is_valid": "True"})
        report = historical_clv_backtester.build_backtest(str(source))
        assert report["summary"]["sample"] == 2
        assert "league" in report["splits"]
        assert report["verdict"] == "historical_evidence_only"
        out = root / "reports" / "backtest.json"
        html = root / "reports" / "backtest.html"
        historical_clv_backtester.write_json(report, str(out))
        historical_clv_backtester.write_html(report, str(html))
        assert out.exists() and html.exists()
    print("test_historical_clv_backtester ok")


if __name__ == "__main__":
    main()
