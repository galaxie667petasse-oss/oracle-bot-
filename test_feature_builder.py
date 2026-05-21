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
        "shadow": True,
        "home_elo": 1700,
        "away_elo": 1600,
        "form3_home": 7,
        "form3_away": 4,
        "form5_home": 10,
        "form5_away": 8,
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
