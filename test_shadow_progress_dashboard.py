import json
import tempfile
from pathlib import Path

import shadow_progress_dashboard
from event_lifecycle_manager import build_lifecycle_report, write_json as write_lifecycle_json
from shadow_ledger import add_shadow_entry


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow.csv"
        add_shadow_entry(str(ledger), match_date="2026-06-06", league="J League", home="A", away="B", market="h2h", side="home", taken_odds="2.10")
        lifecycle_path = root / "reports" / "event_lifecycle.json"
        write_lifecycle_json(build_lifecycle_report(str(ledger)), str(lifecycle_path))
        evidence_path = root / "reports" / "evidence_gate.json"
        evidence_path.write_text(json.dumps({"global_status": "insufficient_evidence", "blockers": ["sample shadow < 1000"]}), encoding="utf-8")
        report = shadow_progress_dashboard.build_progress_dashboard(str(ledger), str(lifecycle_path), str(evidence_path))
        assert report["observations"] == 1
        assert report["pending_closing"] == 1
        assert report["sample_progress"]["1000"]["remaining"] == 999
        output = root / "reports" / "shadow_progress.html"
        json_out = root / "reports" / "shadow_progress.json"
        shadow_progress_dashboard.write_json(report, str(json_out))
        shadow_progress_dashboard.write_html(report, str(output))
        assert output.exists() and json_out.exists()
        assert shadow_progress_dashboard.main(["--ledger", str(ledger), "--lifecycle", str(lifecycle_path), "--evidence", str(evidence_path), "--output", str(output), "--json", str(json_out)]) == 0
    print("test_shadow_progress_dashboard ok")


if __name__ == "__main__":
    main()
