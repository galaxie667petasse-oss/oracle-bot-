import csv
import json
import tempfile
from pathlib import Path

import telegram_near_close_reporter as reporter


FIELDS = [
    "shadow_id",
    "match_date",
    "league",
    "home_team",
    "away_team",
    "market_type",
    "side",
    "taken_odds",
    "bookmaker",
    "status",
    "result",
    "closing_odds",
    "closing_bookmaker",
    "closing_source",
    "closing_quality",
    "closing_status",
    "clv",
    "clv_pct",
    "notes",
]


def write_ledger(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow({
            "shadow_id": "sh_test",
            "match_date": "2026-06-17",
            "league": "World Cup",
            "home_team": "Ghana",
            "away_team": "Panama",
            "market_type": "h2h",
            "side": "home",
            "taken_odds": "2.26",
            "bookmaker": "10Bet",
            "status": "observation",
            "result": "unknown",
            "closing_odds": "2.26",
            "closing_bookmaker": "10Bet",
            "closing_source": "api_football_near_close",
            "closing_quality": "same_bookmaker",
            "closing_status": "captured",
            "clv": "0.0",
            "clv_pct": "0.0",
            "notes": "source=api_football; source_event_id=1489385",
        })


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow_ledger.csv"
        output = root / "reports" / "preview.md"
        tracking = root / "reports" / "telegram_published_near_close.json"
        write_ledger(ledger)

        row = reporter._find_row(str(ledger), "sh_test")
        message = reporter.build_message(row)
        assert "NEAR-CLOSE CAPTURÉE" in message
        assert "Match : Ghana - Panama" in message
        assert "Cote prise : 2.26" in message
        assert "Cote near-close : 2.26" in message
        assert "CLV : 0.00%" in message
        assert "Aucune mise" in message

        dry = reporter.publish_near_close(
            str(ledger),
            "sh_test",
            output=str(output),
            tracking=str(tracking),
            dry_run=True,
            allow_send=False,
        )
        assert dry["dry_run"] is True
        assert dry["tracking_updated"] is False
        assert output.exists()
        assert not tracking.exists()

        missing_ledger = root / "reports" / "missing_ledger.csv"
        write_ledger(missing_ledger)
        text = missing_ledger.read_text(encoding="utf-8").replace("2.26,10Bet,api_football_near_close", ",10Bet,api_football_near_close")
        missing_ledger.write_text(text, encoding="utf-8")
        missing = reporter.publish_near_close(
            str(missing_ledger),
            "sh_test",
            output=str(root / "reports" / "missing_preview.md"),
            tracking=str(root / "reports" / "missing_tracking.json"),
            dry_run=True,
            allow_send=False,
        )
        assert missing["selected"] is False
        assert missing["status"] == "missing_closing"

        calls = []
        original_send = reporter.send_message_text

        def fake_send(text, allow_send=False, dry_run=True, plain_text=False, no_parse_mode=False, **kwargs):
            calls.append({
                "text": text,
                "allow_send": allow_send,
                "dry_run": dry_run,
                "plain_text": plain_text,
                "no_parse_mode": no_parse_mode,
            })
            return {"errors": [], "sent": 1 if allow_send and not dry_run else 0, "dry_run": dry_run}

        reporter.send_message_text = fake_send
        try:
            sent = reporter.publish_near_close(
                str(ledger),
                "sh_test",
                output=str(output),
                tracking=str(tracking),
                dry_run=False,
                allow_send=True,
                plain_text=True,
            )
            assert sent["tracking_updated"] is True
            assert calls[-1]["allow_send"] is True
            assert calls[-1]["dry_run"] is False
            assert calls[-1]["plain_text"] is True
            state = json.loads(tracking.read_text(encoding="utf-8"))
            assert state["published_near_close_ids"] == ["sh_test"]

            duplicate = reporter.publish_near_close(
                str(ledger),
                "sh_test",
                output=str(output),
                tracking=str(tracking),
                dry_run=False,
                allow_send=True,
            )
            assert duplicate["selected"] is False
            assert duplicate["duplicate"] is True
            assert len(calls) == 1

            forced = reporter.publish_near_close(
                str(ledger),
                "sh_test",
                output=str(output),
                tracking=str(tracking),
                dry_run=False,
                allow_send=True,
                force=True,
            )
            assert forced["selected"] is True
            assert forced["tracking_updated"] is True
            assert len(calls) == 2
        finally:
            reporter.send_message_text = original_send

    print("test_telegram_near_close_reporter ok")


if __name__ == "__main__":
    main()
