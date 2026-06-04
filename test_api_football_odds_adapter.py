from pathlib import Path
import json
import tempfile

import api_football_odds_adapter


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def missing_team_odds_payload():
    return {
        "response": [
            {
                "fixture": {"id": 9901, "date": "2026-06-04T18:00:00+00:00"},
                "league": {"name": "Serie A"},
                "bookmakers": [
                    {
                        "name": "Book Test",
                        "bets": [
                            {
                                "name": "Match Winner",
                                "values": [
                                    {"value": "Home", "odd": "2.10"},
                                    {"value": "Draw", "odd": "3.40"},
                                    {"value": "Away", "odd": "3.20"},
                                ],
                            },
                            {
                                "name": "Goals Over/Under",
                                "values": [{"value": "Over 2.5", "odd": "1.90"}],
                            },
                        ],
                    }
                ],
            }
        ]
    }


def fixtures_payload():
    return {
        "response": [
            {
                "fixture": {"id": 9901, "date": "2026-06-04T18:00:00+00:00", "status": {"short": "NS"}},
                "league": {"name": "Serie A", "country": "Italy"},
                "teams": {"home": {"name": "Parma Calcio 1913"}, "away": {"name": "Napoli"}},
            }
        ]
    }


def main():
    fixture = Path("tests/fixtures/api_football_odds_sample.json")
    payload = api_football_odds_adapter.read_fixture(str(fixture))
    rows = api_football_odds_adapter.normalize_api_football_payload(payload)
    assert len(rows) == 5
    assert rows[0]["source"] == "api_football"
    assert any(row["side"] == "home" for row in rows)
    assert any(row["market_type"] == "total" for row in rows)
    assert all(row["validation_status"] == "valid" for row in rows)
    assert api_football_odds_adapter.main(["--dry-run", "--league", "EPL", "--date", "2026-06-01"]) == 0
    assert api_football_odds_adapter.main(["--check-config"]) == 0
    empty = {"response": [], "_http_status": 200}
    assert api_football_odds_adapter.response_warnings(empty)
    assert api_football_odds_adapter.main(["--from-fixture", str(fixture)]) == 0

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        odds_json = root / "odds_missing_teams.json"
        fixtures_json = root / "fixtures.json"
        output = root / "reports" / "api_odds.csv"
        invalid = root / "reports" / "api_invalid.csv"
        summary = root / "reports" / "api_summary.json"
        html = root / "reports" / "api_summary.html"
        write_json(odds_json, missing_team_odds_payload())
        write_json(fixtures_json, fixtures_payload())

        raw_without_enrichment = api_football_odds_adapter.normalize_api_football_payload(api_football_odds_adapter.read_fixture(str(odds_json)))
        assert all(row["validation_status"] == "invalid" for row in raw_without_enrichment)
        fixtures_index = api_football_odds_adapter.load_fixture_index(fixtures_json=str(fixtures_json))
        enriched = api_football_odds_adapter.normalize_api_football_payload(api_football_odds_adapter.read_fixture(str(odds_json)), fixture_index=fixtures_index)
        assert any(row["validation_status"] == "valid" for row in enriched)
        assert any(row["home_team"] == "Parma Calcio 1913" for row in enriched)

        rows, invalid_rows, report = api_football_odds_adapter.process_payload(
            api_football_odds_adapter.read_fixture(str(odds_json)),
            fixtures_index=fixtures_index,
            market="h2h",
            valid_only=True,
            one_side_per_event=True,
            prefer_side="away",
            max_events=1,
        )
        assert report["raw_odds_lines"] == 4
        assert report["rows_enriched_with_teams"] == 4
        assert report["valid_rows"] == 1
        assert rows[0]["side"] == "away"
        assert invalid_rows == []

        assert api_football_odds_adapter.main([
            "--from-fixture",
            str(odds_json),
            "--fixtures-json",
            str(fixtures_json),
            "--market",
            "h2h",
            "--valid-only",
            "--one-side-per-event",
            "--prefer-side",
            "home",
            "--max-events",
            "1",
            "--output",
            str(output),
            "--output-invalid",
            str(invalid),
            "--summary-json",
            str(summary),
            "--html",
            str(html),
        ]) == 0
        payload_summary = json.loads(summary.read_text(encoding="utf-8"))
        assert payload_summary["fixtures_loaded"] == 1
        assert payload_summary["valid_rows"] == 1
        assert output.exists() and invalid.exists() and html.exists()

    print("test_api_football_odds_adapter ok")


if __name__ == "__main__":
    main()
