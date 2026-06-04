import csv
import tempfile
from pathlib import Path

import shadow_ledger
import shadow_result_matcher
from api_football_results_adapter import RESULT_COLUMNS


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow_ledger.csv"
        entry = shadow_ledger.add_shadow_entry(str(ledger), match_date="2026-06-01", league="EPL", home="Arsenal", away="Chelsea", market="h2h", side="home", taken_odds="2.10")
        results = root / "reports" / "results.csv"
        results.parent.mkdir(parents=True, exist_ok=True)
        with results.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=RESULT_COLUMNS)
            writer.writeheader()
            writer.writerow({"fixture_id": "1", "date": "2026-06-01", "league": "EPL", "home_team": "Arsenal", "away_team": "Chelsea", "home_goals": "2", "away_goals": "1", "is_finished": "True"})
        dry = shadow_result_matcher.match_results(str(ledger), str(results), dry_run=True)
        assert dry["matched"] == 1 and dry["updated"] == 0
        applied = shadow_result_matcher.match_results(str(ledger), str(results), dry_run=False)
        assert applied["updated"] == 1
        rows = shadow_ledger.read_ledger(str(ledger))
        assert rows[0]["shadow_id"] == entry["shadow_id"]
        assert rows[0]["result"] == "win"
        assert rows[0]["status"] == "settled"
    print("test_shadow_result_matcher ok")


if __name__ == "__main__":
    main()
