import csv
import tempfile
from pathlib import Path

import join_diagnostics


def write_csv(path: Path, fieldnames, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    assert join_diagnostics.classify_join_quality(91)["join_quality"] == "excellent"
    assert join_diagnostics.classify_join_quality(80)["join_quality"] == "exploitable_prudent"
    assert join_diagnostics.classify_join_quality(60)["join_quality"] == "fragile"
    blocked = join_diagnostics.classify_join_quality(39.89)
    assert blocked["join_quality"] == "insuffisant"
    assert blocked["modeling_allowed_by_join_quality"] is False

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        oracle_db = root / "oracle_db.json"
        data_dir = root / "data"
        oracle_db.write_text("{}", encoding="utf-8")
        data_dir.mkdir()
        before_db = oracle_db.read_text(encoding="utf-8")

        xgabora = root / "features.csv"
        external = root / "external.csv"
        write_csv(
            xgabora,
            ["date", "home", "away", "market_type", "odds"],
            [
                {"date": "2024-01-01", "home": "Athletic Bilbao", "away": "Real Betis", "market_type": "h2h", "odds": "1.9"},
                {"date": "2024-01-02", "home": "Atlético Madrid", "away": "Cádiz", "market_type": "h2h", "odds": "1.6"},
                {"date": "2024-01-03", "home": "Girona FC", "away": "CA Osasuna", "market_type": "h2h", "odds": "2.1"},
                {"date": "2024-01-05", "home": "Sevilla FC", "away": "Valencia", "market_type": "h2h", "odds": "2.0"},
            ],
        )
        write_csv(
            external,
            ["date", "league", "season", "home_team", "away_team", "home_xg", "away_xg"],
            [
                {"date": "2024-01-01", "league": "La-Liga", "season": "2023-2024", "home_team": "Athletic Club", "away_team": "Betis", "home_xg": "1.2", "away_xg": "0.8"},
                {"date": "2024-01-02", "league": "La-Liga", "season": "2023-2024", "home_team": "Atletico Madrid", "away_team": "Cadiz", "home_xg": "2.0", "away_xg": "0.5"},
                {"date": "2024-01-03", "league": "La-Liga", "season": "2023-2024", "home_team": "Girona", "away_team": "Osasuna", "home_xg": "1.4", "away_xg": "1.1"},
                {"date": "2024-01-04", "league": "La-Liga", "season": "2023-2024", "home_team": "Sevilla", "away_team": "Valencia", "home_xg": "1.0", "away_xg": "1.0"},
            ],
        )

        report = join_diagnostics.build_join_diagnostics(str(xgabora), str(external), league="La-Liga", show_unmatched=1)
        assert report["external_matches"] == 4
        assert report["join_rate_before_alias"] < report["join_rate_after_alias"]
        assert report["join_rate_after_alias"] == 75.0
        assert report["join_quality"] == "exploitable_prudent"
        assert report["alias_matches_gained"] >= 2
        assert report["unmatched_count"] == 1
        assert report["show_unmatched"] == 1
        assert len(report["unmatched_external_examples"]) == 1
        assert any(item["raw"] == "Athletic Club" for item in report["alias_used"])
        assert report["top_alias_suggestions"]
        assert any("date" in item["cause"] for item in report["probable_causes"])

        bundes_xgabora = root / "bundes_features.csv"
        bundes_external = root / "bundes_external.csv"
        write_csv(
            bundes_xgabora,
            ["date", "home", "away", "competition", "market_type", "odds"],
            [
                {"date": "2024-02-01", "home": "Leverkusen", "away": "Ein Frankfurt", "competition": "D1", "market_type": "h2h", "odds": "1.8"},
                {"date": "2024-02-02", "home": "MGladbach", "away": "Dortmund", "competition": "D1", "market_type": "h2h", "odds": "2.0"},
                {"date": "2024-02-03", "home": "FC Koln", "away": "Mainz", "competition": "D1", "market_type": "h2h", "odds": "2.4"},
                {"date": "2024-02-04", "home": "Union Berlin", "away": "Heidenheim", "competition": "D1", "market_type": "h2h", "odds": "2.2"},
                {"date": "2024-02-05", "home": "Arsenal", "away": "Chelsea", "competition": "E0", "market_type": "h2h", "odds": "2.1"},
            ],
        )
        write_csv(
            bundes_external,
            ["date", "league", "season", "home_team", "away_team", "home_xg", "away_xg"],
            [
                {"date": "2024-02-01", "league": "GER-Bundesliga", "season": "2023-2024", "home_team": "Bayer Leverkusen", "away_team": "Eintracht Frankfurt", "home_xg": "1.3", "away_xg": "0.7"},
                {"date": "2024-02-02", "league": "GER-Bundesliga", "season": "2023-2024", "home_team": "Borussia Monchengladbach", "away_team": "Borussia Dortmund", "home_xg": "1.1", "away_xg": "1.4"},
                {"date": "2024-02-03", "league": "GER-Bundesliga", "season": "2023-2024", "home_team": "FC Koln", "away_team": "Mainz 05", "home_xg": "0.9", "away_xg": "1.2"},
                {"date": "2024-02-04", "league": "GER-Bundesliga", "season": "2023-2024", "home_team": "1. FC Union Berlin", "away_team": "FC Heidenheim", "home_xg": "1.0", "away_xg": "0.8"},
            ],
        )
        bundes_report = join_diagnostics.build_join_diagnostics(str(bundes_xgabora), str(bundes_external), league="Bundesliga")
        assert bundes_report["xgabora_competitions_considered"] == {"D1": 4}
        assert bundes_report["xgabora_rows_filtered_out"] == 1
        assert bundes_report["join_rate_before_alias"] == 0.0
        assert bundes_report["join_rate_after_alias"] == 100.0
        assert bundes_report["join_quality"] == "excellent"
        assert bundes_report["alias_matches_gained"] == 4
        assert not bundes_report["warnings"]

        seriea_xgabora = root / "seriea_features.csv"
        seriea_external = root / "seriea_external.csv"
        write_csv(
            seriea_xgabora,
            ["date", "home", "away", "competition", "market_type", "odds"],
            [
                {"date": "2024-04-01", "home": "Inter", "away": "Milan", "competition": "I1", "market_type": "h2h", "odds": "1.9"},
                {"date": "2024-04-02", "home": "Roma", "away": "Verona", "competition": "I1", "market_type": "h2h", "odds": "2.0"},
                {"date": "2024-04-03", "home": "Parma", "away": "Napoli", "competition": "I1", "market_type": "h2h", "odds": "2.4"},
            ],
        )
        write_csv(
            seriea_external,
            ["date", "league", "season", "home_team", "away_team", "home_xg", "away_xg"],
            [
                {"date": "2024-04-01", "league": "Serie A", "season": "2023-2024", "home_team": "Internazionale", "away_team": "AC Milan", "home_xg": "1.4", "away_xg": "0.9"},
                {"date": "2024-04-02", "league": "Serie A", "season": "2023-2024", "home_team": "AS Roma", "away_team": "Hellas Verona", "home_xg": "1.2", "away_xg": "0.8"},
                {"date": "2024-04-03", "league": "Serie A", "season": "2023-2024", "home_team": "Parma Calcio 1913", "away_team": "SSC Napoli", "home_xg": "1.0", "away_xg": "1.7"},
                {"date": "2024-04-04", "league": "Serie A", "season": "2023-2024", "home_team": "Parma Calcio 1913", "away_team": "SSC Napoli", "home_xg": "0.8", "away_xg": "1.4"},
            ],
        )
        seriea_report = join_diagnostics.build_join_diagnostics(str(seriea_xgabora), str(seriea_external), league="Serie A", show_unmatched=1)
        assert seriea_report["join_rate_before_alias"] == 0.0
        assert seriea_report["join_rate_after_alias"] == 75.0
        assert seriea_report["join_rate_gain"] == 75.0
        assert seriea_report["join_quality"] == "exploitable_prudent"
        assert any(item["external_name"] == "Parma Calcio 1913" for item in seriea_report["top_alias_impacts"])
        assert any(item["team"] == "Parma Calcio 1913" for item in seriea_report["unmatched_by_team"])
        assert len(seriea_report["unmatched_external_examples"]) == 1
        unmatched_csv = root / "reports" / "seriea_unmatched.csv"
        join_diagnostics.write_unmatched_csv(seriea_report, str(unmatched_csv))
        assert unmatched_csv.exists()
        assert "Parma Calcio 1913" in unmatched_csv.read_text(encoding="utf-8")

        ligue1_xgabora = root / "ligue1_features.csv"
        ligue1_external = root / "ligue1_external.csv"
        write_csv(
            ligue1_xgabora,
            ["date", "home", "away", "competition", "market_type", "odds"],
            [
                {"date": "2024-05-01", "home": "Paris SG", "away": "Marseille", "competition": "F1", "market_type": "h2h", "odds": "1.7"},
                {"date": "2024-05-02", "home": "St Etienne", "away": "Nimes", "competition": "F1", "market_type": "h2h", "odds": "2.4"},
            ],
        )
        write_csv(
            ligue1_external,
            ["date", "league", "season", "home_team", "away_team", "home_xg", "away_xg"],
            [
                {"date": "2024-05-01", "league": "Ligue 1", "season": "2023-2024", "home_team": "Paris Saint-Germain", "away_team": "Olympique Marseille", "home_xg": "2.0", "away_xg": "0.6"},
                {"date": "2024-05-02", "league": "Ligue 1", "season": "2023-2024", "home_team": "Saint-Étienne", "away_team": "Nîmes", "home_xg": "1.1", "away_xg": "1.1"},
            ],
        )
        ligue1_report = join_diagnostics.build_join_diagnostics(str(ligue1_xgabora), str(ligue1_external), league="Ligue 1")
        assert ligue1_report["join_rate_before_alias"] == 0.0
        assert ligue1_report["join_rate_after_alias"] == 100.0
        assert ligue1_report["join_quality"] == "excellent"

        json_path = root / "reports" / "join.json"
        html_path = root / "reports" / "join.html"
        join_diagnostics.write_json(report, str(json_path))
        join_diagnostics.write_html(report, str(html_path))
        assert json_path.exists()
        assert html_path.exists()
        assert list(data_dir.iterdir()) == []
        assert oracle_db.read_text(encoding="utf-8") == before_db

    print("test_join_diagnostics ok")


if __name__ == "__main__":
    main()
