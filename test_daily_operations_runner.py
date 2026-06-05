import tempfile
from pathlib import Path

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

    print("test_daily_operations_runner ok")


if __name__ == "__main__":
    main()
