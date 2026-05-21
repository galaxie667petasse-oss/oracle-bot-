import csv
import os
import sys
import tempfile
import types
from datetime import timezone
from pathlib import Path

from pricing import expected_value, fair_odds, implied_probability, market_margin, remove_vig_1x2, remove_vig_two_way
from xgabora_dataset_import import inspect_dates, load_candidates, import_candidates, result_for_market


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
    "OddOver25",
    "OddUnder25",
    "B365>2.5",
    "B365<2.5",
    "B365BTTSYes",
    "B365BTTSNo",
    "HomeElo",
    "AwayElo",
    "Form3Home",
    "Form3Away",
    "Form5Home",
    "Form5Away",
    "HTHome",
    "HTAway",
    "HomeShots",
    "AwayShots",
    "HomeTarget",
    "AwayTarget",
    "HomeCorners",
    "AwayCorners",
    "HomeYellow",
    "AwayYellow",
    "HomeRed",
    "AwayRed",
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
            "MaxUnder25": "2.00",
            "B365BTTSYes": "1.78",
            "B365BTTSNo": "2.05",
            "HomeElo": "1700",
            "AwayElo": "1600",
            "Form3Home": "7",
            "Form3Away": "4",
            "Form5Home": "11",
            "Form5Away": "6",
            "HTHome": "1",
            "HTAway": "0",
            "HomeShots": "14",
            "AwayShots": "9",
            "HomeTarget": "6",
            "AwayTarget": "3",
            "HomeCorners": "7",
            "AwayCorners": "4",
            "HomeYellow": "2",
            "AwayYellow": "3",
            "HomeRed": "0",
            "AwayRed": "1",
        },
        {
            "Division": "SP1",
            "MatchDate": "2024-01-11",
            "MatchTime": "20:00",
            "HomeTeam": "Gamma",
            "AwayTeam": "Delta",
            "FTHG": "1",
            "FTAG": "0",
            "FTR": "H",
            "OddHome": "2.30",
            "OddDraw": "3.00",
            "OddAway": "3.20",
            "B365>2.5": "1.95",
            "B365<2.5": "1.85",
            "HomeElo": "1500",
            "AwayElo": "1520",
            "HTHome": "0",
            "HTAway": "0",
            "HomeShots": "8",
            "AwayShots": "11",
            "HomeTarget": "4",
            "AwayTarget": "2",
            "HomeCorners": "3",
            "AwayCorners": "6",
            "HomeYellow": "1",
            "AwayYellow": "1",
            "HomeRed": "0",
            "AwayRed": "0",
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
        assert len(candidates) == 12
        assert stats.h2h_crees == 4
        assert stats.draw_crees == 2
        assert stats.over_crees == 2
        assert stats.under_crees == 2
        assert stats.over_under_crees == 4
        assert stats.btts_crees == 2
        assert stats.date_min_importee == "2024-01-10"
        assert stats.date_max_importee == "2024-01-11"
        assert stats.distribution_annuelle["2024"] == 2

        home_pick = next(c for c in candidates if c["home"] == "Alpha FC" and c["pari"] == "Victoire Alpha FC")
        away_pick = next(c for c in candidates if c["home"] == "Alpha FC" and c["pari"] == "Victoire Beta FC")
        draw_pick = next(c for c in candidates if c["home"] == "Gamma" and c["market_type"] == "draw")
        over_pick = next(c for c in candidates if c["home"] == "Alpha FC" and c["pari"] == "Plus de 2.5 buts")
        under_pick = next(c for c in candidates if c["home"] == "Alpha FC" and c["pari"] == "Moins de 2.5 buts")
        alt_over_pick = next(c for c in candidates if c["home"] == "Gamma" and c["pari"] == "Plus de 2.5 buts")
        alt_under_pick = next(c for c in candidates if c["home"] == "Gamma" and c["pari"] == "Moins de 2.5 buts")
        btts_yes = next(c for c in candidates if c["home"] == "Alpha FC" and c["market_type"] == "btts" and "Oui" in c["pari"])

        assert home_pick["result"] == "win"
        assert away_pick["result"] == "loss"
        assert draw_pick["result"] == "loss"
        assert over_pick["result"] == "win"
        assert under_pick["result"] == "loss"
        assert over_pick["market_type"] == "total"
        assert under_pick["market_type"] == "total"
        assert over_pick["odds"] == 1.90
        assert under_pick["odds"] == 2.00
        assert alt_over_pick["odds"] == 1.95
        assert alt_over_pick["result"] == "loss"
        assert alt_under_pick["result"] == "win"
        assert btts_yes["result"] == "win"
        assert not any(c["home"] == "Gamma" and c["market_type"] == "btts" for c in candidates)
        assert home_pick["odds"] == 2.12
        assert home_pick["home_elo"] == 1700.0
        assert home_pick["away_elo"] == 1600.0
        assert home_pick["elo_diff"] == 100.0
        assert home_pick["period_bucket"] == "test_2024_plus"
        assert home_pick["data_weight"] == 1.0
        assert home_pick["home_shots"] == 14.0
        assert home_pick["away_shots"] == 9.0
        assert home_pick["shots_diff"] == 5.0
        assert home_pick["home_target"] == 6.0
        assert home_pick["away_target"] == 3.0
        assert home_pick["target_diff"] == 3.0
        assert home_pick["total_shots"] == 23.0
        assert home_pick["total_target"] == 9.0
        assert home_pick["corners_diff"] == 3.0
        assert home_pick["total_corners"] == 11.0
        assert home_pick["cards_diff"] == -1.0
        assert home_pick["red_card_any"] == 1
        assert home_pick["ht_total_goals"] == 1.0
        assert home_pick["ft_total_goals"] == 3.0
        assert home_pick["second_half_goals"] == 2.0
        assert home_pick["home_clean_sheet"] == 0
        assert home_pick["away_clean_sheet"] == 0
        assert home_pick["both_teams_scored"] == 1
        assert home_pick["over_2_5_result"] == 1
        assert home_pick["under_2_5_result"] == 0
        assert home_pick["implied_probability"] == round(implied_probability(2.12), 6)
        h2h_no_vig = remove_vig_1x2(2.12, 3.25, 4.00)
        h2h_margin = market_margin([implied_probability(2.12), implied_probability(3.25), implied_probability(4.00)])
        assert h2h_no_vig is not None
        assert home_pick["no_vig_probability"] == round(h2h_no_vig["home"], 6)
        assert home_pick["market_margin"] == round(h2h_margin, 6)
        assert home_pick["fair_odds_market"] == round(fair_odds(h2h_no_vig["home"]), 4)
        assert home_pick["ev_market_baseline"] == round(expected_value(h2h_no_vig["home"], 2.12), 6)
        assert away_pick["no_vig_probability"] == round(h2h_no_vig["away"], 6)

        total_no_vig = remove_vig_two_way(1.90, 2.00)
        total_margin = market_margin([implied_probability(1.90), implied_probability(2.00)])
        assert total_no_vig is not None
        assert over_pick["no_vig_probability"] == round(total_no_vig["over"], 6)
        assert under_pick["no_vig_probability"] == round(total_no_vig["under"], 6)
        assert over_pick["market_margin"] == round(total_margin, 6)
        assert under_pick["fair_odds_market"] == round(fair_odds(total_no_vig["under"]), 4)
        assert btts_yes["implied_probability"] == round(implied_probability(1.78), 6)
        assert "no_vig_probability" not in btts_yes

        only_2024, only_2024_stats = load_candidates(str(csv_path), date_from="2024-01-01")
        assert len(only_2024) == len(candidates)
        gamma_only, gamma_stats = load_candidates(str(csv_path), limit=1, date_from="2024-01-11", date_to="2024-01-11")
        assert gamma_stats.matches_lus == 1
        assert len(gamma_only) == 5
        assert all(c["home"] == "Gamma" for c in gamma_only)

        inspection = inspect_dates(str(csv_path))
        assert inspection["total_lignes"] == 3
        assert inspection["matchs_score_final"] == 3
        assert inspection["date_min"] == "2024-01-10"
        assert inspection["date_max"] == "2024-01-12"
        assert inspection["matchs_over_under"] == 2

        assert result_for_market(2, 1, "h2h_home") == "win"
        assert result_for_market(1, 1, "draw") == "win"
        assert result_for_market(2, 1, "over25") == "win"
        assert result_for_market(2, 1, "under25") == "loss"
        assert result_for_market(2, 1, "btts_yes") == "win"
        assert result_for_market(2, 1, "btts_no") == "loss"

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
