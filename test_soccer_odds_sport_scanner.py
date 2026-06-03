import json
import tempfile
from pathlib import Path

import soccer_odds_sport_scanner as scanner


def sample_payload():
    return [
        {
            "id": "evt_jp_1",
            "sport_key": "soccer_japan_j_league",
            "sport_title": "J League",
            "commence_time": "2026-06-01T10:00:00Z",
            "home_team": "Urawa Reds",
            "away_team": "Kobe",
            "bookmakers": [
                {
                    "key": "book",
                    "title": "Book",
                    "markets": [
                        {"key": "h2h", "outcomes": [
                            {"name": "Urawa Reds", "price": 2.1},
                            {"name": "Draw", "price": 3.2},
                            {"name": "Kobe", "price": 3.0},
                        ]}
                    ],
                }
            ],
        }
    ]


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fixtures = root / "fixtures"
        fixtures.mkdir()
        (fixtures / "soccer_japan_j_league.json").write_text(json.dumps(sample_payload()), encoding="utf-8")

        dry = scanner.scan_sports(["soccer_japan_j_league"], dry_run=True, allow_network=False)
        assert dry["active_sports"] == 0
        assert dry["sports"][0]["request_status"] == "dry_run"

        report = scanner.scan_sports(["soccer_japan_j_league"], from_fixtures=str(fixtures), dry_run=True)
        assert report["active_sports"] == 1
        assert report["sports"][0]["distinct_events"] == 1
        assert report["sports"][0]["usable_for_shadow"] is True

        output = root / "reports" / "scan.json"
        html = root / "reports" / "scan.html"
        scanner.write_json(report, str(output))
        scanner.write_html(report, str(html))
        assert output.exists()
        assert html.exists()
        assert scanner.main(["--dry-run", "--sports", "soccer_japan_j_league"]) == 0

    print("test_soccer_odds_sport_scanner ok")


if __name__ == "__main__":
    main()
