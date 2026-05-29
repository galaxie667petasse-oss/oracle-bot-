import tempfile
from pathlib import Path

import shadow_clv_report
import shadow_ledger


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow_ledger.csv"
        oracle_db = root / "oracle_db.json"
        oracle_db.write_text("{}", encoding="utf-8")
        before = oracle_db.read_text(encoding="utf-8")

        shadow_ledger.add_shadow_entry(str(ledger), match_date="2026-06-01", league="EPL", home="A", away="B", market="h2h", side="home", taken_odds="2.10", closing_odds="2.00", strategy_name="s1", result="win", status="settled")
        shadow_ledger.add_shadow_entry(str(ledger), match_date="2026-06-02", league="La Liga", home="C", away="D", market="total", side="over", taken_odds="1.90", closing_odds="2.00", strategy_name="s2", result="loss", status="settled")
        shadow_ledger.add_shadow_entry(str(ledger), match_date="2026-06-03", league="EPL", home="E", away="F", market="h2h", side="away", taken_odds="2.50", strategy_name="s1")

        report = shadow_clv_report.build_shadow_clv_report(str(ledger))
        assert report["signals_total"] == 3
        assert report["signals_with_closing"] == 2
        assert report["clv_coverage"] == 66.67
        assert report["sample_size"] == 3
        assert report["roi"] == 5.0
        assert report["winrate"] == 50.0
        assert report["verdict"] == "sample_insufficient"
        assert "EPL" in report["clv_by_league"]
        assert "h2h" in report["clv_by_market"]
        assert "s1" in report["clv_by_strategy"]
        assert any("sample <1000" in warning for warning in report["warnings"])

        out_json = root / "reports" / "shadow_clv_report.json"
        out_html = root / "reports" / "shadow_clv_report.html"
        shadow_clv_report.write_json(report, str(out_json))
        shadow_clv_report.write_html(report, str(out_html))
        assert out_json.exists()
        assert out_html.exists()
        assert "Shadow CLV Report" in out_html.read_text(encoding="utf-8")
        assert oracle_db.read_text(encoding="utf-8") == before

    print("test_shadow_clv_report ok")


if __name__ == "__main__":
    main()
