import csv
import tempfile
from pathlib import Path

import shadow_ledger
import shadow_workflow


def write_closing_csv(path: Path, shadow_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["shadow_id", "closing_odds", "closing_source", "notes"])
        writer.writeheader()
        writer.writerow({"shadow_id": shadow_id, "closing_odds": "2.00", "closing_source": "manual", "notes": "dry"})


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow_ledger.csv"
        data_dir = root / "data"
        data_dir.mkdir()

        info = shadow_workflow.workflow_init(str(ledger))
        assert Path(info["ledger"]).exists()
        assert (root / "reports" / "shadow_candidates_template.csv").exists()
        assert (root / "reports" / "manual_results_import_template.csv").exists()

        today = shadow_workflow.workflow_today(str(ledger), "2026-06-01")
        assert today["today_count"] == 0
        summary = shadow_ledger.summarize_ledger(str(ledger))
        assert summary["signals_total"] == 0

        entry = shadow_ledger.add_shadow_entry(str(ledger), match_date="2026-06-01", home="A", away="B", market="h2h", side="home", taken_odds="2.10")
        closing_template = shadow_workflow.make_closing_template(str(ledger), output=str(root / "reports" / "manual_closing_import_template.csv"))
        rows = list(csv.DictReader(closing_template.open(newline="", encoding="utf-8")))
        assert rows[0]["shadow_id"] == entry["shadow_id"]

        closing_csv = root / "reports" / "manual_closing_import.csv"
        write_closing_csv(closing_csv, entry["shadow_id"])
        before = ledger.read_text(encoding="utf-8")
        imported = shadow_workflow.import_manual_closing(str(ledger), str(closing_csv), dry_run=True)
        assert imported["rows_imported"] == 1
        assert ledger.read_text(encoding="utf-8") == before

        full = shadow_workflow.workflow_full(str(ledger), skip_benchmark=True, skip_dashboard=True)
        assert full["report"]["signals_total"] == 1
        assert full["optional"] == []

        try:
            shadow_workflow.make_closing_template(str(ledger), output=str(data_dir / "bad.csv"))
            raise AssertionError("ecriture data acceptee")
        except ValueError:
            pass

    print("test_shadow_workflow ok")


if __name__ == "__main__":
    main()
