import tempfile
from pathlib import Path

import api_odds_collection_runner as runner
import odds_snapshot_store
from shadow_ledger import read_ledger


def snapshot():
    return {
        "captured_at": "2026-06-01T09:00:00",
        "source": "the_odds_api",
        "source_event_id": "evt1",
        "league": "J League",
        "match_date": "2026-06-01",
        "kickoff_time": "2026-06-01T10:00:00",
        "home_team": "Urawa Reds",
        "away_team": "Kobe",
        "bookmaker": "Book",
        "market_type": "h2h",
        "side": "home",
        "odds": "2.10",
        "is_live": "false",
        "is_near_close": "false",
    }


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        snapshots = root / "reports" / "odds.csv"
        selection = root / "reports" / "selection.csv"
        summary = root / "reports" / "selection.json"
        ledger = root / "reports" / "shadow.csv"
        collect = runner.collect("soccer_japan_j_league", "eu", "h2h", str(root / "reports" / "collect.csv"), allow_network=False)
        assert collect["dry_run"] is True
        assert "--allow-network" in collect["command"]

        odds_snapshot_store.append_snapshot_rows(str(snapshots), [snapshot()])
        selected = runner.select(str(snapshots), str(selection), str(summary), max_events=1, one_side_per_event=True)
        assert selected["selected_rows"] == 1
        assert selection.exists()
        assert summary.exists()

        dry_shadow = runner.to_shadow(str(selection), str(ledger), apply=False)
        assert dry_shadow["dry_run"] is True
        assert read_ledger(str(ledger)) == []
        applied = runner.to_shadow(str(selection), str(ledger), apply=True)
        assert applied["rows_added"] == 1
        assert len(read_ledger(str(ledger))) == 1
        args = runner.parse_args(["--full-pre-match"])
        full = runner.full_pre_match(args)
        assert full["collect"]["dry_run"] is True
        assert runner.main(["--collect", "--sport", "soccer_japan_j_league"]) == 0

    print("test_api_odds_collection_runner ok")


if __name__ == "__main__":
    main()
