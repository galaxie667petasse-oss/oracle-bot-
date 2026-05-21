import csv
import json
import os
import tempfile
from pathlib import Path

from feature_builder import build_feature_rows, main as feature_main


def sample_record(idx, market_type, pari, odds, result, **extra):
    row = {
        "match_id": "feature-match-1",
        "date_key": "2024-02-01",
        "home": "Alpha",
        "away": "Beta",
        "competition": "E0",
        "market_type": market_type,
        "pari": pari,
        "odds": odds,
        "result": result,
        "score": "2-1",
        "shadow": True,
        "home_elo": 1700,
        "away_elo": 1600,
        "form3_home": 7,
        "form3_away": 4,
        "form5_home": 10,
        "form5_away": 8,
        "home_shots": 14,
        "away_shots": 9,
        "home_target": 6,
        "away_target": 3,
        "total_shots": 23,
        "total_target": 9,
        "home_corners": 7,
        "away_corners": 4,
        "total_corners": 11,
        "home_yellow": 2,
        "away_yellow": 3,
        "home_red": 0,
        "away_red": 1,
        "both_teams_scored": 1,
        "over_2_5_result": 1,
    }
    row.update(extra)
    row["id"] = idx
    return row


def main():
    records = [
        sample_record("home", "h2h", "Victoire Alpha", 2.0, "win", import_family="home"),
        sample_record("draw", "draw", "Match nul", 3.5, "loss", import_family="draw"),
        sample_record("away", "h2h", "Victoire Beta", 4.0, "loss", import_family="away"),
        sample_record("over", "total", "Plus de 2.5 buts", 1.9, "win"),
        sample_record("under", "total", "Moins de 2.5 buts", 2.0, "loss"),
        sample_record("pending", "total", "Plus de 2.5 buts", 1.8, "pending"),
    ]
    db = {"scans": {"2024-02-01": {"picks": [], "candidates": records}}}
    rows = build_feature_rows(db)
    assert len(rows) == 5
    home = next(row for row in rows if row["pari"] == "Victoire Alpha")
    over = next(row for row in rows if row["pari"] == "Plus de 2.5 buts")
    assert home["target_win"] == 1
    assert over["target_win"] == 1
    assert home["no_vig_probability"] not in (None, "")
    assert over["no_vig_probability"] not in (None, "")
    assert home["elo_diff"] == 100
    assert home["elo_abs_diff"] == 100
    assert home["form3_diff"] == 3
    assert home["is_home_pick"] == 1
    assert over["is_over"] == 1
    assert home["attacking_pressure_home"] == 26
    assert home["attacking_pressure_away"] == 15
    assert home["attacking_pressure_diff"] == 11
    assert home["shot_accuracy_home"] == round(6 / 14, 6)
    assert home["tempo_proxy"] == 34
    assert home["discipline_risk"] == 7

    rolling_records = [
        sample_record("r1", "h2h", "Victoire Alpha", 1.8, "win", date_key="2024-01-01", home="Alpha", away="Old 1", score="2-1", home_shots=10, away_shots=8, home_target=5, away_target=2, home_corners=4, away_corners=3),
        sample_record("r2", "h2h", "Victoire Old 2", 2.1, "loss", date_key="2024-01-10", home="Old 2", away="Alpha", score="0-3", home_shots=7, away_shots=12, home_target=1, away_target=6, home_corners=2, away_corners=7),
        sample_record("current", "h2h", "Victoire Alpha", 2.0, "win", date_key="2024-02-01", home="Alpha", away="Beta", score="4-4", home_shots=99, away_shots=99, home_target=50, away_target=50, home_corners=20, away_corners=20),
        sample_record("future", "h2h", "Victoire Alpha", 1.5, "win", date_key="2024-03-01", home="Alpha", away="Future", score="9-0", home_shots=30, away_shots=1, home_target=15, away_target=0, home_corners=10, away_corners=1),
    ]
    rolling_rows = build_feature_rows({"scans": {"rolling": {"picks": [], "candidates": rolling_records}}})
    current = next(row for row in rolling_rows if row["date"] == "2024-02-01")
    assert current["home_team_goals_for_avg5"] == 2.5
    assert current["home_team_goals_against_avg5"] == 0.5
    assert current["home_team_shots_avg5"] == 11.0
    assert current["home_team_target_avg5"] == 5.5
    assert current["home_team_corners_avg5"] == 5.5
    assert current["home_team_btts_rate5"] == 0.5
    assert current["home_team_over25_rate5"] == 1.0
    assert current["away_team_goals_for_avg5"] is None

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "oracle_db.json"
        output = Path(tmp) / "features.csv"
        db_path.write_text(json.dumps(db, ensure_ascii=False), encoding="utf-8")
        before = db_path.read_text(encoding="utf-8")
        os.environ["DB_FILE"] = str(db_path)
        os.environ["DATABASE_URL"] = ""
        feature_main(["--output", str(output)])
        after = db_path.read_text(encoding="utf-8")
        assert before == after
        assert output.exists()
        with output.open(newline="", encoding="utf-8") as fh:
            exported = list(csv.DictReader(fh))
        assert len(exported) == 5
        assert exported[0]["target_win"] in ("0", "1")

    print("test_feature_builder ok")


if __name__ == "__main__":
    main()
