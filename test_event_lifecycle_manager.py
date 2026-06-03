import tempfile
from datetime import datetime
from pathlib import Path

import event_lifecycle_manager as lifecycle
from shadow_ledger import add_shadow_entry


def add(path, **kwargs):
    return add_shadow_entry(str(path), league="J League", home="A", away="B", market="h2h", side="home", taken_odds="2.10", bookmaker="Book", **kwargs)


def main():
    now = datetime.fromisoformat("2026-06-03T12:00:00")
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "reports" / "shadow.csv"
        future = add(ledger, match_date="2026-06-04")
        due = add(ledger, match_date="2026-06-03", notes="kickoff_time=2026-06-03T13:00:00")
        overdue = add(ledger, match_date="2026-06-02")
        captured = add(ledger, match_date="2026-06-04", closing_odds="2.00")
        waiting = add(ledger, match_date="2026-06-02", closing_odds="2.00")
        complete = add(ledger, match_date="2026-06-02", closing_odds="2.00", result="win")
        statuses = {
            future["shadow_id"]: lifecycle.classify_row(future, now=now)["lifecycle_status"],
            due["shadow_id"]: lifecycle.classify_row(due, now=now)["lifecycle_status"],
            overdue["shadow_id"]: lifecycle.classify_row(overdue, now=now)["lifecycle_status"],
            captured["shadow_id"]: lifecycle.classify_row(captured, now=now)["lifecycle_status"],
            waiting["shadow_id"]: lifecycle.classify_row(waiting, now=now)["lifecycle_status"],
            complete["shadow_id"]: lifecycle.classify_row(complete, now=now)["lifecycle_status"],
        }
        assert statuses[future["shadow_id"]] == "pre_match_waiting_close"
        assert statuses[due["shadow_id"]] == "near_close_due_soon"
        assert statuses[overdue["shadow_id"]] == "near_close_overdue"
        assert statuses[captured["shadow_id"]] == "closing_captured"
        assert statuses[waiting["shadow_id"]] == "result_overdue"
        assert statuses[complete["shadow_id"]] == "complete"
        report = lifecycle.build_lifecycle_report(str(ledger), now=now)
        assert report["pending_closing"] == 3
        assert report["pending_results"] == 2
        output = Path(tmp) / "reports" / "event_lifecycle.json"
        html = Path(tmp) / "reports" / "event_lifecycle.html"
        lifecycle.write_json(report, str(output))
        lifecycle.write_html(report, str(html))
        assert output.exists() and html.exists()
        assert lifecycle.main(["--ledger", str(ledger), "--status"]) == 0
        assert lifecycle.main(["--ledger", str(ledger), "--due-now"]) == 0
        assert lifecycle.main(["--ledger", str(ledger), "--due-results"]) == 0
    print("test_event_lifecycle_manager ok")


if __name__ == "__main__":
    main()
