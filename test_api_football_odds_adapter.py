from pathlib import Path

import api_football_odds_adapter


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

    print("test_api_football_odds_adapter ok")


if __name__ == "__main__":
    main()
