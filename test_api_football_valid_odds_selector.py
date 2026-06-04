import csv
import json
import tempfile
from pathlib import Path

import api_football_valid_odds_selector as selector
from odds_normalizer import ODDS_COLUMNS, normalize_odds_rows, write_normalized_csv


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
            "is_near_close": "False",
        },
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
            "side": "away",
            "odds": "3.20",
            "is_near_close": "False",
        },
        {
            "captured_at": "2026-06-04T09:00:00",
            "source": "api_football",
            "source_event_id": "evt2",
            "league": "Serie A",
            "match_date": "2026-06-04",
            "kickoff_time": "2026-06-04T20:00:00+00:00",
            "home_team": "Milan",
            "away_team": "Inter",
            "bookmaker": "Book B",
            "market_type": "h2h",
            "side": "draw",
            "odds": "3.40",
            "is_near_close": "False",
        },
        {
            "captured_at": "2026-06-04T09:00:00",
            "source": "api_football",
            "source_event_id": "evt3",
            "league": "Serie A",
            "match_date": "2026-06-04",
            "kickoff_time": "2026-06-04T21:00:00+00:00",
            "home_team": "Roma",
            "away_team": "Lazio",
            "bookmaker": "Book A",
            "market_type": "h2h",
            "side": "home",
            "odds": "2.00",
            "is_near_close": "True",
        },
    ], source="api_football")
    write_normalized_csv(rows, str(path))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        odds = root / "reports" / "odds.csv"
        selected = root / "reports" / "selection.csv"
        summary = root / "reports" / "selection.json"
        write_odds(odds)

        report = selector.select_valid_odds(str(odds), date_min="2026-06-04", prefer_side="away", max_events=5)
        assert report["rows_read"] == 4
        assert report["valid_candidates"] == 2
        assert report["selected_rows"] == 1
        assert report["selection"][0]["side"] == "away"
        assert report["rejection_reasons"]["draw exclu"] == 1
        assert report["rejection_reasons"]["near-close exclu comme taken odds"] == 1

        report_with_draw = selector.select_valid_odds(str(odds), date_min="2026-06-04", include_draw=True, max_events=5)
        assert report_with_draw["selected_rows"] == 2

        selector.write_selection(report["selection"], str(selected))
        selector.write_summary(report, str(summary))
        assert selected.exists()
        payload = json.loads(summary.read_text(encoding="utf-8"))
        assert payload["selected_rows"] == 1
        with selected.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert set(rows[0]).issuperset(set(ODDS_COLUMNS))

        assert selector.main(["--odds", str(odds), "--output", str(selected), "--summary-json", str(summary), "--date-min", "2026-06-04", "--prefer-side", "home"]) == 0

    print("test_api_football_valid_odds_selector ok")


if __name__ == "__main__":
    main()
