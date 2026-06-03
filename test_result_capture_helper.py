import csv
import tempfile
from pathlib import Path

import result_capture_helper
from shadow_ledger import add_shadow_entry, read_ledger


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow.csv"
        entry = add_shadow_entry(str(ledger), match_date="2026-06-06", league="J League", home="A", away="B", market="h2h", side="home", taken_odds="2.10")
        template = root / "reports" / "manual_results_due.csv"
        report = result_capture_helper.write_template(str(ledger), str(template))
        assert report["rows_written"] == 1
        rows = list(csv.DictReader(template.open(newline="", encoding="utf-8")))
        rows[0]["result"] = "win"
        rows[0]["notes"] = "resultat manuel"
        with template.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=result_capture_helper.TEMPLATE_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        validation = result_capture_helper.validate_results(str(ledger), str(template))
        assert validation["ok"] is True
        dry = result_capture_helper.apply_results(str(ledger), str(template), dry_run=True)
        assert dry["rows_updated"] == 1
        assert read_ledger(str(ledger))[0]["result"] == "unknown"
        applied = result_capture_helper.apply_results(str(ledger), str(template), dry_run=False)
        assert applied["rows_updated"] == 1
        assert read_ledger(str(ledger))[0]["result"] == "win"
        output = root / "reports" / "results.json"
        html = root / "reports" / "results.html"
        result_capture_helper.write_json(applied, str(output))
        result_capture_helper.write_html(applied, str(html))
        assert output.exists() and html.exists()
        assert result_capture_helper.main(["--ledger", str(ledger), "--template", str(root / "reports" / "template2.csv")]) == 0
        assert entry["shadow_id"]
    print("test_result_capture_helper ok")


if __name__ == "__main__":
    main()
