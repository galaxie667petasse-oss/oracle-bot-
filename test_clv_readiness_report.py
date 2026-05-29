import csv
import json
import tempfile
from pathlib import Path

import clv_readiness_report


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
        oracle_db = root / "oracle_db.json"
        oracle_db.write_text("{}", encoding="utf-8")
        before = oracle_db.read_text(encoding="utf-8")
        data_dir = root / "data"
        data_dir.mkdir()

        no_closing = root / "features_no_closing.csv"
        write_csv(
            no_closing,
            ["date", "home", "away", "market_type", "odds", "odds_source_column"],
            [{"date": "2024-01-01", "home": "A", "away": "B", "market_type": "h2h", "odds": "2.0", "odds_source_column": "B365H"}],
        )
        report = clv_readiness_report.analyze_readiness(str(no_closing))
        assert report["clv_calculable"] is False
        assert report["clv_calculable_now"] is False
        assert report["clv_calculable_after_enrichment"] is False
        assert report["status"] == "indisponible"
        assert "C_*" in report["reason"]
        assert report["markets"]["h2h_closing_possible"] is False

        probe_path = root / "reports" / "closing_odds_probe.json"
        probe_path.parent.mkdir(parents=True, exist_ok=True)
        probe_path.write_text(json.dumps({
            "status": "ok",
            "closing_available": True,
            "h2h_closing_available": True,
            "total_closing_available": False,
            "btts_closing_available": False,
            "detected_columns": {"all_closing": ["C_LTH", "C_LTD", "C_LTA"]},
        }, ensure_ascii=False), encoding="utf-8")
        enriched_possible = clv_readiness_report.analyze_readiness(str(no_closing), closing_probe_path=str(probe_path))
        assert enriched_possible["clv_calculable_now"] is False
        assert enriched_possible["source_has_closing"] is True
        assert enriched_possible["clv_calculable_after_enrichment"] is True
        assert "features_closing_enricher.py" in enriched_possible["recommended_next_command"]

        probe_without_path = root / "reports" / "closing_odds_probe_empty.json"
        probe_without_path.write_text(json.dumps({"status": "ok", "closing_available": False}, ensure_ascii=False), encoding="utf-8")
        enriched_blocked = clv_readiness_report.analyze_readiness(str(no_closing), closing_probe_path=str(probe_without_path))
        assert enriched_blocked["source_has_closing"] is False
        assert enriched_blocked["clv_calculable_after_enrichment"] is False

        with_closing = root / "features_with_closing.csv"
        write_csv(
            with_closing,
            ["date", "home", "away", "market_type", "odds", "C_LTH", "C_LTA", "C_LTD", "closing_source"],
            [{"date": "2024-01-01", "home": "A", "away": "B", "market_type": "h2h", "odds": "2.0", "C_LTH": "1.9", "C_LTA": "4.0", "C_LTD": "3.2", "closing_source": "football-data"}],
        )
        ready = clv_readiness_report.analyze_readiness(str(with_closing))
        assert ready["clv_calculable"] is True
        assert ready["clv_calculable_now"] is True
        assert ready["status"] == "partiel"
        assert ready["markets"]["h2h_closing_possible"] is True
        assert ready["markets"]["over_under_closing_possible"] is False
        assert "C_LTH" in ready["closing_columns_detected"]
        assert "C_LTO" in ready["markets"]["over_under_missing_columns"]

        out_json = root / "reports" / "clv_readiness.json"
        out_html = root / "reports" / "clv_readiness.html"
        clv_readiness_report.write_json(ready, str(out_json))
        clv_readiness_report.write_html(ready, str(out_html))
        assert out_json.exists()
        assert out_html.exists()
        assert "CLV Readiness" in out_html.read_text(encoding="utf-8")
        assert list(data_dir.iterdir()) == []
        assert oracle_db.read_text(encoding="utf-8") == before

    print("test_clv_readiness_report ok")


if __name__ == "__main__":
    main()
