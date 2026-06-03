import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import odds_shadow_selector
import odds_snapshot_store
from shadow_ledger import add_shadow_entry


def row(event, side, odds, near="false", book="Book"):
    return {
        "captured_at": "2026-06-01T09:00:00",
        "source": "the_odds_api",
        "source_event_id": event,
        "league": "J League",
        "match_date": "2026-06-01",
        "kickoff_time": "2026-06-01T10:00:00Z",
        "home_team": "Urawa Reds",
        "away_team": "Kobe",
        "bookmaker": book,
        "market_type": "h2h",
        "side": side,
        "odds": odds,
        "is_live": "false",
        "is_near_close": near,
    }


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        snapshots = root / "reports" / "odds.csv"
        output = root / "reports" / "selection.csv"
        summary = root / "reports" / "selection.json"
        rows = [
            row("evt1", "home", "2.10"),
            row("evt1", "draw", "3.20"),
            row("evt1", "away", "3.00"),
            row("evt2", "home", "1.90", near="true"),
        ]
        odds_snapshot_store.append_snapshot_rows(str(snapshots), rows)
        result = odds_shadow_selector.select_shadow_rows(
            str(snapshots),
            max_events=1,
            one_side_per_event=True,
            prefer_side="home",
        )
        assert result["summary"]["selected_rows"] == 1
        assert result["summary"]["distinct_events"] == 1
        assert result["rows"][0]["side"] == "home"
        assert all(row["is_near_close"].lower() != "true" for row in result["rows"])

        odds_snapshot_store.write_snapshots(str(output), result["rows"])
        odds_shadow_selector.write_summary(result["summary"], str(summary))
        assert output.exists()
        assert summary.exists()
        assert odds_shadow_selector.main([
            "--snapshots", str(snapshots),
            "--output", str(output),
            "--summary-json", str(summary),
            "--one-side-per-event",
            "--prefer-side", "home",
        ]) == 0

        future_date = (datetime.now().date() + timedelta(days=2)).isoformat()
        snapshots2 = root / "reports" / "odds_future.csv"
        ledger = root / "reports" / "shadow.csv"
        future_row = row("evt_future", "home", "2.30")
        future_row["match_date"] = future_date
        odds_snapshot_store.append_snapshot_rows(str(snapshots2), [future_row])
        add_shadow_entry(str(ledger), match_date=future_date, league="J League", home="Urawa Reds", away="Kobe", market="h2h", side="home", taken_odds="2.30")
        excluded = odds_shadow_selector.select_shadow_rows(str(snapshots2), exclude_events_from_ledger=str(ledger), min_days_ahead=0, max_days_ahead=7)
        assert excluded["summary"]["selected_rows"] == 0
        assert excluded["summary"]["excluded_existing_events_rows"] == 1

    print("test_odds_shadow_selector ok")


if __name__ == "__main__":
    main()
