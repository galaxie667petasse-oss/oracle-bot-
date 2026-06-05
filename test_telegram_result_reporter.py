import json
import tempfile
from pathlib import Path

import shadow_ledger
import telegram_result_reporter


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow_ledger.csv"
        entry = shadow_ledger.add_shadow_entry(
            str(ledger),
            match_date="2026-06-05",
            league="EPL",
            home="A",
            away="B",
            market="h2h",
            side="home",
            taken_odds="2.10",
            result="win",
            closing_odds="2.00",
        )
        evidence = root / "reports" / "evidence_gate.json"
        evidence.write_text(json.dumps({"global_status": "insufficient_evidence", "shadow_sample": 1}, ensure_ascii=False), encoding="utf-8")
        preview = root / "reports" / "telegram_results_preview.md"
        tracking = root / "reports" / "telegram_published_results.json"
        dry = telegram_result_reporter.publish_results(str(ledger), evidence=str(evidence), output=str(preview), tracking=str(tracking), only_updated=True, dry_run=True)
        assert dry["selected"] == 1
        assert preview.exists()
        assert not tracking.exists()
        original = telegram_result_reporter.send_message_text

        def fake_send(text, allow_send=False, dry_run=True):
            return {"errors": [], "sent": 1, "dry_run": dry_run}

        telegram_result_reporter.send_message_text = fake_send
        try:
            sent = telegram_result_reporter.publish_results(str(ledger), evidence=str(evidence), output=str(preview), tracking=str(tracking), only_updated=True, allow_send=True, dry_run=False)
        finally:
            telegram_result_reporter.send_message_text = original
        assert sent["tracking_updated"] is True
        assert entry["shadow_id"] in tracking.read_text(encoding="utf-8")
        again = telegram_result_reporter.publish_results(str(ledger), evidence=str(evidence), output=str(preview), tracking=str(tracking), only_updated=True, dry_run=True)
        assert again["selected"] == 0
    print("test_telegram_result_reporter ok")


if __name__ == "__main__":
    main()
