import tempfile
from pathlib import Path

import api_football_fixtures_adapter as fixtures
import api_football_matchday_probe as probe
import api_football_odds_adapter as odds


def main():
    fixtures_payload = fixtures.read_fixture("tests/fixtures/api_football_fixtures_sample.json")
    odds_payload = odds.read_fixture("tests/fixtures/api_football_odds_sample.json")
    report = probe.build_probe_report(fixtures_payload, odds_payload, date="2026-06-03")
    assert report["total_fixtures"] == 2
    assert report["odds_rows"] > 0
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "reports" / "probe.json"
        html = Path(tmp) / "reports" / "probe.html"
        probe.write_json(report, str(output))
        probe.write_html(report, str(html))
        assert output.exists() and html.exists()
        assert probe.main(["--dry-run", "--date", "2026-06-03"]) == 0
        assert probe.main(["--date", "2026-06-03", "--from-fixtures", "tests/fixtures/api_football_fixtures_sample.json", "--from-odds", "tests/fixtures/api_football_odds_sample.json", "--output", str(output)]) == 0
    print("test_api_football_matchday_probe ok")


if __name__ == "__main__":
    main()
