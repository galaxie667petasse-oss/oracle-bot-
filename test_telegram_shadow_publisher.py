import tempfile
from pathlib import Path

import shadow_ledger
import telegram_shadow_publisher


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow_ledger.csv"
        old_entry = shadow_ledger.add_shadow_entry(
            str(ledger),
            match_date="2026-06-05",
            league="EPL",
            home="A",
            away="B",
            market="h2h",
            side="home",
            taken_odds="2.10",
        )
        entry = shadow_ledger.add_shadow_entry(
            str(ledger),
            match_date="2026-06-11",
            league="EPL",
            home="C",
            away="D",
            market="h2h",
            side="away",
            taken_odds="3.10",
        )
        entry2 = shadow_ledger.add_shadow_entry(
            str(ledger),
            match_date="2026-06-11",
            league="EPL",
            home="E",
            away="F",
            market="h2h",
            side="home",
            taken_odds="1.90",
        )
        preview = root / "reports" / "telegram_shadow_preview.md"
        tracking = root / "reports" / "telegram_published_observations.json"
        dry = telegram_shadow_publisher.publish_shadow_observations(str(ledger), output=str(preview), tracking=str(tracking), only_new=True, dry_run=True)
        assert dry["selected"] == 0
        assert dry["skipped_without_tracking_baseline"] == 3
        assert preview.exists()
        assert not tracking.exists()

        since = telegram_shadow_publisher.publish_shadow_observations(
            str(ledger),
            output=str(preview),
            tracking=str(tracking),
            only_new=True,
            since_date="2026-06-11",
            max_messages=1,
            dry_run=True,
        )
        assert since["selected"] == 1
        assert since["skipped_old"] == 1
        assert since["max_messages"] == 1
        assert old_entry["shadow_id"] not in preview.read_text(encoding="utf-8")

        mark_tracking = root / "reports" / "telegram_marked_observations.json"
        mark_dry = telegram_shadow_publisher.publish_shadow_observations(
            str(ledger),
            output=str(root / "reports" / "mark_preview.md"),
            tracking=str(mark_tracking),
            mark_existing_as_published=True,
            dry_run=True,
        )
        assert mark_dry["would_mark_existing"] == 3
        assert not mark_tracking.exists()

        ledger_before = ledger.read_text(encoding="utf-8")
        mark_apply_preview = root / "reports" / "mark_apply_preview.md"
        mark_apply = telegram_shadow_publisher.publish_shadow_observations(
            str(ledger),
            output=str(mark_apply_preview),
            tracking=str(mark_tracking),
            mark_existing_as_published=True,
            dry_run=False,
        )
        assert mark_apply["tracking_updated"] is True
        assert mark_tracking.exists()
        assert not mark_apply_preview.exists()
        assert ledger.read_text(encoding="utf-8") == ledger_before
        tracking_text = mark_tracking.read_text(encoding="utf-8")
        assert old_entry["shadow_id"] in tracking_text
        assert entry["shadow_id"] in tracking_text
        assert entry2["shadow_id"] in tracking_text
        original = telegram_shadow_publisher.send_message_text

        def fake_send(text, allow_send=False, dry_run=True):
            return {"errors": [], "sent": 1, "dry_run": dry_run}

        telegram_shadow_publisher.send_message_text = fake_send
        send_tracking = root / "reports" / "telegram_sent_observations.json"
        try:
            sent = telegram_shadow_publisher.publish_shadow_observations(
                str(ledger),
                output=str(preview),
                tracking=str(send_tracking),
                only_new=True,
                since_date="2026-06-11",
                max_messages=2,
                allow_send=True,
                dry_run=False,
            )
        finally:
            telegram_shadow_publisher.send_message_text = original
        assert sent["tracking_updated"] is True
        send_text = send_tracking.read_text(encoding="utf-8")
        assert entry["shadow_id"] in send_text
        assert entry2["shadow_id"] in send_text
        second = telegram_shadow_publisher.publish_shadow_observations(str(ledger), output=str(preview), tracking=str(send_tracking), only_new=True, since_date="2026-06-11", dry_run=True)
        assert second["selected"] == 0
    print("test_telegram_shadow_publisher ok")


if __name__ == "__main__":
    main()
