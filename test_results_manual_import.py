import csv
import tempfile
from pathlib import Path

import results_manual_import
import shadow_ledger


def write_csv(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["shadow_id", "result", "notes"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow_ledger.csv"
        first = shadow_ledger.add_shadow_entry(str(ledger), match_date="2026-06-01", home="A", away="B", market="h2h", side="home", taken_odds="2.10")
        second = shadow_ledger.add_shadow_entry(str(ledger), match_date="2026-06-02", home="C", away="D", market="h2h", side="away", taken_odds="1.90")
        before = ledger.read_text(encoding="utf-8")

        results_csv = root / "reports" / "manual_results_import.csv"
        write_csv(
            results_csv,
            [
                {"shadow_id": first["shadow_id"], "result": "win", "notes": "settled ok"},
                {"shadow_id": second["shadow_id"], "result": "bad", "notes": "bad result"},
                {"shadow_id": "unknown", "result": "loss", "notes": "unknown"},
            ],
        )

        dry = results_manual_import.import_manual_results(str(ledger), str(results_csv), dry_run=True)
        assert dry["rows_updated"] == 1
        assert len(dry["errors"]) == 2
        assert ledger.read_text(encoding="utf-8") == before

        applied = results_manual_import.import_manual_results(str(ledger), str(results_csv))
        assert applied["rows_updated"] == 1
        assert applied["result_counts"]["win"] == 1
        rows = shadow_ledger.read_ledger(str(ledger))
        updated = [row for row in rows if row["shadow_id"] == first["shadow_id"]][0]
        assert updated["result"] == "win"
        assert updated["status"] == "settled"
        assert "settled ok" in updated["notes"]

    print("test_results_manual_import ok")


if __name__ == "__main__":
    main()
