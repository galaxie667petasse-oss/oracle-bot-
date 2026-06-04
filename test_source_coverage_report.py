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
        same_day = root / "same_day.json"
        active.write_text(json.dumps({"sport_keys": ["soccer_japan_j_league", "soccer_brazil_serie_b"]}), encoding="utf-8")
        scan.write_text(json.dumps({"sports": [{"sport_key": "soccer_japan_j_league", "distinct_events": 2, "earliest_match_date": "2026-06-03", "recommended_priority": "high", "usable_for_shadow": True}]}), encoding="utf-8")
        fixtures.write_text(json.dumps({"fixtures_by_league": {"Serie B": 2}, "odds_available_count": 0}), encoding="utf-8")
        same_day.write_text(json.dumps({"odds_valid": 4, "selection_rows": 2}), encoding="utf-8")
        report = coverage.build_source_coverage_report(str(active), str(scan), str(fixtures), same_day_summary_path=str(same_day))
        assert "soccer_brazil_serie_b" in report["competitions_active_not_scanned"]
        assert report["source_recommendations"]
        assert report["same_day_api_football_available"] is True
        assert report["same_day_valid_odds_count"] == 4
        assert report["same_day_shadow_candidates"] == 2
        assert report["next_best_action"] == "review_same_day_shadow_candidates"
        output = root / "reports" / "coverage.json"
        html = root / "reports" / "coverage.html"
        coverage.write_json(report, str(output))
        coverage.write_html(report, str(html))
        assert output.exists() and html.exists()
        assert coverage.main(["--active-sports", str(active), "--the-odds-scan", str(scan), "--fixtures", str(fixtures), "--same-day-summary", str(same_day), "--output", str(output)]) == 0

        manual_report = coverage.build_source_coverage_report(str(active), "", str(fixtures))
        assert manual_report["manual_required_reason"] == "fixtures presentes mais aucune odds API-Football valide exploitable"
        assert manual_report["next_best_action"] == "manual_betclic_required"
    print("test_source_coverage_report ok")


if __name__ == "__main__":
    main()
