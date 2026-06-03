import tempfile
from pathlib import Path

import api_football_fixtures_adapter as fixtures


def main():
    fixture = "tests/fixtures/api_football_fixtures_sample.json"
    payload = fixtures.read_fixture(fixture)
    rows = fixtures.normalize_fixtures_payload(payload)
    assert len(rows) == 2
    assert rows[0]["fixture_id"] == "101"
    assert rows[0]["validation_status"] == "valid"
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "reports" / "fixtures.csv"
        raw = Path(tmp) / "reports" / "fixtures.json"
        fixtures.write_csv(rows, str(output))
        fixtures.write_raw(payload, str(raw))
        assert output.exists() and raw.exists()
        assert fixtures.main(["--dry-run", "--date", "2026-06-03"]) == 0
        assert fixtures.main(["--from-fixture", fixture, "--output", str(output)]) == 0
    print("test_api_football_fixtures_adapter ok")


if __name__ == "__main__":
    main()
