import tempfile
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
    near_rows = the_odds_api_adapter.normalize_the_odds_api_payload(payload, near_close=True)
    assert all(row["is_near_close"].lower() == "true" for row in near_rows)
    filtered = the_odds_api_adapter.filter_normalized_rows(
        rows,
        bookmaker="Book Test",
        match_date="2026-06-01",
        max_events=1,
        one_side_per_event=True,
        prefer_side="home",
    )
    assert len(filtered) == 1
    assert filtered[0]["side"] == "home"
    assert the_odds_api_adapter.main(["--dry-run", "--sport", "soccer_epl"]) == 0
    assert the_odds_api_adapter.main(["--check-config"]) == 0
    with tempfile.TemporaryDirectory() as tmp:
        with_output = Path(tmp) / "reports" / "fixture.csv"
        assert the_odds_api_adapter.main([
            "--from-fixture", str(fixture),
            "--output", str(with_output),
            "--near-close",
            "--one-side-per-event",
            "--prefer-side", "home",
            "--max-events", "1",
        ]) == 0
        assert with_output.exists()

    print("test_the_odds_api_adapter ok")


if __name__ == "__main__":
    main()
