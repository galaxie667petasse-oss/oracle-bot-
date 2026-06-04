import json
import tempfile
from pathlib import Path

import api_football_odds_debug_report as debug_report
from odds_normalizer import normalize_odds_rows, write_normalized_csv


def write_odds(path: Path):
    rows = normalize_odds_rows([
        {
            "captured_at": "2026-06-04T09:00:00",
            "source": "api_football",
            "source_event_id": "evt1",
            "league": "Serie A",
            "match_date": "2026-06-04",
            "kickoff_time": "2026-06-04T18:00:00+00:00",
            "home_team": "Parma",
            "away_team": "Napoli",
            "bookmaker": "Book A",
            "market_type": "h2h",
            "side": "home",
            "odds": "2.10",
            "raw_payload_ref": "fixture_id=evt1;status=NS",
        },
        {
            "captured_at": "2026-06-04T09:00:00",
            "source": "api_football",
            "source_event_id": "evt2",
            "league": "Serie A",
            "match_date": "2026-06-04",
            "kickoff_time": "2026-06-04T12:00:00+00:00",
            "home_team": "Milan",
            "away_team": "Inter",
            "bookmaker": "Book B",
            "market_type": "h2h",
            "side": "away",
            "odds": "2.40",
            "raw_payload_ref": "fixture_id=evt2;status=FT",
        },
        {
            "captured_at": "2026-06-04T09:00:00",
            "source": "api_football",
            "source_event_id": "evt3",
            "league": "Serie A",
            "match_date": "2026-06-04",
            "kickoff_time": "2026-06-04T20:00:00+00:00",
            "home_team": "Roma",
            "away_team": "Lazio",
            "bookmaker": "Book A",
            "market_type": "total",
            "side": "over",
            "odds": "1.90",
            "raw_payload_ref": "fixture_id=evt3;status=NS",
        },
        {
            "captured_at": "2026-06-04T09:00:00",
            "source": "api_football",
            "source_event_id": "evt4",
            "league": "Serie A",
            "match_date": "2026-06-04",
            "kickoff_time": "2026-06-04T21:00:00+00:00",
            "home_team": "",
            "away_team": "",
            "bookmaker": "Book A",
            "market_type": "h2h",
            "side": "home",
            "odds": "2.00",
            "raw_payload_ref": "fixture_id=evt4;status=NS",
        },
    ], source="api_football")
    write_normalized_csv(rows, str(path))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        odds = root / "reports" / "odds.csv"
        output = root / "reports" / "debug.json"
        html = root / "reports" / "debug.html"
        write_odds(odds)
        report = debug_report.build_debug_report(str(odds))
        assert report["total_rows"] == 4
        assert report["valid_h2h_count"] == 2
        assert report["valid_h2h_not_finished_count"] == 1
        assert report["status_counts"]["NS"] == 3
        assert report["status_counts"]["FT"] == 1
        assert report["valid_h2h_by_bookmaker"]["Book A"] == 1
        assert report["examples_selected_candidates"]
        debug_report.write_json(report, str(output))
        debug_report.write_html(report, str(html))
        assert json.loads(output.read_text(encoding="utf-8"))["valid_h2h_count"] == 2
        assert html.exists()
        assert debug_report.main(["--odds", str(odds), "--output", str(output), "--html", str(html)]) == 0
    print("test_api_football_odds_debug_report ok")


if __name__ == "__main__":
    main()
