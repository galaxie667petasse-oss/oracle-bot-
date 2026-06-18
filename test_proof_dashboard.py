import json
import tempfile
from pathlib import Path

import proof_dashboard


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        shadow = root / "reports" / "shadow.json"
        evidence = root / "reports" / "evidence.json"
        historical = root / "reports" / "historical.json"
        same_day = root / "reports" / "same_day.json"
        near_today = root / "reports" / "near_today.json"
        write_json(shadow, {"signals_total": 10, "sample_size": 10, "clv_mean": None, "clv_coverage": 0, "verdict": "not_validated"})
        write_json(evidence, {"global_status": "insufficient_evidence", "blockers": ["sample shadow < 1000"], "strengths": []})
        write_json(historical, {"summary": {"sample": 1200, "clv_mean": 0.01, "roi_unit": 0.02}, "verdict": "historical_watchlist", "blockers": []})
        write_json(same_day, {"fixtures": 4, "odds_valid": 3, "selection_rows": 2, "would_add_or_added": 2})
        write_json(near_today, {"pending_today": 2, "commands": ["python api_football_odds_adapter.py --fixture-id 1 --allow-network"]})
        report = proof_dashboard.build_dashboard(str(shadow), str(evidence), historical_clv_path=str(historical), same_day_path=str(same_day), near_close_today_path=str(near_today))
        assert report["global_status"] == "insufficient_evidence"
        assert report["telegram_read_only_allowed"] is True
        assert report["telegram_live_pick_allowed"] is False
        assert report["sections"]["historical_clv"]["sample"] == 1200
        assert report["sections"]["telegram_read_only"]["can_influence_picks"] is False
        assert report["sections"]["same_day_intake"]["valid_api_football_odds"] == 3
        assert report["sections"]["same_day_intake"]["near_close_pending_today"] == 2
        out = root / "reports" / "proof.json"
        html = root / "reports" / "proof.html"
        proof_dashboard.write_json(report, str(out))
        proof_dashboard.write_html(report, str(html))
        assert out.exists() and html.exists()
        only_hist = proof_dashboard.build_dashboard(historical_clv_path=str(historical))
        assert only_hist["global_status"] == "historical_evidence_only"
        args = proof_dashboard.parse_args([])
        assert args.shadow == "reports/shadow_clv_report.json"
        assert args.evidence == "reports/evidence_gate.json"
        assert args.quality == "reports/shadow_quality_audit.json"
    print("test_proof_dashboard ok")


if __name__ == "__main__":
    main()
