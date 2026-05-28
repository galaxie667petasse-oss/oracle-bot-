import json
import tempfile
from pathlib import Path

import benchmark_governance


def synthetic_db():
    records = []
    for idx, date in enumerate(["2021-01-01", "2022-01-01", "2023-01-01", "2024-01-01", "2025-01-01"]):
        records.append({
            "id": f"r{idx}",
            "match_id": f"m{idx}",
            "date_key": date,
            "date": date,
            "home": "Alpha",
            "away": "Beta",
            "competition": "TEST",
            "market_type": "h2h",
            "pari": "Victoire Alpha",
            "odds": 1.8,
            "result": "win" if idx in (0, 1, 2, 4) else "loss",
            "shadow": True,
        })
        records.append({
            "id": f"t{idx}",
            "match_id": f"tm{idx}",
            "date_key": date,
            "date": date,
            "home": "Gamma",
            "away": "Delta",
            "competition": "TEST",
            "market_type": "total",
            "pari": "Plus de 2.5 buts",
            "odds": 1.9,
            "result": "loss" if idx in (3, 4) else "win",
            "shadow": True,
        })
    return {"scans": {"synthetic": {"picks": [], "candidates": records}}}


def main():
    validation_positive_test_negative = {
        "validation": {"picks": 500, "roi": 3.0},
        "test": {"picks": 500, "roi": -2.0},
    }
    assert benchmark_governance.robustness_score(validation_positive_test_negative) < 80

    failed = benchmark_governance._section("Echec volontaire", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert failed["ok"] is False
    assert "boom" in failed["error"]

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        oracle_db = root / "oracle_db.json"
        oracle_db.write_text("{}", encoding="utf-8")
        before = oracle_db.read_text(encoding="utf-8")

        benchmark = benchmark_governance.build_benchmark(str(root / "features_absent.csv"), db=synthetic_db())
        assert benchmark["summary"]["sections_available"] >= 1
        assert benchmark["summary"]["sections_failed"]
        assert benchmark["summary"]["robust_candidates"] == 0
        assert benchmark["summary"]["strategies_with_clv_available"] == 0
        assert any("CLV report" in warning for warning in benchmark["summary"]["warnings"])
        assert any("Calibration report" in warning for warning in benchmark["summary"]["warnings"])
        assert any("Statistical validation" in warning for warning in benchmark["summary"]["warnings"])
        assert any("XG quality report" in warning for warning in benchmark["summary"]["warnings"])
        assert any("Big 5 xG summary" in warning for warning in benchmark["summary"]["warnings"])
        assert any("CLV readiness" in warning for warning in benchmark["summary"]["warnings"])
        assert benchmark["registry"]
        assert all(entry.get("governance_status") != "production_allowed" for entry in benchmark["registry"])
        assert all("clv_mean" in entry for entry in benchmark["registry"])
        assert all("ece" in entry for entry in benchmark["registry"])
        assert all("bootstrap_roi_p05" in entry for entry in benchmark["registry"])
        assert all("p_value_adjusted" in entry for entry in benchmark["registry"])
        assert all("rejection_reasons" in entry for entry in benchmark["registry"])
        assert oracle_db.read_text(encoding="utf-8") == before

        registry_path = root / "model_registry.json"
        benchmark_governance.write_registry(benchmark["registry"], str(registry_path))
        registry_text = registry_path.read_text(encoding="utf-8").lower()
        assert "secret" not in registry_text
        assert "token" not in registry_text
        assert "password" not in registry_text
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        assert isinstance(registry.get("models"), list)
        assert all("robustness_score" in entry for entry in registry["models"])
        assert all("governance_status" in entry for entry in registry["models"])

        clv_path = root / "reports" / "clv.json"
        calibration_path = root / "reports" / "calibration.json"
        stats_path = root / "reports" / "stats.json"
        clv_path.parent.mkdir(parents=True, exist_ok=True)
        clv_path.write_text(json.dumps({"status": "indisponible", "groups": {}, "summary": {}}, ensure_ascii=False), encoding="utf-8")
        calibration_path.write_text(json.dumps({"status": "indisponible"}, ensure_ascii=False), encoding="utf-8")
        stats_path.write_text(json.dumps({"status": "indisponible", "by_strategy": {}}, ensure_ascii=False), encoding="utf-8")
        benchmark_with_reports = benchmark_governance.build_benchmark(
            str(root / "features_absent.csv"),
            db=synthetic_db(),
            clv_report_path=str(clv_path),
            calibration_report_path=str(calibration_path),
            statistical_report_path=str(stats_path),
        )
        assert benchmark_with_reports["summary"]["clv_report_available"] is False
        assert benchmark_with_reports["summary"]["robust_candidates"] == 0

        big5_path = root / "reports" / "big5_xg_summary.json"
        clv_ready_path = root / "reports" / "clv_readiness.json"
        big5_path.write_text(json.dumps({
            "global": {
                "leagues_available": 3,
                "leagues_exploitable": 3,
                "leagues_clv_available": 0,
                "observations": 1,
                "watchlist": 2,
                "robust_candidates": 0,
            },
            "leagues": [],
            "lab_only": True,
            "can_influence_picks": False,
        }, ensure_ascii=False), encoding="utf-8")
        clv_ready_path.write_text(json.dumps({
            "status": "indisponible",
            "clv_calculable": False,
            "missing_columns": ["C_LTH", "C_LTA"],
            "markets": {"h2h_closing_possible": False},
            "lab_only": True,
            "can_influence_picks": False,
        }, ensure_ascii=False), encoding="utf-8")
        benchmark_big5 = benchmark_governance.build_benchmark(
            str(root / "features_absent.csv"),
            db=synthetic_db(),
            big5_xg_summary_path=str(big5_path),
            clv_readiness_path=str(clv_ready_path),
        )
        assert benchmark_big5["summary"]["big5_xg_available"] is True
        assert benchmark_big5["summary"]["clv_readiness_available"] is True
        assert benchmark_big5["summary"]["clv_calculable"] is False
        assert benchmark_big5["summary"]["big5_observation_count"] == 3
        assert benchmark_big5["summary"]["big5_candidate_count"] == 0
        assert "C_LTH" in benchmark_big5["summary"]["clv_missing_columns"]
        assert any("CLV non calculable" in blocker for blocker in benchmark_big5["summary"]["promotion_blockers"])
        assert benchmark_big5["summary"]["robust_candidates"] == 0

        quality_path = root / "reports" / "xg_quality.json"
        model_path = root / "reports" / "xg_model.json"
        quality_path.write_text(json.dumps({
            "status": "ok",
            "verdict": "fragile",
            "rows": 760,
            "xg_coverage": 90.0,
            "missing_seasons": ["2021-2022"],
            "total_expected_matches": 1900,
            "total_actual_matches": 1520,
            "lab_only": True,
            "can_influence_picks": False,
        }, ensure_ascii=False), encoding="utf-8")
        model_path.write_text(json.dumps({
            "verdict": {
                "promotion_allowed": False,
                "selected_test": {"picks": 1200, "roi": -0.1},
                "governance_note": "observation technique seulement",
                "rejection_reasons": ["ROI test negatif"],
                "xg_improves_brier": True,
                "xg_improves_log_loss": True,
                "edge_test_positive": False,
                "sample_test_sufficient": True,
            },
            "comparison": {
                "with_xg": {"brier": 0.20, "log_loss": 0.60},
                "market": {"brier": 0.21, "log_loss": 0.61},
                "delta_brier_xg_vs_market": -0.01,
                "delta_log_loss_xg_vs_market": -0.01,
            },
            "market_baseline": {"test": {"brier": 0.21, "log_loss": 0.61}},
            "models": [{}, {"selected_validation": {"picks": 1000, "roi": 1.0}}],
            "split_config": {"test_from": "2024-01-01"},
            "join_quality_context": {
                "join_rate": 39.89,
                "join_quality": "insuffisant",
                "modeling_allowed_by_join_quality": False,
                "alias_applied": True,
                "unmatched_count": 1142,
                "join_blocks_promotion": True,
            },
        }, ensure_ascii=False), encoding="utf-8")
        benchmark_with_xg = benchmark_governance.build_benchmark(
            str(root / "features_absent.csv"),
            db=synthetic_db(),
            xg_quality_path=str(quality_path),
            xg_model_path=str(model_path),
        )
        assert benchmark_with_xg["summary"]["xg_quality_available"] is True
        assert benchmark_with_xg["summary"]["xg_model_available"] is True
        assert benchmark_with_xg["summary"]["robust_candidates"] == 0
        xg_entries = [entry for entry in benchmark_with_xg["registry"] if entry.get("name") == "understat_epl_2020_2025_rolling_xg_lab"]
        assert xg_entries
        assert xg_entries[0]["lab_only"] is True
        assert xg_entries[0]["can_influence_picks"] is False
        assert xg_entries[0]["quality_verdict"] == "fragile"
        assert xg_entries[0]["promotion_allowed"] is False
        assert xg_entries[0]["join_quality"] == "insuffisant"
        assert xg_entries[0]["join_blocks_promotion"] is True
        assert xg_entries[0]["unmatched_count"] == 1142
        assert any("quality gate" in reason.lower() for reason in xg_entries[0]["rejection_reasons"])
        assert any("jointure externe insuffisante" in reason.lower() for reason in xg_entries[0]["rejection_reasons"])

        quality_path.write_text(json.dumps({
            "status": "ok",
            "verdict": "exploitable_rolling_xg",
            "rows": 1900,
            "xg_coverage": 100.0,
            "missing_seasons": [],
            "total_expected_matches": 1900,
            "total_actual_matches": 1900,
            "lab_only": True,
            "can_influence_picks": False,
        }, ensure_ascii=False), encoding="utf-8")
        model_path.write_text(json.dumps({
            "verdict": {
                "promotion_allowed": False,
                "selected_test": {"picks": 1500, "roi": 1.2},
                "governance_note": "CLV absent, observation seulement",
                "rejection_reasons": ["CLV absent"],
                "xg_improves_brier": True,
                "xg_improves_log_loss": True,
                "edge_test_positive": True,
                "sample_test_sufficient": True,
            },
            "comparison": {
                "with_xg": {"brier": 0.20, "log_loss": 0.60},
                "market": {"brier": 0.21, "log_loss": 0.61},
                "delta_brier_xg_vs_market": -0.01,
                "delta_log_loss_xg_vs_market": -0.01,
            },
            "market_baseline": {"test": {"brier": 0.21, "log_loss": 0.61}},
            "models": [{}, {"selected_validation": {"picks": 1000, "roi": 1.0}}],
            "split_config": {"test_from": "2024-01-01"},
        }, ensure_ascii=False), encoding="utf-8")
        xg_clv_absent = benchmark_governance.build_benchmark(
            str(root / "features_absent.csv"),
            db=synthetic_db(),
            xg_quality_path=str(quality_path),
            xg_model_path=str(model_path),
        )
        xg_entry = next(entry for entry in xg_clv_absent["registry"] if entry.get("name") == "understat_epl_2020_2025_rolling_xg_lab")
        assert xg_entry["quality_verdict"] == "exploitable_rolling_xg"
        assert xg_entry["promotion_allowed"] is False
        assert xg_clv_absent["summary"]["robust_candidates"] == 0

        summary_path = root / "reports" / "benchmark_summary.json"
        html_path = root / "reports" / "benchmark_governance.html"
        benchmark_governance.write_summary(benchmark, str(summary_path))
        benchmark_governance.write_html(benchmark, str(html_path))
        assert summary_path.exists()
        assert html_path.exists()
        assert "Gouvernance" in html_path.read_text(encoding="utf-8")

    print("test_benchmark_governance ok")


if __name__ == "__main__":
    main()
