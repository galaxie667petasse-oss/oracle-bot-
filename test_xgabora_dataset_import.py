import csv
import os
import sys
import tempfile
import types
from datetime import timezone
from pathlib import Path

from xgabora_dataset_import import load_candidates, import_candidates, result_for_market


HEADER = [
    "Division",
    "MatchDate",
    "MatchTime",
    "HomeTeam",
    "AwayTeam",
    "FTHG",
    "FTAG",
    "FTR",
    "OddHome",
    "OddDraw",
    "OddAway",
    "MaxHome",
    "MaxDraw",
    "MaxAway",
    "Over25",
    "Under25",
    "MaxOver25",
    "MaxUnder25",
    "HomeElo",
    "AwayElo",
    "Form3Home",
    "Form3Away",
    "Form5Home",
    "Form5Away",
]


def write_sample_csv(path: Path):
    rows = [
        {
            "Division": "E0",
            "MatchDate": "2024-01-10",
            "MatchTime": "15:00",
            "HomeTeam": "Alpha FC",
            "AwayTeam": "Beta FC",
            "FTHG": "2",
            "FTAG": "1",
            "FTR": "H",
            "OddHome": "2.00",
            "OddDraw": "3.10",
            "OddAway": "3.80",
            "MaxHome": "2.12",
            "MaxDraw": "3.25",
            "MaxAway": "4.00",
            "MaxOver25": "1.90",
            "MaxUnder25": "2.05",
            "HomeElo": "1700",
            "AwayElo": "1600",
            "Form3Home": "7",
            "Form3Away": "4",
            "Form5Home": "11",
            "Form5Away": "6",
        },
        {
            "Division": "SP1",
            "MatchDate": "2024-01-11",
            "MatchTime": "20:00",
            "HomeTeam": "Gamma",
            "AwayTeam": "Delta",
            "FTHG": "1",
            "FTAG": "1",
            "FTR": "D",
            "OddHome": "2.30",
            "OddDraw": "3.00",
            "OddAway": "3.20",
            "Over25": "1.95",
            "Under25": "1.85",
            "HomeElo": "1500",
            "AwayElo": "1520",
        },
        {
            "Division": "I1",
            "MatchDate": "2024-01-12",
            "MatchTime": "18:00",
            "HomeTeam": "No Odds",
            "AwayTeam": "Ignored",
            "FTHG": "0",
            "FTAG": "1",
            "FTR": "A",
        },
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADER)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = Path(tmp) / "MATCHES.csv"
        db_path = Path(tmp) / "oracle_test_db.json"
        write_sample_csv(csv_path)

        candidates, stats = load_candidates(str(csv_path))
        assert stats.matches_lus == 3
        assert stats.matches_ignores == 1
        assert len(candidates) == 10
        assert stats.h2h_crees == 4
        assert stats.draw_crees == 2
        assert stats.over_under_crees == 4

        home_pick = next(c for c in candidates if c["home"] == "Alpha FC" and c["pari"] == "Victoire Alpha FC")
        away_pick = next(c for c in candidates if c["home"] == "Alpha FC" and c["pari"] == "Victoire Beta FC")
        draw_pick = next(c for c in candidates if c["home"] == "Gamma" and c["market_type"] == "draw")
        over_pick = next(c for c in candidates if c["home"] == "Alpha FC" and c["pari"] == "Plus de 2.5 buts")
        under_pick = next(c for c in candidates if c["home"] == "Alpha FC" and c["pari"] == "Moins de 2.5 buts")

        assert home_pick["result"] == "win"
        assert away_pick["result"] == "loss"
        assert draw_pick["result"] == "win"
        assert over_pick["result"] == "win"
        assert under_pick["result"] == "loss"
        assert home_pick["odds"] == 2.12
        assert home_pick["home_elo"] == 1700.0
        assert home_pick["away_elo"] == 1600.0
        assert home_pick["elo_diff"] == 100.0

        assert result_for_market(2, 1, "h2h_home") == "win"
        assert result_for_market(1, 1, "draw") == "win"
        assert result_for_market(2, 1, "over25") == "win"
        assert result_for_market(2, 1, "under25") == "loss"

        os.environ["DB_FILE"] = str(db_path)
        os.environ["DATABASE_URL"] = ""
        sys.modules.setdefault("pytz", types.SimpleNamespace(timezone=lambda _name: timezone.utc))
        import_stats = import_candidates(candidates)
        assert import_stats.total_appris >= 10
        first_total = import_stats.total_appris
        second_import = import_candidates(candidates)
        assert second_import.deja_presents_ignores == len(candidates)
        assert second_import.nouveaux_importes == 0
        assert second_import.total_appris == first_total
        assert import_stats.poids_agents
        assert db_path.exists()

    print("test_xgabora_dataset_import ok")


if __name__ == "__main__":
    main()
