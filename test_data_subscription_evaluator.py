import json
import tempfile
from pathlib import Path

from data_subscription_evaluator import build_evaluation, write_html, write_json


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reports = root / "reports"
        reports.mkdir()
        (reports / "shadow_clv_report.json").write_text(json.dumps({"signals_total": 10}), encoding="utf-8")
        low = build_evaluation(str(reports))
        assert low["recommendation"] == "no_paid_needed_yet"
        assert "moins de 30" in low["blockers"][0]

        (reports / "shadow_clv_report.json").write_text(json.dumps({"signals_total": 120}), encoding="utf-8")
        (reports / "api_football_next_days" / "summary.json").parent.mkdir(parents=True)
        (reports / "api_football_next_days" / "summary.json").write_text(json.dumps({"dates_scanned": 3}), encoding="utf-8")
        paid = build_evaluation(str(reports))
        assert paid["project_need"]["requests_per_day_needed"] >= 9
        assert paid["recommendation"] in {"stay_free", "API_Football_Pro", "API_Football_Ultra", "API_Football_Mega"}
        out = reports / "subscription.json"
        html = reports / "subscription.html"
        write_json(paid, str(out))
        write_html(paid, str(html))
        assert out.exists() and html.exists()

    print("test_data_subscription_evaluator ok")


if __name__ == "__main__":
    main()
