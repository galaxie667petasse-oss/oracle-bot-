import os
import json
import tempfile
from pathlib import Path

from dashboard_builder import build_dashboard
from report_runner import ReportCommand, big5_xg_commands, command_set, run_report, xg_understat_commands


def write_report(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        report_dir = root / "reports" / "oracle_test"
        db_path = root / "oracle_db.json"
        matches_path = root / "MATCHES.csv"
        db_path.write_text("{}", encoding="utf-8")
        matches_path.write_text("date,home,away\n", encoding="utf-8")
        before_db = db_path.read_text(encoding="utf-8")
        before_matches = matches_path.read_text(encoding="utf-8")
        os.environ["DB_FILE"] = str(db_path)

        manifest = run_report([
            ReportCommand("Succes", "success.txt", ["-c", "print('rapport ok')"], timeout=30),
            ReportCommand("Echec volontaire", "failure.txt", ["-c", "import sys; print('erreur test'); sys.exit(2)"], timeout=30),
            ReportCommand("Succes apres erreur", "success_2.txt", ["-c", "print('rapport ok 2')"], timeout=30),
        ], report_dir, Path.cwd())

        assert (root / "reports").exists()
        assert manifest["ok"] == 2
        assert manifest["failed"] == 1
        assert (report_dir / "success.txt").exists()
        assert (report_dir / "failure.txt").exists()
        assert (report_dir / "run_manifest.json").exists()
        assert db_path.read_text(encoding="utf-8") == before_db
        assert matches_path.read_text(encoding="utf-8") == before_matches

        write_report(report_dir / "pricing_report.txt", """
Rapport pricing Oracle Bot
- Records regles: 528066
- Marge moyenne H2H: 0.66% (marches=122915)
- Marge moyenne Over/Under: 1.83% (marches=79660)
- Marge faible (<= 3.00%): n=492342, ROI=-1.4%, profit=-7078.75
- Marge elevee (>= 8.00%): n=66, ROI=-16.3%, profit=-10.77
""")
        write_report(report_dir / "backtest_modern.txt", """
Backtest temporel Oracle Bot
- Records train: 408969 (2015-01-01 -> 2022-12-31)
- Records test: 66140 (2024-01-01 -> 2025-06-01)
Baseline marche brut
- ROI: -1.2%
Totals seulement
- ROI: -2.0%
Conclusion prudente
- Aucune regle jouable
""")
        write_report(report_dir / "favorite_report.txt", """
Rapport favoris H2H Oracle Bot
  - Tous favoris H2H [non confirme]
  - test n=1000, ROI=-2.5%
  - 1.60 <= cote < 1.80 [non confirme]
  - exterieur favori [fragile]
  - elo_diff fort positif [degradation recente]
""")
        write_report(report_dir / "stability_report.txt", "Rapport de stabilite annuelle\n- degradation recente\n- Aucun segment candidat coherent\n")
        write_report(report_dir / "ml_global.txt", """
Rapport ML leger Oracle Bot
- Test 2024+:
  - modele: n=66140, Brier=0.213805, log loss=0.615889
  - marche no-vig: Brier=0.2135, log loss=0.615094
- edge > 0.02: picks=2879, ROI=-5.06%, note=signal invalide
""")
        write_report(report_dir / "external_profile.txt", """
Score utilite Oracle:
  - odds: 5/5
  - xg: 0/5
  - leak_risk: eleve
  - verdict: utiliser comme enrichissement
""")
        write_report(report_dir / "understat_xg_pipeline.txt", """
Understat xG Full Pipeline Quality Gate
- Quality verdict: exploitable_rolling_xg
- Join rate: 97.5%
- Rolling avg3/avg5: 7190 / 7050
- Brier marche/xG: 0.213 / 0.210
- ROI edge test: -0.1
- Promotion allowed: False
- Conclusion: laboratoire seulement
""")
        (report_dir / "understat_epl_2020_2025_quality.json").write_text(json.dumps({
            "verdict": "exploitable_rolling_xg",
            "seasons_detected": ["2020-2021", "2021-2022", "2022-2023", "2023-2024", "2024-2025"],
            "missing_seasons": [],
            "total_expected_matches": 1900,
            "total_actual_matches": 1900,
            "xg_coverage": 100.0,
        }, ensure_ascii=False), encoding="utf-8")
        (report_dir / "understat_epl_2020_2025_xg_model.json").write_text(json.dumps({
            "market_baseline": {"test": {"brier": 0.213, "log_loss": 0.615}},
            "comparison": {"with_xg": {"brier": 0.210, "log_loss": 0.607}},
            "verdict": {
                "selected_test": {"roi": -0.1},
                "promotion_allowed": False,
                "rejection_reasons": ["ROI test negatif", "CLV absent"],
            },
        }, ensure_ascii=False), encoding="utf-8")
        (report_dir / "big5_xg_summary.json").write_text(json.dumps({
            "global": {
                "leagues_available": 3,
                "leagues_exploitable": 3,
                "leagues_roi_edge_positive": 2,
                "leagues_sample_ge_1000": 0,
                "leagues_clv_available": 0,
                "robust_candidates": 0,
                "conclusion": "CLV absente: observations seulement.",
            },
            "leagues": [
                {"league": "Bundesliga", "dataset_present": True, "market_brier": 0.210108, "xg_brier": 0.210036, "market_log_loss": 0.608061, "xg_log_loss": 0.607923, "roi_edge_test": 2.33, "sample_edge_test": 264, "status": "watchlist maximum"}
            ],
        }, ensure_ascii=False), encoding="utf-8")
        (report_dir / "clv_readiness.json").write_text(json.dumps({
            "status": "indisponible",
            "clv_calculable": False,
            "missing_columns": ["C_LTH", "C_LTA"],
            "markets": {"h2h_closing_possible": False},
        }, ensure_ascii=False), encoding="utf-8")

        summary = build_dashboard(report_dir)
        html = (report_dir / "index.html").read_text(encoding="utf-8")
        assert (report_dir / "summary.json").exists()
        assert "Backtest" in html
        assert "Pricing" in html
        assert "Favorite Report" in html
        assert "Stability" in html
        assert "ML" in html
        assert "External Dataset Lab" in html
        assert summary["records_count"] == 528066
        assert summary["pricing_low_margin_roi"] == -1.4
        assert summary["ml_global_brier_test"] == 0.213805
        assert any(command.name == "CLV analysis" for command in command_set("statistical"))
        assert any(command.name == "Benchmark governance" for command in command_set("full"))
        assert any(command.name == "Understat xG Full Pipeline Quality Gate" for command in command_set("xg-understat"))
        assert any(command.name == "Big 5 xG aggregator" for command in command_set("big5-xg"))
        dry_commands = xg_understat_commands("external.csv", "features.csv", "prefix", skip_benchmark=True, skip_model=True, dry_run=True)
        assert "--dry-run" in dry_commands[0].args
        assert "--skip-benchmark" in dry_commands[0].args
        big5_commands = big5_xg_commands("features.csv", skip_benchmark=True)
        assert any("multi_league_xg_aggregator.py" in command.args for command in big5_commands)
        assert not any("benchmark_governance.py" in command.args for command in big5_commands)
        assert "CLV / Closing Line Value" in html
        assert "CLV Readiness" in html
        assert "Validation statistique" in html
        assert "Understat xG Multi-Season Lab" in html
        assert "Big 5 xG Lab Summary" in html
        assert "League-by-league xG comparison" in html
        assert "Promotion blockers" in html
        assert "aucun pick automatique" in html.lower()

        absent_manifest = run_report(
            xg_understat_commands(str(root / "absent.csv"), str(root / "features_absent.csv"), "absent_test", dry_run=True),
            root / "reports" / "oracle_absent",
            Path.cwd(),
        )
        assert absent_manifest["failed"] == 1
        assert db_path.read_text(encoding="utf-8") == before_db

    print("test_report_runner ok")


if __name__ == "__main__":
    main()
