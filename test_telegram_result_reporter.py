import json
import tempfile
from pathlib import Path

import shadow_ledger
import telegram_result_reporter


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow_ledger.csv"
        settled = shadow_ledger.add_shadow_entry(
            str(ledger),
            match_date="2026-06-17",
            league="World Cup",
            home="Ghana",
            away="Panama",
            market="h2h",
            side="home",
            taken_odds="2.26",
            bookmaker="10Bet",
            closing_odds="2.26",
            result="win",
            status="settled",
        )
        pending = shadow_ledger.add_shadow_entry(
            str(ledger),
            match_date="2026-06-18",
            league="World Cup",
            home="A",
            away="B",
            market="h2h",
            side="home",
            taken_odds="2.00",
        )
        rows = shadow_ledger.read_ledger(str(ledger))
        rows[0].update({
            "result_status": "win",
            "result_home_goals": "1",
            "result_away_goals": "0",
            "profit_units": "1.26",
            "settlement_status": "settled",
            "is_result_final": "True",
            "clv": "0.0",
        })
        shadow_ledger.write_ledger(rows, str(ledger))

        evidence = root / "reports" / "evidence_gate.json"
        evidence.write_text(json.dumps({"global_status": "insufficient_evidence", "shadow_sample": 1}, ensure_ascii=False), encoding="utf-8")
        preview = root / "reports" / "telegram_results_preview.md"
        tracking = root / "reports" / "telegram_published_results.json"

        dry = telegram_result_reporter.publish_results(
            str(ledger),
            shadow_id=settled["shadow_id"],
            evidence=str(evidence),
            output=str(preview),
            tracking=str(tracking),
            dry_run=True,
        )
        assert dry["selected"] == 1
        assert dry["dry_run"] is True
        assert dry["tracking_updated"] is False
        assert not tracking.exists()
        text = preview.read_text(encoding="utf-8")
        assert "ORACLE SHADOW LAB" in text
        assert "Ghana - Panama" in text
        assert "Score final : Ghana 1 - 0 Panama" in text
        assert "Profit shadow : +1.26u" in text
        assert "sample insuffisant" in text
        assert "TELEGRAM_BOT_TOKEN" not in text

        pending_report = telegram_result_reporter.publish_results(
            str(ledger),
            shadow_id=pending["shadow_id"],
            evidence=str(evidence),
            output=str(preview),
            tracking=str(tracking),
            dry_run=True,
        )
        assert pending_report["selected"] == 0
        assert pending_report["skipped_pending"] == 1
        assert not tracking.exists()

        original = telegram_result_reporter.send_message_text
        calls = []

        def fake_send(text, allow_send=False, dry_run=True, plain_text=False, no_parse_mode=False):
            calls.append({"allow_send": allow_send, "dry_run": dry_run, "text": text})
            return {"errors": [], "sent": 0 if dry_run else 1, "dry_run": dry_run}

        telegram_result_reporter.send_message_text = fake_send
        try:
            no_send = telegram_result_reporter.publish_results(
                str(ledger),
                shadow_id=settled["shadow_id"],
                evidence=str(evidence),
                output=str(preview),
                tracking=str(tracking),
                allow_send=False,
                dry_run=True,
            )
            assert calls[-1]["allow_send"] is False
            assert calls[-1]["dry_run"] is True
            sent = telegram_result_reporter.publish_results(
                str(ledger),
                shadow_id=settled["shadow_id"],
                evidence=str(evidence),
                output=str(preview),
                tracking=str(tracking),
                allow_send=True,
                dry_run=False,
            )
        finally:
            telegram_result_reporter.send_message_text = original
        assert no_send["tracking_updated"] is False
        assert sent["tracking_updated"] is True
        assert settled["shadow_id"] in tracking.read_text(encoding="utf-8")

        duplicate = telegram_result_reporter.publish_results(
            str(ledger),
            shadow_id=settled["shadow_id"],
            evidence=str(evidence),
            output=str(preview),
            tracking=str(tracking),
            dry_run=True,
        )
        assert duplicate["selected"] == 0
        assert duplicate["duplicate_skipped"] == 1

    print("test_telegram_result_reporter ok")


if __name__ == "__main__":
    main()
