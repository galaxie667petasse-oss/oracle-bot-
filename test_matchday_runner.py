import csv
import tempfile
from pathlib import Path

import matchday_pack
import matchday_runner
from manual_betclic_intake_helper import write_betclic_template


def fill_manual(path: Path, near_close: bool = False) -> None:
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    for row in rows:
        row["captured_at"] = "2026-06-01T18:55:00" if near_close else "2026-06-01T10:00:00"
        row["bookmaker"] = "Book"
        row["side"] = "home"
        row["odds"] = "2.00" if near_close else "2.10"
        row["is_near_close"] = "true" if near_close else "false"
        row["notes"] = "source manuelle reelle"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def fill_results(path: Path) -> None:
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    rows.append({"shadow_id": "", "result": "win", "notes": "resultat manuel"})
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["shadow_id", "result", "notes"])
        writer.writeheader()
        writer.writerows(rows)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "matches.csv"
        with source.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["match_date", "league", "home_team", "away_team", "kickoff_time"])
            writer.writeheader()
            writer.writerow({"match_date": "2026-06-01", "league": "EPL", "home_team": "Arsenal", "away_team": "Chelsea", "kickoff_time": "2026-06-01T19:00:00"})
        pack = root / "reports" / "matchday_2026_06_01"
        matchday_pack.create_pack("2026-06-01", str(pack), str(source))
        fill_manual(pack / "matchday_manual_odds.csv", near_close=False)
        fill_manual(pack / "matchday_near_close.csv", near_close=True)
        ledger = root / "reports" / "shadow_ledger.csv"
        store = root / "reports" / "odds_snapshots.csv"
        reports = root / "reports"
        assert matchday_runner.validate_pack(str(pack))["valid"]
        dry = matchday_runner.full_dry_run(str(pack), str(ledger), str(store), str(reports), phase="near_close")
        assert dry["dry_run"] is True
        assert dry["staged_shadow_created"] == 1
        assert dry["staged_closing_matched"] == 1
        assert not ledger.exists()
        assert not store.exists()
        pre_pack = root / "reports" / "matchday_pre"
        matchday_pack.create_pack("2026-06-01", str(pre_pack), str(source))
        fill_manual(pre_pack / "matchday_manual_odds.csv", near_close=False)
        pre = matchday_runner.full_dry_run(str(pre_pack), str(ledger), str(store), str(reports), phase="pre_match")
        assert pre["staged_shadow_created"] == 1
        assert pre["phase"]["phase_status"] == "ready_pre_match"
        assert not pre["phase"]["phase_blockers"]
        assert not ledger.exists()
        near_block = matchday_runner.full_dry_run(str(pre_pack), str(ledger), str(store), str(reports), phase="near_close")
        assert near_block["phase"]["phase_status"] == "blocked_near_close"
        assert near_block["phase"]["phase_blockers"]
        fill_results(pack / "matchday_results.csv")
        post = matchday_runner.full_dry_run(str(pack), str(ledger), str(store), str(reports), phase="post_match")
        assert post["staged_results_imported"] == 1
        assert post["phase"]["phase_status"] == "ready_post_match"
        assert matchday_runner.import_taken(str(pack), str(store), apply=True)["valid_taken_rows"] == 1
        assert matchday_runner.to_shadow(str(store), str(ledger), apply=True)["rows_added"] == 1
        assert matchday_runner.import_near_close(str(pack), str(store), apply=True)["valid_near_close_rows"] == 1
        assert matchday_runner.match_closing(str(store), str(ledger), apply=True)["closing_updated"] == 1
        report = matchday_runner.write_matchday_report(str(pack), str(ledger), str(store), str(reports))
        assert "evidence" in report
        assert (reports / "matchday_runner_summary.json").exists()
        intake = root / "reports" / "betclic.csv"
        write_betclic_template(str(intake), "2026-06-01")
        fill_manual(intake, near_close=False)
        intake_rows = list(csv.DictReader(intake.open(newline="", encoding="utf-8")))
        intake_rows[0].update({"league": "EPL", "home_team": "Arsenal", "away_team": "Chelsea", "kickoff_time": "2026-06-01T19:00:00"})
        with intake.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=intake_rows[0].keys())
            writer.writeheader()
            writer.writerows(intake_rows)
        intake_pack = root / "reports" / "matchday_from_intake"
        assert matchday_runner.main(["--from-intake", str(intake), "--pack", str(intake_pack), "--full-dry-run", "--ledger", str(root / "reports" / "ledger_intake.csv"), "--store", str(root / "reports" / "store_intake.csv")]) == 0
    print("test_matchday_runner ok")


if __name__ == "__main__":
    main()
