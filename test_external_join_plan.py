import csv
import os
import tempfile
from pathlib import Path

from external_join_plan import build_join_plan, detect_join_columns


def write_csv(path: Path, rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        xgabora = Path(tmp) / "features.csv"
        external = Path(tmp) / "external.csv"
        db_path = Path(tmp) / "oracle_db.json"
        db_path.write_text("{}", encoding="utf-8")
        before = db_path.read_text(encoding="utf-8")
        os.environ["DB_FILE"] = str(db_path)

        write_csv(xgabora, [
            {"date": "2024-08-16", "home": "Arsenal FC", "away": "Chelsea", "competition": "EPL", "odds": "1.8"},
            {"date": "2024-08-17", "home": "Liverpool", "away": "Everton", "competition": "EPL", "odds": "1.5"},
            {"date": "2024-08-17", "home": "Liverpool", "away": "Everton", "competition": "EPL", "odds": "2.0"},
        ])
        write_csv(external, [
            {"Date": "2024-08-16", "HomeTeam": "Arsenal", "AwayTeam": "Chelsea", "League": "Premier League", "Home_xG": "1.8"},
            {"Date": "2024-08-18", "HomeTeam": "Manchester City", "AwayTeam": "Spurs", "League": "Premier League", "Home_xG": "2.4"},
        ])

        columns = detect_join_columns(str(external))
        assert columns["date"] == "Date"
        assert columns["home"] == "HomeTeam"
        assert columns["away"] == "AwayTeam"

        plan = build_join_plan(str(xgabora), str(external))
        assert plan["xgabora_rows"] == 3
        assert plan["external_rows"] == 2
        assert plan["xgabora_unique_matches"] == 2
        assert plan["external_unique_matches"] == 2
        assert plan["matched"] == 1
        assert plan["match_rate"] == 50.0
        assert plan["matched_examples"]
        assert plan["external_unmatched_examples"]
        assert plan["recommendations"]
        assert db_path.read_text(encoding="utf-8") == before

    print("test_external_join_plan ok")


if __name__ == "__main__":
    main()
