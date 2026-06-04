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
        (fixtures / "soccer_brazil_serie_b.json").write_text(json.dumps(sample_payload()), encoding="utf-8")
        active = root / "active.json"
        active.write_text(json.dumps({
            "sports": [
                {"key": "soccer_japan_j_league", "group": "Soccer", "active": True, "has_outrights": False},
                {"key": "soccer_brazil_serie_b", "group": "Soccer", "active": True, "has_outrights": False},
                {"key": "soccer_fifa_world_cup_winner", "group": "Soccer", "active": True, "has_outrights": True},
            ]
        }), encoding="utf-8")

        dry = scanner.scan_sports(["soccer_japan_j_league"], dry_run=True, allow_network=False)
        assert dry["active_sports"] == 0
        assert dry["sports"][0]["request_status"] == "dry_run"

        report = scanner.scan_sports(["soccer_japan_j_league"], from_fixtures=str(fixtures), dry_run=True)
        assert report["active_sports"] == 1
        assert report["sports"][0]["distinct_events"] == 1
        assert report["sports"][0]["usable_for_shadow"] is True
        expanded = scanner.scan_sports(active_sports_json=str(active), from_fixtures=str(fixtures), dry_run=True)
        keys = [item["sport_key"] for item in expanded["sports"]]
        assert "soccer_brazil_serie_b" in keys
        assert "soccer_fifa_world_cup_winner" not in keys
        assert expanded["sports"][0]["priority"] in {"high", "medium", "low"}

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
