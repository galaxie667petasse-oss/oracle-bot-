import tempfile
import csv
from pathlib import Path

import shadow_ledger


def write_csv(path: Path, fieldnames, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow_ledger.csv"
        data_dir = root / "data"
        data_dir.mkdir()
        oracle_db = root / "oracle_db.json"
        oracle_db.write_text("{}", encoding="utf-8")
        before_db = oracle_db.read_text(encoding="utf-8")

        path = shadow_ledger.init_ledger(str(ledger))
        assert path.exists()
        assert shadow_ledger.read_ledger(str(ledger)) == []

        first = shadow_ledger.add_shadow_entry(
            str(ledger),
            match_date="2026-06-01",
            league="EPL",
            home="Arsenal",
            away="Chelsea",
            market="h2h",
            side="home",
            taken_odds="2.10",
            bookmaker="manual",
            strategy_name="test_signal",
            reason="observation shadow",
        )
        assert first["clv_available"] == "False"
        assert first["clv_percent"] == ""

        second = shadow_ledger.add_shadow_entry(
            str(ledger),
            match_date="2026-06-02",
            league="EPL",
            home="Beta",
            away="Gamma",
            market="h2h",
            side="away",
            taken_odds="2.20",
            closing_odds="2.00",
            closing_source="manual",
            result="win",
            status="settled",
        )
        assert second["clv_available"] == "True"
        assert second["clv_percent"] == 0.1

        try:
            shadow_ledger.add_shadow_entry(str(ledger), taken_odds="1.00")
            raise AssertionError("cote invalide acceptee")
        except ValueError:
            pass
        try:
            shadow_ledger.add_shadow_entry(str(ledger), taken_odds="2.00", closing_odds="1.00")
            raise AssertionError("closing invalide acceptee")
        except ValueError:
            pass

        summary = shadow_ledger.summarize_ledger(str(ledger))
        assert summary["signals_total"] == 2
        assert summary["signals_with_clv"] == 1
        assert summary["clv_coverage"] == 50.0
        assert len(shadow_ledger.pending_closing(str(ledger))) == 1
        assert len(shadow_ledger.pending_results(str(ledger))) == 1
        shadow_ledger.set_result(str(ledger), first["shadow_id"], "loss")
        rows_after_result = shadow_ledger.read_ledger(str(ledger))
        updated_first = [row for row in rows_after_result if row["shadow_id"] == first["shadow_id"]][0]
        assert updated_first["result"] == "loss"
        assert updated_first["status"] == "settled"
        try:
            shadow_ledger.set_result(str(ledger), first["shadow_id"], "bad")
            raise AssertionError("result invalide accepte")
        except ValueError:
            pass

        export = root / "reports" / "shadow_ledger_export.csv"
        shadow_ledger.export_ledger(str(ledger), str(export))
        assert export.exists()
        assert len(shadow_ledger.read_ledger(str(export))) == 2

        batch = root / "reports" / "shadow_candidates_manual.csv"
        write_csv(
            batch,
            shadow_ledger.CANDIDATE_IMPORT_COLUMNS,
            [
                {"match_date": "2026-06-04", "league": "EPL", "home_team": "A", "away_team": "B", "market_type": "h2h", "side": "home", "taken_odds": "2.05", "bookmaker": "manual", "strategy_name": "s1", "reason": "observation", "confidence_label": "", "model_probability": "0.52", "market_probability": "0.50", "no_vig_probability": "", "edge_probability": "0.02", "notes": ""},
                {"match_date": "2026-06-04", "league": "EPL", "home_team": "A", "away_team": "B", "market_type": "h2h", "side": "home", "taken_odds": "2.05", "bookmaker": "manual", "strategy_name": "s1", "reason": "observation", "confidence_label": "", "model_probability": "0.52", "market_probability": "0.50", "no_vig_probability": "", "edge_probability": "0.02", "notes": ""},
                {"match_date": "2026-06-05", "league": "EPL", "home_team": "C", "away_team": "D", "market_type": "h2h", "side": "away", "taken_odds": "2.40", "bookmaker": "manual", "strategy_name": "s2", "reason": "", "confidence_label": "watchlist", "model_probability": "", "market_probability": "", "no_vig_probability": "", "edge_probability": "", "notes": ""},
                {"match_date": "2026-06-06", "league": "EPL", "home_team": "E", "away_team": "F", "market_type": "h2h", "side": "home", "taken_odds": "1.00", "bookmaker": "manual", "strategy_name": "bad", "reason": "", "confidence_label": "", "model_probability": "", "market_probability": "", "no_vig_probability": "", "edge_probability": "", "notes": ""},
            ],
        )
        imported = shadow_ledger.add_csv_entries(str(ledger), str(batch))
        assert imported["rows_read"] == 4
        assert imported["rows_added"] == 2
        assert imported["duplicates_ignored"] == 1
        assert len(imported["errors"]) == 1
        assert len(shadow_ledger.read_ledger(str(ledger))) == 4

        imported_dupes = shadow_ledger.add_csv_entries(str(ledger), str(batch), allow_duplicates=True)
        assert imported_dupes["rows_added"] == 3
        assert imported_dupes["duplicates_ignored"] == 0

        try:
            shadow_ledger.export_ledger(str(ledger), str(data_dir / "shadow.csv"))
            raise AssertionError("ecriture data non bloquee")
        except ValueError:
            pass

        assert list(data_dir.iterdir()) == []
        assert oracle_db.read_text(encoding="utf-8") == before_db

    print("test_shadow_ledger ok")


if __name__ == "__main__":
    main()
