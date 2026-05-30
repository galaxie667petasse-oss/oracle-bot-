import tempfile
from pathlib import Path

import odds_e2e_demo


def main():
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "data" / "features_modern.csv"
        data.parent.mkdir()
        data.write_text("safe\n", encoding="utf-8")
        before = data.read_text(encoding="utf-8")
        out = Path(tmp) / "reports" / "odds_e2e_demo"
        summary = odds_e2e_demo.run_demo(str(out))
        assert (out / "manual_odds_snapshot_demo.csv").exists()
        assert (out / "odds_snapshots_demo.csv").exists()
        assert (out / "shadow_ledger_demo.csv").exists()
        assert (out / "shadow_clv_report_demo.json").exists()
        assert summary["shadow_report"]["signals_total"] == 1
        assert summary["shadow_report"]["signals_with_closing"] == 1
        assert data.read_text(encoding="utf-8") == before

    print("test_odds_e2e_demo ok")


if __name__ == "__main__":
    main()
