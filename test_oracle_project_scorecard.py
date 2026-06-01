import json
import tempfile
from pathlib import Path

import oracle_project_scorecard as scorecard


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reports = root / "reports"
        reports.mkdir()
        (reports / "shadow_clv_report.json").write_text(json.dumps({
            "sample_size": 50,
            "clv_coverage": 20.0,
            "clv_mean": 0.01,
        }), encoding="utf-8")
        report = scorecard.build_scorecard(str(reports))
        assert report["scores"]["preuve betting reelle"]["score"] < 50
        assert report["robust_candidates"] == 0
        output = reports / "project_scorecard.json"
        html = reports / "project_scorecard.html"
        scorecard.write_json(report, str(output))
        scorecard.write_html(report, str(html))
        assert output.exists()
        assert "Scorecard" in html.read_text(encoding="utf-8")
    print("test_oracle_project_scorecard ok")


if __name__ == "__main__":
    main()
