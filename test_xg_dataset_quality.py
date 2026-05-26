import csv
import tempfile
from pathlib import Path

import xg_dataset_quality


EXPECTED = "2020-2021,2021-2022,2022-2023,2023-2024,2024-2025"


def write_csv(path: Path, fieldnames, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def season_rows(seasons, per_season=380, xg=True, with_date=True):
    rows = []
    for season in seasons:
        start = int(season[:4])
        for index in range(per_season):
            month = (index % 12) + 1
            day = (index % 28) + 1
            rows.append({
                "date": f"{start}-{month:02d}-{day:02d}" if with_date else "",
                "league": "EPL",
                "season": season,
                "home_team": f"Home {season} {index}",
                "away_team": f"Away {season} {index}",
                "home_goals": str(index % 4),
                "away_goals": str((index + 1) % 4),
                "home_xg": "1.2" if xg else "",
                "away_xg": "0.8" if xg else "",
                "source": "understat_soccerdata",
            })
    return rows


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        oracle_db = root / "oracle_db.json"
        oracle_db.write_text("{}", encoding="utf-8")
        before = oracle_db.read_text(encoding="utf-8")
        data_dir = root / "data"
        data_dir.mkdir()

        fieldnames = ["date", "league", "season", "home_team", "away_team", "home_goals", "away_goals", "home_xg", "away_xg", "source"]
        complete = root / "external.csv"
        write_csv(complete, fieldnames, season_rows(EXPECTED.split(",")))
        report = xg_dataset_quality.build_quality_report(str(complete), league="EPL", expected_seasons=EXPECTED)
        assert report["rows"] == 1900
        assert report["verdict"] == "exploitable_rolling_xg"
        assert report["total_expected_matches"] == 1900
        assert report["duplicate_count"] == 0
        assert report["xg_coverage"] == 100.0
        assert report["lab_only"] is True
        assert report["can_influence_picks"] is False

        missing = root / "missing.csv"
        write_csv(missing, fieldnames, season_rows(EXPECTED.split(",")[:-1]))
        missing_report = xg_dataset_quality.build_quality_report(str(missing), league="EPL", expected_seasons=EXPECTED)
        assert missing_report["verdict"] == "fragile"
        assert missing_report["missing_seasons"] == ["2024-2025"]
        assert any("manquantes" in warning for warning in missing_report["warnings"])

        no_xg = root / "no_xg.csv"
        write_csv(no_xg, fieldnames, season_rows(["2020-2021"], xg=False))
        no_xg_report = xg_dataset_quality.build_quality_report(str(no_xg), league="EPL", expected_seasons="2020-2021")
        assert no_xg_report["verdict"] == "a_eviter"
        assert no_xg_report["home_xg_missing"] == 380

        duplicate_rows = season_rows(["2020-2021"], per_season=10)
        duplicate_rows.append(dict(duplicate_rows[0]))
        duplicate_path = root / "duplicate.csv"
        write_csv(duplicate_path, fieldnames, duplicate_rows)
        duplicate_report = xg_dataset_quality.build_quality_report(str(duplicate_path), league="EPL", expected_seasons="2020-2021")
        assert duplicate_report["duplicate_count"] == 1
        assert any("Volume inattendu" in warning for warning in duplicate_report["warnings"])

        no_date = root / "no_date.csv"
        write_csv(no_date, fieldnames, season_rows(["2020-2021"], with_date=False))
        no_date_report = xg_dataset_quality.build_quality_report(str(no_date), league="EPL", expected_seasons="2020-2021")
        assert no_date_report["verdict"] == "a_eviter"

        json_path = root / "reports" / "quality.json"
        html_path = root / "reports" / "quality.html"
        xg_dataset_quality.write_json(report, str(json_path))
        xg_dataset_quality.write_html(report, str(html_path))
        assert json_path.exists()
        assert html_path.exists()
        assert list(data_dir.iterdir()) == []
        assert oracle_db.read_text(encoding="utf-8") == before

    print("test_xg_dataset_quality ok")


if __name__ == "__main__":
    main()
