import csv
import tempfile
from pathlib import Path

import odds_lab_wizard
from manual_odds_import import MANUAL_COLUMNS


def write_manual(path: Path, odds: str = "2.10") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANUAL_COLUMNS)
        writer.writeheader()
        writer.writerow({
            "captured_at": "2026-06-01T10:00:00",
            "source": "manual_csv",
            "league": "EPL",
            "match_date": "2026-06-01",
            "kickoff_time": "2026-06-01T19:00:00",
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "bookmaker": "Book",
            "market_type": "h2h",
            "side": "home",
            "odds": odds,
            "is_live": "false",
            "is_near_close": "false",
            "notes": "test",
        })


def main():
    with tempfile.TemporaryDirectory() as tmp:
        reports = Path(tmp) / "reports"
        store = reports / "odds.csv"
        ledger = reports / "shadow.csv"
        status = odds_lab_wizard.build_status(str(store), str(ledger), str(reports))
        assert status["snapshots_total"] == 0
        templates = odds_lab_wizard.make_templates(str(reports), str(ledger), force=True)
        assert Path(templates["manual_odds"]).exists()
        manual = reports / "manual.csv"
        write_manual(manual)
        valid = odds_lab_wizard.validate_manual(str(manual))
        assert valid["valid_rows"] == 1
        bad = reports / "bad.csv"
        write_manual(bad, odds="0.5")
        invalid = odds_lab_wizard.validate_manual(str(bad))
        assert invalid["rejected_rows"] == 1
        imported = odds_lab_wizard.import_manual(str(manual), str(store))
        assert imported["imported"] is True
        dry = odds_lab_wizard.dry_run_full(str(store), str(ledger), str(reports))
        assert dry["odds_to_shadow"]["dry_run"] is True
        demo = odds_lab_wizard.demo(str(reports), str(store), str(ledger), apply=False)
        assert Path(demo["manual_demo"]).exists()
        assert "Demo synthetique" in demo["message"]
        actions = odds_lab_wizard.next_actions(str(store), str(ledger))
        assert actions
        real = odds_lab_wizard.real_start(str(store), str(ledger))
        assert "guard" in real
        archive = odds_lab_wizard.archive_tests(str(reports), label="before_real")
        assert "archive" in archive and "reset" in archive
        pack = odds_lab_wizard.matchday_pack_command("2026-06-01", str(reports))
        assert Path(pack["output_dir"]).exists()
        status_pack = odds_lab_wizard.pack_status(pack["output_dir"])
        assert status_pack["ready_for_dry_run"]
        dry_matchday = odds_lab_wizard.matchday_full_dry_run(pack["output_dir"], str(ledger), str(store), str(reports))
        assert dry_matchday["dry_run"] is True

    print("test_odds_lab_wizard ok")


if __name__ == "__main__":
    main()
