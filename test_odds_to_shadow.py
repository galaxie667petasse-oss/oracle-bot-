import tempfile
from pathlib import Path

import odds_snapshot_store
import odds_to_shadow
import shadow_ledger


def snapshot():
    return {
        "captured_at": "2026-06-01T10:00:00",
        "source": "manual_csv",
        "league": "EPL",
        "match_date": "2026-06-01",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "bookmaker": "Book",
        "market_type": "h2h",
        "side": "home",
        "odds": "2.10",
    }


def main():
    with tempfile.TemporaryDirectory() as tmp:
        snapshots = Path(tmp) / "reports" / "odds.csv"
        ledger = Path(tmp) / "reports" / "shadow.csv"
        odds_snapshot_store.append_snapshot_rows(str(snapshots), [snapshot()])
        dry = odds_to_shadow.snapshots_to_shadow(str(snapshots), str(ledger), dry_run=True)
        assert dry["rows_added"] == 1
        assert shadow_ledger.read_ledger(str(ledger)) == []
        report = odds_to_shadow.snapshots_to_shadow(str(snapshots), str(ledger), dry_run=False)
        assert report["rows_added"] == 1
        assert len(shadow_ledger.read_ledger(str(ledger))) == 1
        dup = odds_to_shadow.snapshots_to_shadow(str(snapshots), str(ledger), dry_run=False)
        assert dup["duplicates_ignored"] == 1
        text = " ".join(row.get("reason", "") for row in shadow_ledger.read_ledger(str(ledger)))
        assert "selection active" not in text.lower()

    print("test_odds_to_shadow ok")


if __name__ == "__main__":
    main()
