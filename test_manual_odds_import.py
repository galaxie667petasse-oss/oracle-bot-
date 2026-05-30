import csv
import tempfile
from pathlib import Path

import manual_odds_import
import odds_snapshot_store


def main():
    with tempfile.TemporaryDirectory() as tmp:
        template = Path(tmp) / "reports" / "manual_odds_snapshot_template.csv"
        manual_odds_import.write_template(str(template))
        assert template.exists()
        source = Path(tmp) / "reports" / "manual.csv"
        with source.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=manual_odds_import.MANUAL_COLUMNS)
            writer.writeheader()
            writer.writerow({
                "captured_at": "2026-06-01T10:00:00",
                "source": "manual_csv",
                "league": "EPL",
                "match_date": "2026-06-01",
                "kickoff_time": "19:00",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "bookmaker": "Book",
                "market_type": "h2h",
                "side": "home",
                "odds": "2.10",
                "is_live": "false",
                "is_near_close": "false",
                "notes": "test",
            })
            writer.writerow({
                "captured_at": "2026-06-01T10:00:00",
                "source": "manual_csv",
                "league": "EPL",
                "match_date": "2026-06-01",
                "kickoff_time": "19:00",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "bookmaker": "Book",
                "market_type": "h2h",
                "side": "away",
                "odds": "0,5",
                "is_live": "non",
                "is_near_close": "oui",
                "notes": "invalid odds",
            })
        rows = manual_odds_import.normalize_manual_csv(str(source))
        assert rows[0]["validation_status"] == "valid"
        assert rows[1]["validation_status"] == "invalid"
        summary = manual_odds_import.build_summary(str(source), rows)
        assert summary["valid_rows"] == 1
        assert summary["rejected_rows"] == 1
        assert summary["near_close_count"] == 1
        out = Path(tmp) / "reports" / "normalized.csv"
        manual_odds_import.write_normalized_csv(rows, str(out))
        assert out.exists()
        valid_out = Path(tmp) / "reports" / "valid.csv"
        rejects_out = Path(tmp) / "reports" / "rejects.csv"
        summary_out = Path(tmp) / "reports" / "summary.json"
        manual_odds_import.write_valid(rows, str(valid_out))
        manual_odds_import.write_rejects(rows, str(rejects_out))
        manual_odds_import.write_summary_json(summary, str(summary_out))
        assert valid_out.exists()
        assert rejects_out.exists()
        assert summary_out.exists()
        store = Path(tmp) / "reports" / "store.csv"
        odds_snapshot_store.append_snapshot_rows(str(store), manual_odds_import.split_rows(rows)["valid"])
        assert odds_snapshot_store.summarize_snapshots(str(store))["rows_total"] == 1
        assert manual_odds_import.main(["--input", str(source), "--strict"]) == 2

    print("test_manual_odds_import ok")


if __name__ == "__main__":
    main()
