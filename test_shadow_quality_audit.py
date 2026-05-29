import csv
import tempfile
from pathlib import Path

import shadow_ledger
import shadow_quality_audit


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow_ledger.csv"
        first = shadow_ledger.add_shadow_entry(str(ledger), match_date="2026-06-01", league="EPL", home="A", away="B", market="h2h", side="home", taken_odds="2.10", closing_odds="2.00", result="win", status="settled")
        clean = shadow_quality_audit.audit_shadow_ledger(str(ledger))
        assert clean["verdict"] == "clean"
        assert clean["clv_coverage"] == 100.0
        assert clean["result_coverage"] == 100.0

        rows = shadow_ledger.read_ledger(str(ledger))
        duplicate = dict(rows[0])
        duplicate["shadow_id"] = first["shadow_id"]
        rows.append(duplicate)
        bad = dict(rows[0])
        bad["shadow_id"] = "bad"
        bad["taken_odds"] = "1.00"
        bad["closing_odds"] = "1.00"
        bad["clv_percent"] = "9.0"
        bad["result"] = "bad_result"
        rows.append(bad)
        shadow_ledger.write_ledger(rows, str(ledger))
        report = shadow_quality_audit.audit_shadow_ledger(str(ledger))
        assert report["verdict"] == "invalid"
        assert report["duplicate_shadow_ids"]
        assert report["observations_without_valid_odds"] == 1
        assert report["line_errors"]

        empty = root / "reports" / "empty.csv"
        shadow_ledger.init_ledger(str(empty))
        empty_report = shadow_quality_audit.audit_shadow_ledger(str(empty))
        assert empty_report["rows"] == 0
        assert empty_report["verdict"] == "usable_with_warnings"

        out_json = root / "reports" / "shadow_quality_audit.json"
        out_html = root / "reports" / "shadow_quality_audit.html"
        shadow_quality_audit.write_json(report, str(out_json))
        shadow_quality_audit.write_html(report, str(out_html))
        assert out_json.exists()
        assert out_html.exists()

    print("test_shadow_quality_audit ok")


if __name__ == "__main__":
    main()
