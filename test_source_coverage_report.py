import json
import tempfile
from pathlib import Path

import source_coverage_report as coverage


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        active = root / "active.json"
        scan = root / "scan.json"
        fixtures = root / "fixtures.json"
        active.write_text(json.dumps({"sport_keys": ["soccer_japan_j_league", "soccer_brazil_serie_b"]}), encoding="utf-8")
        scan.write_text(json.dumps({"sports": [{"sport_key": "soccer_japan_j_league", "distinct_events": 2, "earliest_match_date": "2026-06-03", "recommended_priority": "high", "usable_for_shadow": True}]}), encoding="utf-8")
        fixtures.write_text(json.dumps({"fixtures_by_league": {"Serie B": 2}, "odds_available_count": 0}), encoding="utf-8")
        report = coverage.build_source_coverage_report(str(active), str(scan), str(fixtures))
        assert "soccer_brazil_serie_b" in report["competitions_active_not_scanned"]
        assert report["source_recommendations"]
        output = root / "reports" / "coverage.json"
        html = root / "reports" / "coverage.html"
        coverage.write_json(report, str(output))
        coverage.write_html(report, str(html))
        assert output.exists() and html.exists()
        assert coverage.main(["--active-sports", str(active), "--the-odds-scan", str(scan), "--fixtures", str(fixtures), "--output", str(output)]) == 0
    print("test_source_coverage_report ok")


if __name__ == "__main__":
    main()
