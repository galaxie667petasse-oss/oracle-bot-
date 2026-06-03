import json
import tempfile
from pathlib import Path

import near_close_scheduler
from shadow_ledger import add_shadow_entry


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow.csv"
        add_shadow_entry(str(ledger), match_date="2026-06-06", league="J League", home="A", away="B", market="h2h", side="home", taken_odds="2.10")
        add_shadow_entry(str(ledger), match_date="2026-06-06", league="Primera Division - Chile", home="C", away="D", market="h2h", side="away", taken_odds="2.20")
        report = near_close_scheduler.build_schedule(str(ledger))
        assert report["pending_total"] == 2
        assert report["leagues_count"] == 2
        assert any(item["sport_key"] == "soccer_japan_j_league" for item in report["schedule"])
        custom = root / "config" / "sport_map.json"
        custom.parent.mkdir()
        custom.write_text(json.dumps({"J League": "soccer_custom"}), encoding="utf-8")
        custom_report = near_close_scheduler.build_schedule(str(ledger), str(custom))
        assert any(item["sport_key"] == "soccer_custom" for item in custom_report["schedule"])
        output = root / "reports" / "near_close_schedule.json"
        html = root / "reports" / "near_close_schedule.html"
        near_close_scheduler.write_json(report, str(output))
        near_close_scheduler.write_html(report, str(html))
        assert output.exists() and html.exists()
        assert near_close_scheduler.main(["--ledger", str(ledger), "--commands"]) == 0
    print("test_near_close_scheduler ok")


if __name__ == "__main__":
    main()
