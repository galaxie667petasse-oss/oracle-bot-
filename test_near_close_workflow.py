import tempfile
from pathlib import Path

import near_close_workflow
from odds_normalizer import write_normalized_csv
from shadow_ledger import add_shadow_entry, read_ledger


def near_close_row():
    return {
        "captured_at": "2026-06-01T18:55:00",
        "source": "manual_csv",
        "source_event_id": "evt1",
        "league": "J League",
        "match_date": "2026-06-01",
        "kickoff_time": "2026-06-01T19:00:00",
        "home_team": "Urawa Reds",
        "away_team": "Kobe",
        "bookmaker": "Book",
        "market_type": "h2h",
        "side": "home",
        "odds": "2.00",
        "is_near_close": "true",
    }


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow.csv"
        snapshots = root / "reports" / "odds.csv"
        near_file = root / "reports" / "near.csv"
        add_shadow_entry(
            str(ledger),
            match_date="2026-06-01",
            league="J League",
            home="Urawa Reds",
            away="Kobe",
            market="h2h",
            side="home",
            taken_odds="2.10",
            bookmaker="Book",
        )
        write_normalized_csv([near_close_row()], str(near_file))

        status = near_close_workflow.build_status(str(ledger))
        assert status["pending_closing_count"] == 1
        commands = near_close_workflow.suggest_commands(str(ledger))
        assert any("soccer_japan_j_league" in command for command in commands["commands"])

        dry = near_close_workflow.run_near_close_file(str(ledger), str(snapshots), str(near_file), apply=False, reports_dir=str(root / "reports"))
        assert dry["dry_run"] is True
        assert dry["match_report"]["matches_found"] == 1
        assert read_ledger(str(ledger))[0]["closing_odds"] == ""

        applied = near_close_workflow.run_near_close_file(str(ledger), str(snapshots), str(near_file), apply=True, reports_dir=str(root / "reports"))
        assert applied["dry_run"] is False
        assert read_ledger(str(ledger))[0]["closing_odds"] == "2.0"
        output = root / "reports" / "near_close_plan.json"
        html = root / "reports" / "near_close_plan.html"
        near_close_workflow.write_plan(status, str(output), str(html))
        assert output.exists() and html.exists()
        assert near_close_workflow.main(["--ledger", str(ledger), "--status"]) == 0

    print("test_near_close_workflow ok")


if __name__ == "__main__":
    main()
