import tempfile
from pathlib import Path

import shadow_ledger
import telegram_ops_runner


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
        original_daily = telegram_ops_runner.run_daily_reporter
        original_shadow = telegram_ops_runner.publish_shadow_observations
        original_results = telegram_ops_runner.publish_results

        def fake_daily(*args, **kwargs):
            return {"phase": "daily", "dry_run": kwargs.get("dry_run", True)}

        def fake_shadow(*args, **kwargs):
            return {"phase": "shadow", "selected": 1, "dry_run": kwargs.get("dry_run", True)}

        def fake_results(*args, **kwargs):
            return {"phase": "results", "selected": 0, "dry_run": kwargs.get("dry_run", True)}

        telegram_ops_runner.run_daily_reporter = fake_daily
        telegram_ops_runner.publish_shadow_observations = fake_shadow
        telegram_ops_runner.publish_results = fake_results
        try:
            report = telegram_ops_runner.run_telegram_ops(
                "2026-06-05",
                ledger=str(ledger),
                reports_dir=str(root / "reports" / "telegram_ops"),
                full_dry_run=True,
            )
        finally:
            telegram_ops_runner.run_daily_reporter = original_daily
            telegram_ops_runner.publish_shadow_observations = original_shadow
            telegram_ops_runner.publish_results = original_results
        assert report["dry_run"] is True
        assert "morning_daily" in report["phases"]
        assert "pre_close" in report["phases"]
        assert "post_match" in report["phases"]
        assert report["allow_send"] is False
    print("test_telegram_ops_runner ok")


if __name__ == "__main__":
    main()
