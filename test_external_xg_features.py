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
