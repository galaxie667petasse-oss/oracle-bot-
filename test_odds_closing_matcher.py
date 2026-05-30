import tempfile
from pathlib import Path

import odds_closing_matcher
import odds_snapshot_store
import shadow_ledger


def snap(book="Book", odds="2.00"):
    return {
        "captured_at": "2026-06-01T18:59:00",
        "source": "manual_csv",
        "league": "EPL",
        "match_date": "2026-06-01",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "bookmaker": book,
        "market_type": "h2h",
        "side": "home",
        "odds": odds,
        "is_near_close": "true",
    }


def main():
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "reports" / "shadow.csv"
        snapshots = Path(tmp) / "reports" / "odds.csv"
        shadow_ledger.add_shadow_entry(str(ledger), match_date="2026-06-01", league="EPL", home="Arsenal", away="Chelsea", market="h2h", side="home", taken_odds="2.10", bookmaker="Book")
        odds_snapshot_store.append_snapshot_rows(str(snapshots), [snap()])
        dry = odds_closing_matcher.match_closing_snapshots(str(ledger), str(snapshots), dry_run=True)
        assert dry["matches_found"] == 1
        assert shadow_ledger.read_ledger(str(ledger))[0]["closing_odds"] == ""
        report = odds_closing_matcher.match_closing_snapshots(str(ledger), str(snapshots), dry_run=False)
        assert report["closing_updated"] == 1
        row = shadow_ledger.read_ledger(str(ledger))[0]
        assert row["closing_odds"] == "2.0"
        assert float(row["clv_percent"]) > 0
        no_overwrite = odds_closing_matcher.match_closing_snapshots(str(ledger), str(snapshots), dry_run=False)
        assert no_overwrite["closing_updated"] == 0

        ledger2 = Path(tmp) / "reports" / "shadow2.csv"
        snapshots2 = Path(tmp) / "reports" / "odds2.csv"
        shadow_ledger.add_shadow_entry(str(ledger2), match_date="2026-06-01", league="EPL", home="Arsenal", away="Chelsea", market="h2h", side="home", taken_odds="2.10", bookmaker="Book")
        odds_snapshot_store.append_snapshot_rows(str(snapshots2), [snap("Book A"), snap("Book B")])
        ambiguous = odds_closing_matcher.match_closing_snapshots(str(ledger2), str(snapshots2), dry_run=False)
        assert ambiguous["ambiguous"] == 1

    print("test_odds_closing_matcher ok")


if __name__ == "__main__":
    main()
