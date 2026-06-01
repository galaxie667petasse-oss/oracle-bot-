import csv
import tempfile
from pathlib import Path

import matchday_pack


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "matches.csv"
        with source.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["match_date", "league", "home_team", "away_team", "kickoff_time"])
            writer.writeheader()
            writer.writerow({"match_date": "2026-06-01", "league": "EPL", "home_team": "Arsenal", "away_team": "Chelsea", "kickoff_time": "2026-06-01T19:00:00"})
        pack = root / "reports" / "matchday_2026_06_01"
        created = matchday_pack.create_pack("2026-06-01", str(pack), str(source), with_example_row=True, market="h2h", bookmaker="manual", league="International")
        assert "matchday_manual_odds.csv" in created["files"]
        assert "matchday_examples.csv" in created["files"]
        assert (pack / "matchday_checklist.md").exists()
        examples = list(csv.DictReader((pack / "matchday_examples.csv").open(newline="", encoding="utf-8")))
        assert len(examples) == 2
        assert examples[0]["is_near_close"] == "false"
        assert examples[1]["is_near_close"] == "true"
        status = matchday_pack.pack_status(str(pack))
        assert status["taken"]["rows"] == 1
        assert status["near_close"]["rows"] == 1
        assert (pack / "matchday_status.json").exists()
        empty_pack = root / "reports" / "matchday_empty"
        matchday_pack.create_pack("2026-06-02", str(empty_pack))
        empty = matchday_pack.pack_status(str(empty_pack))
        assert empty["warnings"]
    print("test_matchday_pack ok")


if __name__ == "__main__":
    main()
