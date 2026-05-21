import csv
import json
import os
import tempfile
from pathlib import Path

from external_dataset_probe import detect_columns, profile_csv, profile_folder, utility_score


def write_csv(path: Path):
    rows = [
        {
            "Date": "2024-08-16",
            "HomeTeam": "Arsenal",
            "AwayTeam": "Chelsea",
            "FTHG": "2",
            "FTAG": "1",
            "Home_xG": "1.8",
            "Away_xG": "0.9",
            "HomeShots": "14",
            "AwayShots": "8",
            "HomeSOT": "6",
            "AwaySOT": "3",
            "B365H": "1.80",
            "B365D": "3.60",
            "B365A": "4.50",
            "League": "Premier League",
        },
        {
            "Date": "2025-01-03",
            "HomeTeam": "Liverpool",
            "AwayTeam": "Everton",
            "FTHG": "1",
            "FTAG": "1",
            "Home_xG": "2.1",
            "Away_xG": "0.7",
            "HomeShots": "18",
            "AwayShots": "5",
            "HomeSOT": "7",
            "AwaySOT": "2",
            "B365H": "1.50",
            "B365D": "4.20",
            "B365A": "6.00",
            "League": "Premier League",
        },
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    columns = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "Home_xG", "HomeShots", "B365H"]
    detected = detect_columns(columns)
    assert detected["date"] == ["Date"]
    assert "HomeTeam" in detected["home_team"]
    assert "AwayTeam" in detected["away_team"]
    assert "FTHG" in detected["score"]
    assert "Home_xG" in detected["xg"]
    assert "HomeShots" in detected["shots"]
    assert "B365H" in detected["odds"]

    with tempfile.TemporaryDirectory() as tmp:
        csv_path = Path(tmp) / "external.csv"
        json_path = Path(tmp) / "players.json"
        db_path = Path(tmp) / "oracle_db.json"
        write_csv(csv_path)
        json_path.write_text(json.dumps([{"Date": "2024-01-01", "Player": "A", "Team": "Arsenal", "xG": 0.3}]), encoding="utf-8")
        db_path.write_text("{}", encoding="utf-8")
        before = db_path.read_text(encoding="utf-8")
        os.environ["DB_FILE"] = str(db_path)

        profile = profile_csv(str(csv_path))
        assert profile["rows"] == 2
        assert profile["columns_count"] >= 10
        assert profile["date_min"] == "2024-08-16"
        assert profile["date_max"] == "2025-01-03"
        assert profile["year_distribution"]["2024"] == 1
        assert profile["utility"]["xg"] >= 3
        assert profile["utility"]["odds"] >= 3
        assert profile["utility"]["join_possible_with_xgabora"] >= 4
        assert profile["utility"]["leak_risk"] == "eleve"
        assert profile["utility"]["verdict"] in {"utiliser comme enrichissement", "utiliser comme base principale"}
        assert profile["timing"]["post_match"]
        assert profile["examples"]

        folder = profile_folder(tmp)
        assert len(folder["files"]) >= 2
        assert folder["utility"]["xg"] >= 3
        assert db_path.read_text(encoding="utf-8") == before

        synthetic = {"detected_columns": detected, "columns": columns, "date_max": "2025-01-01"}
        score = utility_score(synthetic)
        assert score["recency"] == 5

    print("test_external_dataset_probe ok")


if __name__ == "__main__":
    main()
