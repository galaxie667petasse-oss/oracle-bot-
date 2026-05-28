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

        report = join_diagnostics.build_join_diagnostics(str(xgabora), str(external), league="La-Liga")
        assert report["external_matches"] == 4
        assert report["join_rate_before_alias"] < report["join_rate_after_alias"]
        assert report["join_rate_after_alias"] == 75.0
        assert report["join_quality"] == "exploitable_prudent"
        assert report["alias_matches_gained"] >= 2
        assert report["unmatched_count"] == 1
        assert any(item["raw"] == "Athletic Club" for item in report["alias_used"])
        assert report["top_alias_suggestions"]
        assert any("date" in item["cause"] for item in report["probable_causes"])

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
