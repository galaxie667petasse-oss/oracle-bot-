import tempfile
from pathlib import Path

import shadow_ledger
import telegram_shadow_publisher


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
        )
        preview = root / "reports" / "telegram_shadow_preview.md"
        tracking = root / "reports" / "telegram_published_observations.json"
        dry = telegram_shadow_publisher.publish_shadow_observations(str(ledger), output=str(preview), tracking=str(tracking), only_new=True, dry_run=True)
        assert dry["selected"] == 1
        assert preview.exists()
        assert not tracking.exists()
        original = telegram_shadow_publisher.send_message_text

        def fake_send(text, allow_send=False, dry_run=True):
            return {"errors": [], "sent": 1, "dry_run": dry_run}

        telegram_shadow_publisher.send_message_text = fake_send
        try:
            sent = telegram_shadow_publisher.publish_shadow_observations(str(ledger), output=str(preview), tracking=str(tracking), only_new=True, allow_send=True, dry_run=False)
        finally:
            telegram_shadow_publisher.send_message_text = original
        assert sent["tracking_updated"] is True
        assert entry["shadow_id"] in tracking.read_text(encoding="utf-8")
        second = telegram_shadow_publisher.publish_shadow_observations(str(ledger), output=str(preview), tracking=str(tracking), only_new=True, dry_run=True)
        assert second["selected"] == 0
    print("test_telegram_shadow_publisher ok")


if __name__ == "__main__":
    main()
