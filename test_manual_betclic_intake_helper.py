import csv
import tempfile
from pathlib import Path

import manual_betclic_intake_helper as betclic


def fill_template(path: Path, near_close: str = "false") -> None:
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    rows[0].update({
        "league": "Brazil Serie B",
        "home_team": "Team A",
        "away_team": "Team B",
        "kickoff_time": "2026-06-03T18:00:00",
        "side": "home",
        "odds": "2.10",
        "is_near_close": near_close,
    })
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        csv_path = root / "reports" / "betclic.csv"
        betclic.write_betclic_template(str(csv_path), "2026-06-03")
        fill_template(csv_path)
        report = betclic.validate_betclic_csv(str(csv_path))
        assert report["valid_rows"] == 1
        pack = root / "reports" / "matchday"
        pack_report = betclic.to_matchday_pack(str(csv_path), str(pack))
        assert pack_report["created"] is True
        assert (pack / "matchday_manual_odds.csv").exists()
        ledger = root / "reports" / "shadow.csv"
        dry = betclic.to_shadow(str(csv_path), str(ledger), apply=False)
        assert dry["dry_run"] is True
        assert not ledger.exists()
        assert betclic.main(["--template", str(csv_path), "--date", "2026-06-03"]) == 0
        fill_template(csv_path)
        assert betclic.main(["--validate", str(csv_path)]) == 0
    print("test_manual_betclic_intake_helper ok")


if __name__ == "__main__":
    main()
