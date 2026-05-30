import tempfile
from pathlib import Path

import odds_intake_audit
import odds_snapshot_store
import shadow_ledger


def snap(near=False):
    return {
        "captured_at": "2026-06-01T18:55:00" if near else "2026-06-01T10:00:00",
        "source": "manual_csv",
        "league": "EPL",
        "match_date": "2026-06-01",
        "kickoff_time": "2026-06-01T19:00:00",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "bookmaker": "Book",
        "market_type": "h2h",
        "side": "home",
        "odds": "2.00" if near else "2.10",
        "is_near_close": "true" if near else "false",
    }


def main():
    with tempfile.TemporaryDirectory() as tmp:
        snapshots = Path(tmp) / "reports" / "odds.csv"
        ledger = Path(tmp) / "reports" / "shadow.csv"
        empty = odds_intake_audit.build_intake_audit(str(snapshots), str(ledger))
        assert empty["verdict"] == "no_data"
        odds_snapshot_store.append_snapshot_rows(str(snapshots), [snap(False), snap(True)])
        only = odds_intake_audit.build_intake_audit(str(snapshots), str(ledger))
        assert only["verdict"] == "snapshots_only"
        assert only["closing_coverage_possible"] == 100.0
        shadow_ledger.add_shadow_entry(str(ledger), match_date="2026-06-01", league="EPL", home="Arsenal", away="Chelsea", market="h2h", side="home", taken_odds="2.10")
        report = odds_intake_audit.build_intake_audit(str(snapshots), str(ledger))
        assert report["shadow_linked_to_snapshots"] == 1
        assert report["verdict"] == "shadow_started"
        json_out = Path(tmp) / "reports" / "audit.json"
        html_out = Path(tmp) / "reports" / "audit.html"
        odds_intake_audit.write_json(report, str(json_out))
        odds_intake_audit.write_html(report, str(html_out))
        assert json_out.exists()
        assert html_out.exists()

    print("test_odds_intake_audit ok")


if __name__ == "__main__":
    main()
