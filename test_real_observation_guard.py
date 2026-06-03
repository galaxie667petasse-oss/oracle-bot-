import tempfile
from pathlib import Path

from odds_normalizer import write_normalized_csv
from shadow_ledger import add_shadow_entry
import real_observation_guard as guard


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow_ledger.csv"
        snapshots = root / "reports" / "odds_snapshots.csv"
        add_shadow_entry(str(ledger), match_date="2026-06-01", league="EPL", home="Arsenal", away="Chelsea", market="h2h", side="home", taken_odds="2.10", bookmaker="Book", notes="observation reelle")
        rows = [
            {
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
                "odds": "2.10",
                "is_live": "false",
                "is_near_close": "false",
            },
            {
                "captured_at": "2026-06-01T18:55:00",
                "source": "manual_csv",
                "league": "EPL",
                "match_date": "2026-06-01",
                "kickoff_time": "2026-06-01T19:00:00",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "bookmaker": "Book",
                "market_type": "h2h",
                "side": "home",
                "odds": "2.00",
                "is_live": "false",
                "is_near_close": "true",
            },
        ]
        write_normalized_csv(rows, str(snapshots))
        report = guard.build_guard_report(str(ledger), str(snapshots), scope="snapshots")
        assert report["verdict"] == "clean_real_collection", report
        rows[1]["home_team"] = "Liverpool"
        write_normalized_csv(rows, str(snapshots))
        bad = guard.build_guard_report(str(ledger), str(snapshots), scope="snapshots")
        assert bad["near_close_without_taken_count"] == 1
        assert bad["verdict"] == "invalid"
        rows = rows[:1]
        write_normalized_csv(rows, str(snapshots))
        pre = guard.build_guard_report(str(ledger), str(snapshots), phase="pre_match", scope="ledger")
        assert pre["taken_without_near_close_count"] == 1
        assert "taken sans near-close correspondant" in pre["warnings"]
        assert "taken sans near-close correspondant" not in pre["blockers"]
        near_phase = guard.build_guard_report(str(ledger), str(snapshots), phase="near_close", scope="ledger")
        assert "taken sans near-close correspondant" in near_phase["blockers"]
        snapshots_scope = guard.build_guard_report(str(ledger), str(snapshots), phase="pre_match", scope="snapshots")
        assert snapshots_scope["near_close_without_taken_count"] == 0
        notes = guard.check_notes(str(snapshots))
        assert notes["exists"] is True
        output = root / "reports" / "guard.json"
        html = root / "reports" / "guard.html"
        guard.write_json(bad, str(output))
        guard.write_html(bad, str(html))
        assert output.exists() and html.exists()
    print("test_real_observation_guard ok")


if __name__ == "__main__":
    main()
