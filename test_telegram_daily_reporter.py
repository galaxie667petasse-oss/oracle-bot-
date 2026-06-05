import tempfile
from pathlib import Path

import shadow_ledger
import telegram_daily_reporter


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow_ledger.csv"
        shadow_ledger.add_shadow_entry(
            str(ledger),
            match_date="2026-06-05",
            league="EPL",
            home="A",
            away="B",
            market="h2h",
            side="home",
            taken_odds="2.10",
            notes="kickoff_time=2026-06-05T18:00:00",
        )
        original_daily = telegram_daily_reporter.run_daily_operations

        def fake_daily(date, reports_dir, ledger, allow_network=False, full_dry_run=True):
            Path(reports_dir).mkdir(parents=True, exist_ok=True)
            return {"date": date, "phases": {"post_match": {"shadow_report": {"signals_total": 1, "pending_results": 1}}}}

        telegram_daily_reporter.run_daily_operations = fake_daily
        try:
            report = telegram_daily_reporter.run_daily_reporter(
                "2026-06-05",
                ledger=str(ledger),
                reports_dir=str(root / "reports" / "daily"),
                output=str(root / "reports" / "telegram_daily_preview.md"),
                dry_run=True,
            )
        finally:
            telegram_daily_reporter.run_daily_operations = original_daily
        assert report["dry_run"] is True
        assert "RAPPORT DU JOUR" in report["message"]
        assert Path(report["preview"]).exists()
        assert report["notify"]["sent"] == 0
    print("test_telegram_daily_reporter ok")


if __name__ == "__main__":
    main()
