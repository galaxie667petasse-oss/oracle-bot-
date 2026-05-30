from pathlib import Path

import the_odds_api_adapter


def main():
    fixture = Path("tests/fixtures/the_odds_api_sample.json")
    payload = the_odds_api_adapter.read_fixture(str(fixture))
    rows = the_odds_api_adapter.normalize_the_odds_api_payload(payload)
    assert len(rows) == 5
    assert rows[0]["source"] == "the_odds_api"
    assert any(row["side"] == "draw" for row in rows)
    assert any(row["market_type"] == "total" for row in rows)
    assert all(row["validation_status"] == "valid" for row in rows)
    assert the_odds_api_adapter.main(["--dry-run", "--sport", "soccer_epl"]) == 0
    assert the_odds_api_adapter.main(["--check-config"]) == 0

    print("test_the_odds_api_adapter ok")


if __name__ == "__main__":
    main()
