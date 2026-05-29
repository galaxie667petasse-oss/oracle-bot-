import csv
import tempfile
from pathlib import Path

import clv_readiness_report
import features_closing_enricher


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
        features = root / "features.csv"
        source = root / "matches.csv"
        output = root / "reports" / "features_with_closing_preview.csv"
        oracle_db = root / "oracle_db.json"
        oracle_db.write_text("{}", encoding="utf-8")
        before_db = oracle_db.read_text(encoding="utf-8")

        write_csv(
            features,
            ["date", "home", "away", "market_type", "pari", "odds", "is_home_pick", "is_away_pick", "is_draw", "is_over", "is_under"],
            [
                {"date": "2024-01-01", "home": "Alpha", "away": "Beta", "market_type": "h2h", "pari": "Victoire Alpha", "odds": "2.10", "is_home_pick": "1", "is_away_pick": "0", "is_draw": "0", "is_over": "0", "is_under": "0"},
                {"date": "2024-01-01", "home": "Alpha", "away": "Beta", "market_type": "draw", "pari": "Nul", "odds": "3.40", "is_home_pick": "0", "is_away_pick": "0", "is_draw": "1", "is_over": "0", "is_under": "0"},
            ],
        )
        write_csv(
            source,
            ["Date", "HomeTeam", "AwayTeam", "C_LTH", "C_LTD", "C_LTA"],
            [{"Date": "2024-01-01", "HomeTeam": "Alpha", "AwayTeam": "Beta", "C_LTH": "2.00", "C_LTD": "3.30", "C_LTA": "4.00"}],
        )
        before_features = features.read_text(encoding="utf-8")
        summary = features_closing_enricher.enrich_features_with_closing(str(features), str(source), str(output))
        assert summary["rows_with_closing"] == 2
        assert summary["closing_coverage"] == 100.0
        rows = read_rows(output)
        assert rows[0]["closing_odds"] == "2.0"
        assert rows[0]["closing_source"] == "C_LTH"
        assert rows[0]["clv_percent"] == "0.05"
        assert rows[1]["closing_source"] == "C_LTD"
        readiness = clv_readiness_report.analyze_readiness(str(output))
        assert readiness["clv_calculable"] is True

        source_without = root / "matches_no_closing.csv"
        output_without = root / "reports" / "features_without_closing_preview.csv"
        write_csv(source_without, ["Date", "HomeTeam", "AwayTeam", "B365H"], [{"Date": "2024-01-01", "HomeTeam": "Alpha", "AwayTeam": "Beta", "B365H": "2.0"}])
        no_closing = features_closing_enricher.enrich_features_with_closing(str(features), str(source_without), str(output_without))
        assert no_closing["rows_with_closing"] == 0
        assert no_closing["source_has_closing"] is False
        try:
            features_closing_enricher.enrich_features_with_closing(str(features), str(source), str(root / "data" / "features_with_closing.csv"))
            raise AssertionError("ecriture data non bloquee")
        except ValueError as exc:
            assert "data" in str(exc)

        assert features.read_text(encoding="utf-8") == before_features
        assert oracle_db.read_text(encoding="utf-8") == before_db

    print("test_features_closing_enricher ok")


if __name__ == "__main__":
    main()
