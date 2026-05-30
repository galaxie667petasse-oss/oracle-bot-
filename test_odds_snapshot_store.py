import tempfile
from pathlib import Path

import odds_snapshot_store


def row():
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
        "is_near_close": "true",
    }


def main():
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "reports" / "odds_snapshots.csv"
        odds_snapshot_store.init_store(str(store))
        assert store.exists()
        report = odds_snapshot_store.append_snapshot_rows(str(store), [row(), row()])
        assert report["appended_rows"] == 2
        summary = odds_snapshot_store.summarize_snapshots(str(store))
        assert summary["rows_total"] == 2
        assert summary["near_close_rows"] == 2
        assert summary["clv_readiness_potential"] == "near_close_only"
        validation = odds_snapshot_store.validate_store(str(store))
        assert validation["valid"] is True
        filtered = odds_snapshot_store.filter_snapshots(str(store), market="h2h")
        assert len(filtered) == 2
        near = Path(tmp) / "reports" / "near.csv"
        odds_snapshot_store.export_near_close(str(store), str(near))
        assert near.exists()
        dedupe = odds_snapshot_store.dedupe_snapshots(str(store))
        assert dedupe["removed"] == 1
        export = Path(tmp) / "reports" / "export.csv"
        odds_snapshot_store.export_snapshots(str(store), str(export))
        assert export.exists()
        invalid = dict(row())
        invalid["odds"] = "0.5"
        report = odds_snapshot_store.append_snapshot_rows(str(store), [invalid])
        assert report["invalid_rows"] == 1

    print("test_odds_snapshot_store ok")


if __name__ == "__main__":
    main()
