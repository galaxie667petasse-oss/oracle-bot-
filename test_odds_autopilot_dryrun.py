import tempfile
import json
from pathlib import Path

import odds_autopilot_dryrun
from shadow_ledger import add_shadow_entry, read_ledger


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow.csv"
        snapshots = root / "reports" / "odds.csv"
        add_shadow_entry(str(ledger), match_date="2026-06-06", league="J League", home="A", away="B", market="h2h", side="home", taken_odds="2.10")
        (root / "reports" / "source_coverage_report.json").write_text(json.dumps({"identified_gaps": ["fixtures API-Football sans odds associees"]}), encoding="utf-8")
        before = read_ledger(str(ledger))
        report = odds_autopilot_dryrun.build_autopilot_report(str(ledger), str(snapshots), str(root / "reports"))
        assert report["current_state"]["pending_closing"] == 1
        assert any("near_close_scheduler.py" in command for command in report["safe_next_commands"])
        assert "appel reseau automatique" in report["blocked_actions"]
        assert report["source_coverage_summary"]["available"] is True
        assert read_ledger(str(ledger)) == before
        output = root / "reports" / "autopilot.json"
        html = root / "reports" / "autopilot.html"
        odds_autopilot_dryrun.write_json(report, str(output))
        odds_autopilot_dryrun.write_html(report, str(html))
        assert output.exists() and html.exists()
        assert odds_autopilot_dryrun.main(["--ledger", str(ledger), "--snapshots", str(snapshots), "--output", str(output), "--html", str(html)]) == 0
    print("test_odds_autopilot_dryrun ok")


if __name__ == "__main__":
    main()
