import tempfile
from pathlib import Path

import live_scan_smoke_test


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        calls = []
        original = live_scan_smoke_test.run_next_days

        def fake_next_days(date, **kwargs):
            calls.append({"date": date, **kwargs})
            return {
                "start_date": date,
                "days": kwargs.get("days"),
                "allow_network": kwargs.get("allow_network"),
                "dry_run": kwargs.get("dry_run"),
                "fixtures_total": 4,
                "odds_valid_total": 3,
                "h2h_valid_not_finished_total": 2,
                "selected_total": 1,
                "date_reports": [],
                "lab_only": True,
                "can_influence_picks": False,
            }

        live_scan_smoke_test.run_next_days = fake_next_days
        try:
            report = live_scan_smoke_test.build_live_scan_smoke_test(
                "2026-06-11",
                days=2,
                allow_network=True,
                debug=True,
                output_json=str(root / "reports" / "live.json"),
                output_html=str(root / "reports" / "live.html"),
                output_dir=str(root / "reports" / "next"),
                ledger=str(root / "reports" / "shadow_ledger.csv"),
            )
        finally:
            live_scan_smoke_test.run_next_days = original

        assert calls
        assert calls[0]["allow_network"] is True
        assert calls[0]["dry_run"] is True
        assert calls[0]["apply"] is False
        assert calls[0]["debug_network"] is True
        assert report["ledger_write"] is False
        assert report["telegram_send"] is False
        assert report["fixtures_total"] == 4
        assert (root / "reports" / "live.json").exists()
        assert (root / "reports" / "live.html").exists()
        assert not (root / "reports" / "shadow_ledger.csv").exists()

        def fake_zero(date, **kwargs):
            return {
                "start_date": date,
                "allow_network": kwargs.get("allow_network"),
                "fixtures_total": 0,
                "odds_valid_total": 0,
                "h2h_valid_not_finished_total": 0,
                "selected_total": 0,
                "lab_only": True,
                "can_influence_picks": False,
            }

        live_scan_smoke_test.run_next_days = fake_zero
        try:
            zero = live_scan_smoke_test.build_live_scan_smoke_test(
                "2026-06-12",
                days=1,
                allow_network=False,
                output_json=str(root / "reports" / "zero.json"),
                output_html=str(root / "reports" / "zero.html"),
                output_dir=str(root / "reports" / "zero_next"),
                ledger=str(root / "reports" / "zero_ledger.csv"),
            )
        finally:
            live_scan_smoke_test.run_next_days = original
        assert zero["allow_network"] is False
        assert "reseau non autorise" in " ".join(zero["explanations"])

    print("test_live_scan_smoke_test ok")


if __name__ == "__main__":
    main()
