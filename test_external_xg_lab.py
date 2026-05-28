import csv
import tempfile
from pathlib import Path

import external_xg_lab


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
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        oracle_db = root / "oracle_db.json"
        matches_csv = root / "data" / "MATCHES.csv"
        oracle_db.write_text("{}", encoding="utf-8")
        matches_csv.parent.mkdir(parents=True, exist_ok=True)
        matches_csv.write_text("date,home,away\n", encoding="utf-8")
        before_db = oracle_db.read_text(encoding="utf-8")
        before_matches = matches_csv.read_text(encoding="utf-8")

        xgabora = root / "features_modern.csv"
        external = root / "external" / "matches.csv"
        write_csv(
            xgabora,
            ["date", "home", "away", "market_type", "odds", "result", "no_vig_probability"],
            [
                {"date": "2024-01-01", "home": "Arsenal", "away": "Chelsea", "market_type": "h2h", "odds": "1.80", "result": "win", "no_vig_probability": "0.56"},
                {"date": "2024-01-02", "home": "Manchester United", "away": "Tottenham", "market_type": "h2h", "odds": "2.10", "result": "loss", "no_vig_probability": "0.47"},
                {"date": "2024-01-03", "home": "West Ham United", "away": "Aston Villa", "market_type": "total", "odds": "1.95", "result": "win", "no_vig_probability": "0.51"},
            ],
        )
        write_csv(
            external,
            ["Date", "HomeTeam", "AwayTeam", "Home_xG", "Away_xG", "HomeShots", "AwayShots", "Competition"],
            [
                {"Date": "2024-01-01", "HomeTeam": "Arsenal", "AwayTeam": "Chelsea", "Home_xG": "1.7", "Away_xG": "0.8", "HomeShots": "12", "AwayShots": "7", "Competition": "EPL"},
                {"Date": "2024-01-02", "HomeTeam": "Man United", "AwayTeam": "Spurs", "Home_xG": "1.1", "Away_xG": "1.3", "HomeShots": "9", "AwayShots": "11", "Competition": "EPL"},
                {"Date": "2024-01-03", "HomeTeam": "West Ham Utd", "AwayTeam": "Aston Villa", "Home_xG": "1.4", "Away_xG": "1.2", "HomeShots": "10", "AwayShots": "8", "Competition": "EPL"},
                {"Date": "2024-01-04", "HomeTeam": "Everton", "AwayTeam": "Liverpool", "Home_xG": "0.6", "Away_xG": "2.2", "HomeShots": "5", "AwayShots": "15", "Competition": "EPL"},
            ],
        )

        detected = external_xg_lab.detect_columns(["Date", "HomeTeam", "AwayTeam", "Home_xG", "Away_xG", "HomeShots", "AwayShots"])
        assert detected["date"] == ["Date"]
        assert detected["home_team"] == ["HomeTeam"]
        assert detected["away_team"] == ["AwayTeam"]
        assert detected["home_xg"] == ["Home_xG"]
        assert detected["away_xg"] == ["Away_xG"]

        profile = external_xg_lab.profile_path(str(external))
        assert profile["files_read"] == 1
        assert profile["profiles"][0]["xg_richness"] == "eleve"
        assert profile["profiles"][0]["leak_risk"] == "eleve"
        assert profile["profiles"][0]["date_min"] == "2024-01-01"

        plan = external_xg_lab.build_join_plan(str(xgabora), str(external))
        assert plan["exact_matches"]
        assert len(plan["fuzzy_matches"]) == 1
        assert len(plan["unmatched_external"]) == 1
        assert plan["match_rate"] == 75.0

        evaluation = external_xg_lab.evaluate_join(str(xgabora), str(external))
        assert evaluation["matches_with_xg"] == 3
        assert evaluation["matches_with_xg_and_xgabora_odds"] == 3
        assert evaluation["covers_2024_plus"] is True
        assert evaluation["join_quality"] == "exploitable_prudent"
        assert evaluation["modeling_allowed_by_join_quality"] is True
        assert evaluation["verdict"] in {"dataset utile seulement laboratoire", "integration fragile"}
        alias_report = root / "reports" / "alias_report.json"
        written_alias = external_xg_lab.write_alias_report(str(xgabora), str(external), str(alias_report), league="EPL")
        assert written_alias.exists()

        preview = root / "reports" / "external_xg_preview.csv"
        result = external_xg_lab.build_preview(str(xgabora), str(external), str(preview))
        assert result["rows_written"] == 3
        assert preview.exists()
        preview_rows = read_rows(preview)
        arsenal = next(row for row in preview_rows if row["home"] == "Arsenal")
        assert arsenal["home_xg"] == "1.7"
        assert arsenal["away_xg"] == "0.8"
        assert arsenal["xg_diff"] == "0.9"
        assert arsenal["shots_diff"] == "5.0"
        assert arsenal["source_external_file"] == "matches.csv"
        assert arsenal["leak_risk"] == "eleve"

        assert oracle_db.read_text(encoding="utf-8") == before_db
        assert matches_csv.read_text(encoding="utf-8") == before_matches

    source = Path("external_xg_lab.py").read_text(encoding="utf-8").lower()
    forbidden = ["requests", "urlopen", "kaggle.api", "download(", "scrape"]
    assert not any(token in source for token in forbidden)

    print("test_external_xg_lab ok")


if __name__ == "__main__":
    main()
