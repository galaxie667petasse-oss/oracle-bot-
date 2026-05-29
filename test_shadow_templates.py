import csv
import tempfile
from pathlib import Path

import shadow_ledger
import shadow_templates


def read_rows(path: Path):
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reports = root / "reports"
        data_dir = root / "data"
        data_dir.mkdir()
        ledger = reports / "shadow_ledger.csv"
        first = shadow_ledger.add_shadow_entry(str(ledger), match_date="2026-06-01", home="A", away="B", market="h2h", side="home", taken_odds="2.10")
        shadow_ledger.add_shadow_entry(str(ledger), match_date="2026-06-02", home="C", away="D", market="h2h", side="away", taken_odds="2.00", closing_odds="1.90", result="win", status="settled")

        candidates = shadow_templates.create_candidates_template(str(reports / "shadow_candidates_template.csv"))
        closing = shadow_templates.create_closing_template(str(reports / "manual_closing_import_template.csv"), ledger=str(ledger))
        results = shadow_templates.create_results_template(str(reports / "manual_results_import_template.csv"), ledger=str(ledger))
        assert candidates.exists()
        assert closing.exists()
        assert results.exists()
        assert read_rows(closing)[0]["shadow_id"] == first["shadow_id"]
        assert read_rows(results)[0]["shadow_id"] == first["shadow_id"]

        try:
            shadow_templates.create_candidates_template(str(candidates))
            raise AssertionError("overwrite accepte sans force")
        except FileExistsError:
            pass
        shadow_templates.create_candidates_template(str(candidates), force=True)

        try:
            shadow_templates.create_candidates_template(str(data_dir / "bad.csv"))
            raise AssertionError("ecriture data acceptee")
        except ValueError:
            pass

    print("test_shadow_templates ok")


if __name__ == "__main__":
    main()
