import csv
import tempfile
from pathlib import Path

import closing_manual_import
import shadow_ledger


def write_csv(path: Path, fieldnames, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow_ledger.csv"
        first = shadow_ledger.add_shadow_entry(str(ledger), taken_odds="2.10", match_date="2026-06-01", league="EPL", home="A", away="B", market="h2h", side="home")
        second = shadow_ledger.add_shadow_entry(str(ledger), taken_odds="1.90", match_date="2026-06-02", league="EPL", home="C", away="D", market="h2h", side="away")
        before = ledger.read_text(encoding="utf-8")

        closing_csv = root / "reports" / "manual_closing_import.csv"
        write_csv(
            closing_csv,
            ["shadow_id", "closing_odds", "closing_source", "notes"],
            [
                {"shadow_id": first["shadow_id"], "closing_odds": "2.00", "closing_source": "manual_close", "notes": "ok"},
                {"shadow_id": "unknown", "closing_odds": "2.00", "closing_source": "manual_close", "notes": "bad"},
                {"shadow_id": second["shadow_id"], "closing_odds": "1.00", "closing_source": "manual_close", "notes": "bad odds"},
            ],
        )

        dry = closing_manual_import.import_manual_closing(str(ledger), str(closing_csv), dry_run=True)
        assert dry["rows_imported"] == 1
        assert len(dry["errors"]) == 2
        assert ledger.read_text(encoding="utf-8") == before

        applied = closing_manual_import.import_manual_closing(str(ledger), str(closing_csv), dry_run=False)
        assert applied["rows_imported"] == 1
        assert applied["signals_with_clv"] == 1
        rows = shadow_ledger.read_ledger(str(ledger))
        updated = [row for row in rows if row["shadow_id"] == first["shadow_id"]][0]
        assert updated["closing_odds"] == "2.0"
        assert updated["closing_source"] == "manual_close"
        assert updated["clv_available"] == "True"
        assert float(updated["clv_percent"]) == 0.05

    print("test_closing_manual_import ok")


if __name__ == "__main__":
    main()
