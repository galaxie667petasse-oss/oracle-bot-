import csv
import tempfile
from pathlib import Path

from external_xg_features import (
    build_external_xg_features,
    compute_rolling_features,
    read_external_matches,
    validate_no_xg_leakage,
)


def write_csv(path: Path, fieldnames, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_rows(path: Path):
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main():
    external_rows = [
        {"date": "2024-08-01", "home_team": "Alpha", "away_team": "Beta", "home_xg": "1.0", "away_xg": "0.5", "score": "1-0"},
        {"date": "2024-08-02", "home_team": "Gamma", "away_team": "Alpha", "home_xg": "0.4", "away_xg": "2.0", "score": "0-2"},
        {"date": "2024-08-03", "home_team": "Alpha", "away_team": "Delta", "home_xg": "3.0", "away_xg": "1.0", "score": "3-1"},
        {"date": "2024-08-04", "home_team": "Epsilon", "away_team": "Alpha", "home_xg": "0.6", "away_xg": "1.4", "score": "0-1"},
        {"date": "2024-08-05", "home_team": "Alpha", "away_team": "Zeta", "home_xg": "2.2", "away_xg": "0.7", "score": "2-0"},
        {"date": "2024-08-06", "home_team": "Alpha", "away_team": "Beta", "home_xg": "9.9", "away_xg": "0.2", "score": "9-0"},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        external = root / "external.csv"
        xgabora = root / "features.csv"
        output = root / "reports" / "xg_features.csv"
        alias_report = root / "reports" / "alias_report.json"
        oracle_db = root / "oracle_db.json"
        matches_csv = root / "data" / "MATCHES.csv"
        oracle_db.write_text("{}", encoding="utf-8")
        matches_csv.parent.mkdir(parents=True, exist_ok=True)
        matches_csv.write_text("date,home,away\n", encoding="utf-8")
        before_db = oracle_db.read_text(encoding="utf-8")
        before_matches = matches_csv.read_text(encoding="utf-8")

        write_csv(external, ["date", "home_team", "away_team", "home_xg", "away_xg", "score"], external_rows)
        matches, _meta = read_external_matches(str(external))
        rolling = compute_rolling_features(matches)
        first = next(row for row in rolling if row["date"] == "2024-08-01")
        sixth = next(row for row in rolling if row["date"] == "2024-08-06")
        assert first["home_xg_for_avg3"] is None
        assert sixth["home_xg_for_avg3"] == 2.2
        assert sixth["home_xg_for_avg5"] == 1.92
        assert sixth["home_xg_matches_available"] == 5
        assert sixth["home_xg_for_avg3"] != 9.9
        assert all(source_date < sixth["date"] for source_date in sixth["_source_dates"])

        write_csv(
            xgabora,
            ["date", "home", "away", "market_type", "pari", "result", "odds", "no_vig_probability"],
            [
                {"date": "2024-08-06", "home": "Alpha", "away": "Beta", "market_type": "h2h", "pari": "Victoire Alpha", "result": "win", "odds": "1.8", "no_vig_probability": "0.55"},
                {"date": "2024-08-06", "home": "Alpha", "away": "Beta", "market_type": "total", "pari": "Plus de 2.5 buts", "result": "win", "odds": "1.9", "no_vig_probability": "0.52"},
                {"date": "2024-08-07", "home": "Alpha", "away": "Beta", "market_type": "h2h", "pari": "Victoire Alpha", "result": "loss", "odds": "1.8", "no_vig_probability": "0.55"},
            ],
        )
        summary = build_external_xg_features(str(external), str(xgabora), str(output), alias_report=str(alias_report))
        assert summary["external_matches_read"] == 6
        assert summary["matched_external_matches"] == 1
        assert summary["join_rate_before_alias"] == summary["join_rate_after_alias"]
        assert summary["alias_matches_gained"] == 0
        assert alias_report.exists()
        assert summary["enriched_rows"] == 2
        rows = read_rows(output)
        assert len(rows) == 2
        assert rows[0]["home_xg_for_avg3"] == "2.2"
        assert rows[1]["home_xg_for_avg3"] == "2.2"
        assert "home_xg" not in rows[0]
        assert rows[0]["xg_leak_risk"] == "controlled_rolling"

        bundes_external = root / "bundes_external.csv"
        bundes_xgabora = root / "bundes_features.csv"
        bundes_output = root / "reports" / "bundes_xg_features.csv"
        write_csv(
            bundes_external,
            ["date", "league", "home_team", "away_team", "home_xg", "away_xg"],
            [
                {"date": "2024-01-01", "league": "GER-Bundesliga", "home_team": "Bayer Leverkusen", "away_team": "Eintracht Frankfurt", "home_xg": "1.0", "away_xg": "0.5"},
                {"date": "2024-01-02", "league": "GER-Bundesliga", "home_team": "Bayern Munich", "away_team": "Bayer Leverkusen", "home_xg": "2.0", "away_xg": "1.0"},
                {"date": "2024-01-03", "league": "GER-Bundesliga", "home_team": "Bayer Leverkusen", "away_team": "Borussia Dortmund", "home_xg": "1.5", "away_xg": "1.2"},
                {"date": "2024-01-04", "league": "GER-Bundesliga", "home_team": "FC Heidenheim", "away_team": "Bayer Leverkusen", "home_xg": "0.8", "away_xg": "1.7"},
                {"date": "2024-01-05", "league": "GER-Bundesliga", "home_team": "Bayer Leverkusen", "away_team": "Mainz 05", "home_xg": "2.2", "away_xg": "0.7"},
                {"date": "2024-01-06", "league": "GER-Bundesliga", "home_team": "Bayer Leverkusen", "away_team": "Eintracht Frankfurt", "home_xg": "2.4", "away_xg": "0.9"},
            ],
        )
        write_csv(
            bundes_xgabora,
            ["date", "home", "away", "competition", "market_type", "pari", "result", "odds", "no_vig_probability"],
            [
                {"date": "2024-01-01", "home": "Leverkusen", "away": "Ein Frankfurt", "competition": "D1", "market_type": "h2h", "pari": "Victoire Leverkusen", "result": "win", "odds": "1.8", "no_vig_probability": "0.55"},
                {"date": "2024-01-02", "home": "Bayern Munich", "away": "Leverkusen", "competition": "D1", "market_type": "h2h", "pari": "Victoire Bayern", "result": "win", "odds": "1.8", "no_vig_probability": "0.55"},
                {"date": "2024-01-03", "home": "Leverkusen", "away": "Dortmund", "competition": "D1", "market_type": "h2h", "pari": "Victoire Leverkusen", "result": "win", "odds": "1.8", "no_vig_probability": "0.55"},
                {"date": "2024-01-04", "home": "Heidenheim", "away": "Leverkusen", "competition": "D1", "market_type": "h2h", "pari": "Victoire Heidenheim", "result": "loss", "odds": "2.8", "no_vig_probability": "0.35"},
                {"date": "2024-01-05", "home": "Leverkusen", "away": "Mainz", "competition": "D1", "market_type": "h2h", "pari": "Victoire Leverkusen", "result": "win", "odds": "1.8", "no_vig_probability": "0.55"},
                {"date": "2024-01-06", "home": "Leverkusen", "away": "Ein Frankfurt", "competition": "D1", "market_type": "h2h", "pari": "Victoire Leverkusen", "result": "win", "odds": "1.8", "no_vig_probability": "0.55"},
            ],
        )
        bundes_summary = build_external_xg_features(str(bundes_external), str(bundes_xgabora), str(bundes_output))
        assert bundes_summary["join_rate_after_alias"] == 100.0
        bundes_rows = read_rows(bundes_output)
        assert len(bundes_rows) == 6
        final_bundes = next(row for row in bundes_rows if row["date"] == "2024-01-06")
        assert final_bundes["home_xg_for_avg3"] != ""

        seriea_external = root / "seriea_external.csv"
        seriea_xgabora = root / "seriea_features.csv"
        seriea_output = root / "reports" / "seriea_xg_features.csv"
        write_csv(
            seriea_external,
            ["date", "league", "home_team", "away_team", "home_xg", "away_xg"],
            [{"date": "2024-04-01", "league": "Serie A", "home_team": "Internazionale", "away_team": "AC Milan", "home_xg": "1.0", "away_xg": "0.5"}],
        )
        write_csv(
            seriea_xgabora,
            ["date", "home", "away", "competition", "market_type", "pari", "result", "odds", "no_vig_probability"],
            [{"date": "2024-04-01", "home": "Inter", "away": "Milan", "competition": "I1", "market_type": "h2h", "pari": "Victoire Inter", "result": "win", "odds": "1.9", "no_vig_probability": "0.52"}],
        )
        seriea_summary = build_external_xg_features(str(seriea_external), str(seriea_xgabora), str(seriea_output))
        assert seriea_summary["join_rate_after_alias"] == 100.0

        ligue1_external = root / "ligue1_external.csv"
        ligue1_xgabora = root / "ligue1_features.csv"
        ligue1_output = root / "reports" / "ligue1_xg_features.csv"
        write_csv(
            ligue1_external,
            ["date", "league", "home_team", "away_team", "home_xg", "away_xg"],
            [{"date": "2024-05-01", "league": "Ligue 1", "home_team": "Paris Saint-Germain", "away_team": "Olympique Marseille", "home_xg": "2.1", "away_xg": "0.5"}],
        )
        write_csv(
            ligue1_xgabora,
            ["date", "home", "away", "competition", "market_type", "pari", "result", "odds", "no_vig_probability"],
            [{"date": "2024-05-01", "home": "Paris SG", "away": "Marseille", "competition": "F1", "market_type": "h2h", "pari": "Victoire Paris SG", "result": "win", "odds": "1.7", "no_vig_probability": "0.6"}],
        )
        ligue1_summary = build_external_xg_features(str(ligue1_external), str(ligue1_xgabora), str(ligue1_output))
        assert ligue1_summary["join_rate_after_alias"] == 100.0

        try:
            validate_no_xg_leakage([{"date": "2024-08-06", "home_xg_for_avg3": "1.0", "_source_dates": ["2024-08-06"]}])
            raise AssertionError("fuite non detectee")
        except ValueError as exc:
            assert "Fuite" in str(exc)

        try:
            validate_no_xg_leakage([{"date": "2024-08-06", "home_xg": "1.0"}])
            raise AssertionError("xG direct non detecte")
        except ValueError as exc:
            assert "directe" in str(exc)

        assert oracle_db.read_text(encoding="utf-8") == before_db
        assert matches_csv.read_text(encoding="utf-8") == before_matches

    print("test_external_xg_features ok")


if __name__ == "__main__":
    main()
