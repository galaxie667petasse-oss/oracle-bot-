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
        write_json(shadow, {"signals_total": 10, "sample_size": 10, "clv_mean": None, "clv_coverage": 0, "verdict": "not_validated"})
        write_json(evidence, {"global_status": "insufficient_evidence", "blockers": ["sample shadow < 1000"], "strengths": []})
        write_json(historical, {"summary": {"sample": 1200, "clv_mean": 0.01, "roi_unit": 0.02}, "verdict": "historical_watchlist", "blockers": []})
        report = proof_dashboard.build_dashboard(str(shadow), str(evidence), historical_clv_path=str(historical))
        assert report["global_status"] == "insufficient_evidence"
        assert report["sections"]["historical_clv"]["sample"] == 1200
        out = root / "reports" / "proof.json"
        html = root / "reports" / "proof.html"
        proof_dashboard.write_json(report, str(out))
        proof_dashboard.write_html(report, str(html))
        assert out.exists() and html.exists()
        only_hist = proof_dashboard.build_dashboard(historical_clv_path=str(historical))
        assert only_hist["global_status"] == "historical_evidence_only"
    print("test_proof_dashboard ok")


if __name__ == "__main__":
    main()
