import tempfile
from pathlib import Path

import odds_snapshot_store
import odds_source_quality_report


def row(near="true", odds="2.10", market="h2h"):
    return {
        "captured_at": "2026-06-01T10:00:00",
        "source": "manual_csv",
        "league": "EPL",
        "match_date": "2026-06-01",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "bookmaker": "Book",
        "market_type": market,
        "side": "home" if market == "h2h" else "over",
        "odds": odds,
        "is_near_close": near,
    }


def main():
    with tempfile.TemporaryDirectory() as tmp:
        snapshots = Path(tmp) / "reports" / "odds.csv"
        odds_snapshot_store.append_snapshot_rows(str(snapshots), [row(), row(market="total"), row(odds="0.5")])
        report = odds_source_quality_report.build_quality_report(str(snapshots))
        assert report["rows_total"] == 3
        assert report["invalid_rows"] == 1
        assert report["near_close_rows"] == 2
        assert report["clv_capacity"] == "usable"
        json_out = Path(tmp) / "reports" / "quality.json"
        html_out = Path(tmp) / "reports" / "quality.html"
        odds_source_quality_report.write_json(report, str(json_out))
        odds_source_quality_report.write_html(report, str(html_out))
        assert json_out.exists()
        assert html_out.exists()

    print("test_odds_source_quality_report ok")


if __name__ == "__main__":
    main()
