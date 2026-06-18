import tempfile
import csv
from pathlib import Path

import shadow_clv_report
import shadow_ledger


def enrich_with_v97_fields(path: Path) -> None:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = [dict(row) for row in reader]
        fields = list(reader.fieldnames or [])
    for field in ["closing_bookmaker", "closing_captured_at", "closing_fixture_id", "closing_quality", "clv", "clv_pct", "closing_status"]:
        if field not in fields:
            fields.append(field)
    rows[0].update({"closing_bookmaker": "Book", "closing_quality": "same_bookmaker", "closing_status": "captured", "clv": "0.05", "clv_pct": "5.0"})
    rows[1].update({"closing_bookmaker": "Book2", "closing_quality": "cross_bookmaker_same_market", "closing_status": "captured", "clv": "-0.05", "clv_pct": "-5.0"})
    rows[2].update({"closing_quality": "unavailable", "closing_status": "overdue_missing"})
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


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
        enrich_with_v97_fields(ledger)

        report = shadow_clv_report.build_shadow_clv_report(str(ledger))
        assert report["signals_total"] == 3
        assert report["signals_with_closing"] == 2
        assert report["signals_with_clv"] == 2
        assert report["pending_closing"] == 1
        assert report["overdue_missing"] == 1
        assert report["pending_results"] == 1
        assert report["clv_coverage"] == 66.67
        assert report["clv_mean"] == 0.0
        assert report["clv_median"] == 0.0
        assert report["clv_positive_rate"] == 50.0
        assert report["sample_size"] == 3
        assert report["roi"] == 5.0
        assert report["profit"] == 0.1
        assert report["drawdown"] == -1.0
        assert report["winrate"] == 50.0
        assert report["verdict"] == "not_validated"
        assert "EPL" in report["clv_by_league"]
        assert "h2h" in report["clv_by_market"]
        assert "home" in report["clv_by_side"]
        assert "s1" in report["clv_by_strategy"]
        assert "inconnu" in report["clv_by_confidence"]
        assert "inconnu" in report["clv_by_bookmaker"]
        assert "2026-06" in report["clv_by_month"]
        assert report["closing_quality_breakdown"]["same_bookmaker"] == 1
        assert report["closing_quality_breakdown"]["cross_bookmaker_same_market"] == 1
        assert report["closing_quality_breakdown"]["unavailable"] == 1
        assert report["closing_status_breakdown"]["captured"] == 2
        assert report["closing_status_breakdown"]["overdue_missing"] == 1
        assert report["signals_with_closing_details"][0]["closing_odds"]
        assert any("sample <30" in warning for warning in report["warnings"])
        assert any("sample <1000" in warning for warning in report["warnings"])

        out_json = root / "reports" / "shadow_clv_report.json"
        out_html = root / "reports" / "shadow_clv_report.html"
        out_csv = root / "reports" / "shadow_clv_summary.csv"
        shadow_clv_report.write_json(report, str(out_json))
        shadow_clv_report.write_html(report, str(out_html))
        shadow_clv_report.write_summary_csv(report, str(out_csv))
        assert out_json.exists()
        assert out_html.exists()
        assert out_csv.exists()
        assert "Shadow CLV Report" in out_html.read_text(encoding="utf-8")
        assert oracle_db.read_text(encoding="utf-8") == before

    print("test_shadow_clv_report ok")


if __name__ == "__main__":
    main()
