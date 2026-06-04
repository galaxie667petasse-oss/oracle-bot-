import tempfile
from pathlib import Path
import json

import api_football_fixtures_adapter as fixtures
import api_football_matchday_probe as probe
import api_football_odds_adapter as odds


def main():
    fixtures_payload = fixtures.read_fixture("tests/fixtures/api_football_fixtures_sample.json")
    odds_payload = odds.read_fixture("tests/fixtures/api_football_odds_sample.json")
    report = probe.build_probe_report(fixtures_payload, odds_payload, date="2026-06-03")
    assert report["total_fixtures"] == 2
    assert report["odds_rows"] > 0
    assert report["odds_valid_before_enrichment"] == 5
    assert report["odds_valid_after_enrichment"] == 5
    assert report["events_with_valid_h2h"] == 1
    assert report["recommended_action"] == "use_api_football_same_day_runner"
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "reports" / "probe.json"
        html = Path(tmp) / "reports" / "probe.html"
        probe.write_json(report, str(output))
        probe.write_html(report, str(html))
        assert output.exists() and html.exists()
        assert probe.main(["--dry-run", "--date", "2026-06-03"]) == 0
        assert probe.main(["--date", "2026-06-03", "--from-fixtures", "tests/fixtures/api_football_fixtures_sample.json", "--from-odds", "tests/fixtures/api_football_odds_sample.json", "--output", str(output)]) == 0

        fixtures_path = Path(tmp) / "fixtures_missing_team_case.json"
        odds_path = Path(tmp) / "odds_missing_team_case.json"
        fixtures_path.write_text(json.dumps({
            "response": [{
                "fixture": {"id": 888, "date": "2026-06-04T18:00:00+00:00", "status": {"short": "NS"}},
                "league": {"name": "Ligue 1", "country": "France"},
                "teams": {"home": {"name": "Paris Saint Germain"}, "away": {"name": "Marseille"}},
            }]
        }, ensure_ascii=False), encoding="utf-8")
        odds_path.write_text(json.dumps({
            "response": [{
                "fixture": {"id": 888, "date": "2026-06-04T18:00:00+00:00"},
                "league": {"name": "Ligue 1"},
                "bookmakers": [{"name": "Book Test", "bets": [{"name": "Match Winner", "values": [{"value": "Home", "odd": "1.80"}]}]}],
            }]
        }, ensure_ascii=False), encoding="utf-8")
        enriched_report = probe.build_probe_report(fixtures.read_fixture(str(fixtures_path)), odds.read_fixture(str(odds_path)), date="2026-06-04")
        assert enriched_report["odds_valid_before_enrichment"] == 0
        assert enriched_report["odds_valid_after_enrichment"] == 1
        assert enriched_report["events_missing_teams"] == 0
        assert enriched_report["bookmaker_coverage"]["Book Test"] == 1
    print("test_api_football_matchday_probe ok")


if __name__ == "__main__":
    main()
