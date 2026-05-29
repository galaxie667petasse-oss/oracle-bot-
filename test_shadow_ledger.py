import tempfile
from pathlib import Path

import shadow_ledger


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

        export = root / "reports" / "shadow_ledger_export.csv"
        shadow_ledger.export_ledger(str(ledger), str(export))
        assert export.exists()
        assert len(shadow_ledger.read_ledger(str(export))) == 2

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
