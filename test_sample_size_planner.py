import json
import tempfile
from pathlib import Path

import sample_size_planner


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert sample_size_planner.sample_size_for_edge(0.01) > 0
        report_path = root / "reports" / "shadow_clv_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps({"sample_size": 25, "clv_mean": 0.01, "clv_coverage": 80.0}), encoding="utf-8")
        plan = sample_size_planner.build_sample_size_plan(target_edge=0.01, clv_mean=0.005, clv_std=0.05, shadow_report_path=str(report_path))
        assert plan["current_sample"] == 25
        assert plan["target_edge_required_sample"] > 0
        assert plan["clv_required_sample"] > 0
        assert plan["standard_error_estimate"] is not None
        assert "<100: bruit extreme" in plan["warnings"]
        out_json = root / "reports" / "sample_size_plan.json"
        out_html = root / "reports" / "sample_size_plan.html"
        sample_size_planner.write_json(plan, str(out_json))
        sample_size_planner.write_html(plan, str(out_html))
        assert out_json.exists()
        assert out_html.exists()

    print("test_sample_size_planner ok")


if __name__ == "__main__":
    main()
