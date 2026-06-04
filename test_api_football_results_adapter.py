import csv
import json
import tempfile
from pathlib import Path

import api_football_results_adapter as adapter


def sample_payload():
    return {
        "response": [
            {
                "fixture": {"id": 1, "date": "2026-06-01T18:00:00+00:00", "status": {"short": "FT"}},
                "league": {"id": 39, "name": "Premier League", "country": "England"},
                "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}},
                "goals": {"home": 2, "away": 1},
            }
        ]
    }


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        payload = sample_payload()
        fixture = root / "fixture.json"
        fixture.write_text(json.dumps(payload), encoding="utf-8")
        rows = adapter.normalize_results_payload(payload)
        assert rows[0]["is_finished"] == "True"
        assert rows[0]["home_goals"] == "2"
        output = root / "reports" / "api_results.csv"
        adapter.write_csv(rows, str(output))
        assert list(csv.DictReader(output.open(newline="", encoding="utf-8")))[0]["fixture_id"] == "1"
        assert adapter.main(["--dry-run", "--date", "2026-06-01"]) == 0
        assert adapter.main(["--from-fixture", str(fixture), "--output", str(root / "reports" / "out.csv")]) == 0
    print("test_api_football_results_adapter ok")


if __name__ == "__main__":
    main()
