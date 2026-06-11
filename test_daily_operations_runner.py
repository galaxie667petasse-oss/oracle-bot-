import tempfile
from pathlib import Path

import daily_operations_runner
from daily_operations_runner import run_daily_operations
from shadow_ledger import add_shadow_entry


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow_ledger.csv"
        add_shadow_entry(
            str(ledger),
            match_date="2026-06-05",
            league="J League",
            home_team="A",
            away_team="B",
            market_type="h2h",
            side="home",
            taken_odds="2.10",
        )
        report = run_daily_operations(
            "2026-06-05",
            reports_dir=str(root / "reports" / "daily"),
            ledger=str(ledger),
            full_dry_run=True,
        )
        assert report["allow_network"] is False
        assert "morning" in report["phases"]
        assert "pre_close" in report["phases"]
        assert "post_match" in report["phases"]
        assert (root / "reports" / "daily" / "daily_operations_summary.json").exists()

        calls = []
        original_next_days = daily_operations_runner.run_next_days

        def fake_next_days(date, **kwargs):
            calls.append({"date": date, **kwargs})
            return {
                "start_date": date,
                "allow_network": kwargs.get("allow_network"),
                "fixtures_total": 0,
                "odds_valid_total": 0,
                "selected_total": 0,
                "lab_only": True,
                "can_influence_picks": False,
            }

        daily_operations_runner.run_next_days = fake_next_days
        try:
            morning = daily_operations_runner.run_daily_operations(
                "2026-06-06",
                reports_dir=str(root / "reports" / "daily_network"),
                ledger=str(ledger),
                allow_network=True,
                morning=True,
            )
        finally:
            daily_operations_runner.run_next_days = original_next_days
        assert calls
        assert calls[0]["allow_network"] is True
        assert morning["allow_network"] is True
        assert morning["morning_scan_network"] is True
        assert morning["next_days_runner_network"] is True

    print("test_daily_operations_runner ok")


if __name__ == "__main__":
    main()
