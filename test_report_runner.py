import os
import json
import tempfile
from pathlib import Path

from dashboard_builder import build_dashboard
from report_runner import ReportCommand, api_odds_commands, big5_xg_commands, closing_preview_commands, closing_readiness_commands, command_set, daily_ops_commands, daily_shadow_commands, free_historical_commands, matchday_commands, odds_intake_commands, odds_lab_commands, ops_commands, project_blueprint_commands, proof_commands, run_report, same_day_commands, shadow_commands, shadow_ops_commands, source_coverage_commands, subscription_commands, xg_understat_commands


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
                "total_leagues_expected": 5,
                "total_leagues_available": 3,
                "missing_leagues": ["SerieA", "Ligue1"],
                "ready_for_big5_conclusion": False,
                "clv_blocker": True,
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
            "clv_calculable_now": False,
            "clv_calculable_after_enrichment": True,
            "clv_calculable_in_preview": True,
            "clv_scope": "partial_h2h_home_away",
            "preview": {"rows_with_clv": 2, "coverage": 50.0, "covered_market_sides": ["h2h_home", "h2h_away"], "uncovered_market_sides": ["h2h_draw", "total_over"]},
            "source_has_closing": True,
            "missing_columns": ["C_LTH", "C_LTA"],
            "markets": {"h2h_closing_possible": False},
            "recommended_next_command": "python features_closing_enricher.py --features data/features_modern.csv --source data/MATCHES.csv --output reports/features_with_closing_preview.csv",
        }, ensure_ascii=False), encoding="utf-8")
        (report_dir / "closing_odds_probe.json").write_text(json.dumps({
            "closing_available": True,
            "h2h_closing_available": "partial",
            "total_closing_available": "none",
            "btts_closing_available": "none",
            "detected_columns": {"all_closing": ["C_LTH", "C_LTD", "C_LTA"]},
        }, ensure_ascii=False), encoding="utf-8")
        write_report(report_dir / "closing_odds_probe.txt", "Closing Odds Probe\n- H2H closing disponible: True\n- Colonnes closing detectees: C_LTH, C_LTD, C_LTA\n")
        (report_dir / "clv_partial_report.json").write_text(json.dumps({
            "status": "partiel",
            "clv_scope": "partial_h2h_home_away",
            "coverage_global": 50.0,
            "covered_market_sides": ["h2h_home", "h2h_away"],
            "excluded_market_sides": ["h2h_draw", "total_over"],
            "rows_with_closing": 2,
            "summary": {"n": 2, "clv_mean": 0.01, "clv_positive_rate": 50.0},
        }, ensure_ascii=False), encoding="utf-8")
        write_report(report_dir / "clv_partial_report.txt", "Rapport CLV Oracle Bot\n- Scope CLV: partial_h2h_home_away\n- Coverage global: 50.0%\n- CLV moyenne: 0.01\n")
        (report_dir / "shadow_clv_report.json").write_text(json.dumps({
            "signals_total": 3,
            "signals_with_closing": 2,
            "pending_closing": 1,
            "pending_results": 1,
            "clv_coverage": 66.67,
            "clv_mean": 0.01,
            "clv_positive_rate": 50.0,
            "roi": -1.0,
            "profit": -0.2,
            "drawdown": -1.0,
            "sample_size": 3,
            "verdict": "not_validated",
            "clv_by_strategy": {"s1": {"n": 2}},
            "clv_by_league": {"EPL": {"n": 2}},
            "warnings": ["sample <1000: promotion impossible"],
        }, ensure_ascii=False), encoding="utf-8")
        write_report(report_dir / "shadow_clv_report.txt", "Shadow CLV Report\n- Signaux shadow: 3\n- Coverage CLV: 66.67%\n- Verdict: not_validated\n")
        (report_dir / "shadow_quality_audit.json").write_text(json.dumps({
            "verdict": "usable_with_warnings",
            "rows": 3,
            "clv_coverage": 66.67,
            "result_coverage": 50.0,
            "blocking_errors": [],
            "warnings": ["Closing odds manquantes: 1"],
        }, ensure_ascii=False), encoding="utf-8")
        write_report(report_dir / "shadow_quality_audit.txt", "Shadow Quality Audit\n- Verdict: usable_with_warnings\n- Coverage CLV: 66.67%\n")
        (report_dir / "evidence_gate.json").write_text(json.dumps({
            "global_status": "insufficient_evidence",
            "blockers": ["sample shadow < 1000"],
            "strengths": ["Shadow workflow pret"],
            "required_next_steps": ["collecter observations"],
        }, ensure_ascii=False), encoding="utf-8")
        write_report(report_dir / "evidence_gate.txt", "Evidence Gate\n- Statut global: insufficient_evidence\n- Bloquant: sample shadow < 1000\n")
        (report_dir / "sample_size_plan.json").write_text(json.dumps({
            "current_sample": 3,
            "target_edge_required_sample": 38416,
            "edge_sample_requirements": {"1.0%": 38416},
        }, ensure_ascii=False), encoding="utf-8")
        write_report(report_dir / "sample_size_plan.txt", "Sample Size Planner\n- Sample actuel: 3\n- Edge 1.0%: sample approx 38416\n")
        write_report(report_dir / "oracle_ops_health.txt", "Oracle Operations Center - Health\n- Statut: OK\n- OK: Telegram non appele par ops\n")
        write_report(report_dir / "shadow_messages_preview.txt", "Oracle Shadow Mode\nStatut: observation seulement\nRappel: aucune mise conseillee\n")
        (report_dir / "odds_snapshot_summary.json").write_text(json.dumps({
            "rows_total": 3,
            "invalid_rows": 1,
            "near_close_rows": 1,
            "sources": ["manual_csv"],
            "bookmakers": ["Book"],
            "leagues": ["EPL"],
            "markets": ["h2h"],
            "duplicates": 0,
        }, ensure_ascii=False), encoding="utf-8")
        (report_dir / "odds_source_quality.json").write_text(json.dumps({
            "rows_total": 3,
            "valid_rows": 2,
            "invalid_rows": 1,
            "sources": {"manual_csv": 2},
            "bookmakers": {"Book": 2},
            "leagues": {"EPL": 2},
            "markets": {"h2h": 2},
            "near_close_rows": 1,
            "near_close_coverage": 50.0,
            "clv_capacity": "partial",
            "markets_covered": {"h2h": True, "total": False, "btts": False},
            "recommendations": ["besoin near-close"],
        }, ensure_ascii=False), encoding="utf-8")
        (report_dir / "odds_to_shadow_report.json").write_text(json.dumps({
            "rows_added": 2,
            "dry_run": True,
        }, ensure_ascii=False), encoding="utf-8")
        (report_dir / "odds_closing_matcher_report.json").write_text(json.dumps({
            "matches_found": 1,
            "closing_updated": 0,
        }, ensure_ascii=False), encoding="utf-8")
        (report_dir / "odds_intake_audit.json").write_text(json.dumps({
            "taken_snapshots": 2,
            "near_close_snapshots": 1,
            "valid_odds": 3,
            "invalid_odds": 0,
            "shadow_linked_to_snapshots": 1,
            "closing_coverage_possible": 50.0,
            "closing_coverage_real": 0.0,
            "verdict": "shadow_started",
            "recommendations": ["matcher near-close"],
        }, ensure_ascii=False), encoding="utf-8")
        write_report(report_dir / "odds_source_config.txt", "Configuration sources de cotes Oracle\n- Validation: OK\n")
        write_report(report_dir / "odds_snapshot_store.txt", "Resume snapshots de cotes Oracle\n- Lignes totales: 3\n")
        write_report(report_dir / "odds_source_quality.txt", "Qualite des sources de cotes Oracle\n- Capacite CLV: partial\n")
        write_report(report_dir / "odds_intake_audit.txt", "Audit intake odds Oracle\n- Verdict: shadow_started\n")
        (report_dir / "soccer_odds_sport_scan.json").write_text(json.dumps({
            "active_sports": 1,
            "high_priority": ["soccer_japan_j_league"],
            "sports": [{"sport_key": "soccer_japan_j_league", "normalized_rows": 6}],
        }, ensure_ascii=False), encoding="utf-8")
        (report_dir / "shadow_selection_summary.json").write_text(json.dumps({
            "selected_rows": 2,
            "distinct_events": 2,
            "warnings": [],
        }, ensure_ascii=False), encoding="utf-8")
        (report_dir / "near_close_plan.json").write_text(json.dumps({
            "pending_closing_count": 2,
            "next_match_date": "2026-06-01",
            "commands": ["python the_odds_api_adapter.py --allow-network --sport soccer_japan_j_league --near-close"],
        }, ensure_ascii=False), encoding="utf-8")
        (report_dir / "event_lifecycle.json").write_text(json.dumps({
            "total_observations": 3,
            "pending_closing": 2,
            "pending_results": 1,
            "completed": 0,
            "status_counts": {"pre_match_waiting_close": 2, "waiting_result": 1},
        }, ensure_ascii=False), encoding="utf-8")
        (report_dir / "near_close_schedule.json").write_text(json.dumps({
            "pending_total": 2,
            "schedule": [{"league": "J League", "pending_count": 2, "sport_key": "soccer_japan_j_league"}],
        }, ensure_ascii=False), encoding="utf-8")
        (report_dir / "shadow_progress_dashboard.json").write_text(json.dumps({
            "observations": 3,
            "clv_coverage": 0.0,
            "roi_coverage": 0.0,
        }, ensure_ascii=False), encoding="utf-8")
        (report_dir / "odds_autopilot_dryrun.json").write_text(json.dumps({
            "recommended_human_action": "collecter near-close",
            "safe_next_commands": ["python near_close_scheduler.py --ledger reports/shadow_ledger.csv --commands"],
            "blocked_actions": ["appel reseau automatique"],
        }, ensure_ascii=False), encoding="utf-8")
        (report_dir / "architecture_map.json").write_text(json.dumps({"blocks": [{"name": "Sources de donnees"}]}, ensure_ascii=False), encoding="utf-8")
        (report_dir / "pipeline_contracts.json").write_text(json.dumps({"contracts": {"odds_snapshot": {}, "shadow_ledger": {}}}, ensure_ascii=False), encoding="utf-8")
        (report_dir / "project_scorecard.json").write_text(json.dumps({
            "global_score": 70,
            "scores": {"preuve betting reelle": {"score": 20}},
        }, ensure_ascii=False), encoding="utf-8")
        (report_dir / "real_observation_guard.json").write_text(json.dumps({
            "verdict": "needs_review",
            "blockers": ["taken sans near-close"],
            "warnings": ["verification humaine"],
            "near_close_without_taken_count": 0,
            "taken_without_near_close_count": 1,
        }, ensure_ascii=False), encoding="utf-8")
        (report_dir / "matchday_status.json").write_text(json.dumps({
            "date": "2026-06-01",
            "phase_detected": "pre_match_ready",
            "taken": {"filled": 2},
            "near_close": {"filled": 1},
            "results": {"filled": 0},
            "warnings": ["resultats manquants"],
            "next_actions": ["collecter near-close"],
        }, ensure_ascii=False), encoding="utf-8")
        write_report(report_dir / "architecture_map.txt", "Architecture canonique\n- Sources de donnees\n- LLM analyste\n")
        write_report(report_dir / "pipeline_contracts.txt", "Contrats disponibles\n- odds_snapshot\n- shadow_ledger\n")
        write_report(report_dir / "llm_analyst_contract.txt", "Contrat LLM analyste\n- Le LLM n'est pas source de verite\n")
        write_report(report_dir / "restitution_schema.txt", "Restitution Oracle\nDecision: non valide\n")
        write_report(report_dir / "progress_loop.txt", "Resume boucle de progression\nentries: 0\n")
        write_report(report_dir / "project_scorecard.txt", "Scorecard projet Oracle\n- Score global: 70\n- Preuve betting reelle: 20\n")
        write_report(report_dir / "agent_orchestrator_dryrun.txt", "Agent orchestrator dry-run Oracle\n- Dry-run uniquement\n")
        write_report(report_dir / "real_observation_guard.txt", "Real Observation Guard Oracle\n- Verdict: needs_review\n")
        write_report(report_dir / "matchday_status.txt", "Status matchday pack Oracle\n- taken: 2\n")
        (report_dir / "api_football_same_day_2026_06_04").mkdir(parents=True, exist_ok=True)
        (report_dir / "api_football_same_day_2026_06_04" / "summary.json").write_text(json.dumps({
            "fixtures": 1,
            "odds_valid": 2,
            "selection_rows": 1,
            "would_add_or_added": 1,
        }, ensure_ascii=False), encoding="utf-8")
        (report_dir / "near_close_today.json").write_text(json.dumps({
            "pending_today": 1,
            "manual_fallback": True,
            "commands": ["python api_football_odds_adapter.py --fixture-id 1 --allow-network"],
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
        assert any(command.name == "Closing odds probe" for command in command_set("closing-readiness"))
        assert any(command.name == "CLV partial analysis" for command in command_set("closing-preview"))
        assert any(command.name == "Shadow CLV report" for command in command_set("shadow"))
        assert any(command.name == "Shadow workflow init" for command in command_set("daily-shadow"))
        assert any(command.name == "Oracle ops health" for command in command_set("ops"))
        assert any(command.name == "Odds source config" for command in command_set("odds-lab"))
        assert any(command.name == "Odds intake audit" for command in command_set("odds-intake"))
        assert any(command.name == "Soccer odds sport scanner" for command in command_set("api-odds"))
        assert any(command.name == "Event lifecycle" for command in command_set("shadow-ops"))
        assert any(command.name == "Source coverage report" for command in command_set("source-coverage"))
        assert any(command.name == "Architecture canonique" for command in command_set("project-blueprint"))
        assert any(command.name == "Matchday status" for command in command_set("matchday"))
        assert any(command.name == "Proof dashboard" for command in command_set("proof"))
        assert any(command.name == "Daily operations full dry-run" for command in command_set("daily-ops"))
        assert any(command.name == "Data subscription evaluator" for command in command_set("subscription"))
        assert any(command.name == "Football-Data free importer" for command in command_set("free-historical"))
        dry_commands = xg_understat_commands("external.csv", "features.csv", "prefix", skip_benchmark=True, skip_model=True, dry_run=True)
        assert "--dry-run" in dry_commands[0].args
        assert "--skip-benchmark" in dry_commands[0].args
        big5_commands = big5_xg_commands("features.csv", skip_benchmark=True)
        assert any("multi_league_xg_aggregator.py" in command.args for command in big5_commands)
        assert not any("benchmark_governance.py" in command.args for command in big5_commands)
        closing_commands = closing_readiness_commands("features.csv", "matches.csv", skip_benchmark=False)
        assert any("closing_odds_probe.py" in command.args for command in closing_commands)
        assert any("--closing-probe" in command.args for command in closing_commands)
        assert any("benchmark_governance.py" in command.args for command in closing_commands)
        preview_commands = closing_preview_commands("features.csv", "matches.csv", str(root / "reports" / "preview.csv"), skip_benchmark=True)
        assert any("features_closing_enricher.py" in command.args for command in preview_commands)
        assert not any("benchmark_governance.py" in command.args for command in preview_commands)
        shadow_cmds = shadow_commands(str(root / "reports" / "shadow_ledger.csv"), "features.csv", skip_benchmark=False)
        assert any("shadow_clv_report.py" in command.args for command in shadow_cmds)
        assert any("--shadow-report" in command.args for command in shadow_cmds)
        assert any("dashboard_builder.py" in command.args for command in shadow_cmds)
        daily_cmds = daily_shadow_commands(str(root / "reports" / "shadow_ledger.csv"), "features.csv", skip_benchmark=True, skip_dashboard=True)
        assert any("shadow_workflow.py" in command.args for command in daily_cmds)
        assert any("--summary-csv" in command.args for command in daily_cmds)
        assert not any("benchmark_governance.py" in command.args for command in daily_cmds)
        assert not any("dashboard_builder.py" in command.args for command in daily_cmds)
        ops_cmds = ops_commands(str(root / "reports" / "shadow_ledger.csv"), skip_evidence=False, skip_quality=False, skip_sample_plan=False, skip_dashboard=True)
        assert any("oracle_ops.py" in command.args for command in ops_cmds)
        assert any("shadow_quality_audit.py" in command.args for command in ops_cmds)
        assert any("evidence_gate.py" in command.args for command in ops_cmds)
        assert any("sample_size_planner.py" in command.args for command in ops_cmds)
        assert not any("dashboard_builder.py" in command.args for command in ops_cmds)
        odds_cmds = odds_lab_commands(str(root / "reports" / "shadow_ledger.csv"), str(root / "reports" / "odds_snapshots.csv"), skip_evidence=True, skip_quality=False, skip_dashboard=True)
        assert any("odds_source_config.py" in command.args for command in odds_cmds)
        assert any("odds_source_quality_report.py" in command.args for command in odds_cmds)
        assert not any("dashboard_builder.py" in command.args for command in odds_cmds)
        intake_cmds = odds_intake_commands(str(root / "reports" / "shadow_ledger.csv"), str(root / "reports" / "odds_snapshots.csv"), skip_evidence=True, skip_quality=True, skip_dashboard=True)
        assert any("odds_intake_audit.py" in command.args for command in intake_cmds)
        assert not any("dashboard_builder.py" in command.args for command in intake_cmds)
        api_cmds = api_odds_commands(str(root / "reports" / "shadow_ledger.csv"), str(root / "reports" / "odds_snapshots.csv"), skip_dashboard=True)
        assert any("soccer_odds_sport_scanner.py" in command.args for command in api_cmds)
        assert any("near_close_workflow.py" in command.args for command in api_cmds)
        assert any("real_observation_guard.py" in command.args and "--scope" in command.args for command in api_cmds)
        assert not any("dashboard_builder.py" in command.args for command in api_cmds)
        shadow_ops_cmds = shadow_ops_commands(str(root / "reports" / "shadow_ledger.csv"), str(root / "reports" / "odds_snapshots.csv"), skip_dashboard=True)
        assert any("event_lifecycle_manager.py" in command.args for command in shadow_ops_cmds)
        assert any("near_close_scheduler.py" in command.args for command in shadow_ops_cmds)
        assert any("evidence_gate.py" in command.args and "--lifecycle" in command.args for command in shadow_ops_cmds)
        assert not any("dashboard_builder.py" in command.args for command in shadow_ops_cmds)
        source_cmds = source_coverage_commands(skip_dashboard=True)
        assert any(command.name == "The Odds API active sports dry-run" for command in source_cmds)
        assert any("source_coverage_report.py" in command.args for command in source_cmds)
        assert not any("dashboard_builder.py" in command.args for command in source_cmds)
        blueprint_cmds = project_blueprint_commands(skip_evidence=True, skip_dashboard=True)
        assert any("oracle_architecture_map.py" in command.args for command in blueprint_cmds)
        assert any("pipeline_contracts.py" in command.args for command in blueprint_cmds)
        assert not any("dashboard_builder.py" in command.args for command in blueprint_cmds)
        matchday_cmds = matchday_commands(str(root / "reports" / "matchday_2026_06_01"), str(root / "reports" / "shadow_ledger.csv"), str(root / "reports" / "odds_snapshots.csv"), phase="pre_match", skip_dashboard=True)
        assert any("matchday_status_report.py" in command.args for command in matchday_cmds)
        assert any("matchday_runner.py" in command.args and "--phase" in command.args for command in matchday_cmds)
        assert any("real_observation_guard.py" in command.args for command in matchday_cmds)
        assert any("evidence_gate.py" in command.args for command in matchday_cmds)
        assert not any("dashboard_builder.py" in command.args for command in matchday_cmds)
        proof_cmds = proof_commands(str(root / "reports" / "shadow_ledger.csv"), str(root / "reports" / "odds_snapshots.csv"), historical_clv=str(root / "reports" / "historical_clv.csv"), skip_dashboard=True)
        assert any("external_evidence_catalog.py" in command.args for command in proof_cmds)
        assert any("near_close_batch_runner.py" in command.args for command in proof_cmds)
        assert any("historical_clv_backtester.py" in command.args for command in proof_cmds)
        assert any("proof_dashboard.py" in command.args for command in proof_cmds)
        assert not any("dashboard_builder.py" in command.args for command in proof_cmds)
        same_cmds = same_day_commands(str(root / "reports" / "shadow_ledger.csv"), date="2026-06-04", skip_dashboard=True)
        assert any("api_football_same_day_runner.py" in command.args and "--dry-run" in command.args for command in same_cmds)
        assert any("api_football_odds_debug_report.py" in command.args for command in same_cmds)
        assert any("near_close_today_helper.py" in command.args for command in same_cmds)
        assert any("source_coverage_report.py" in command.args and "--same-day-summary" in command.args for command in same_cmds)
        assert any("proof_dashboard.py" in command.args and "--same-day" in command.args for command in same_cmds)
        assert not any("dashboard_builder.py" in command.args for command in same_cmds)
        daily_ops_cmds = daily_ops_commands(str(root / "reports" / "shadow_ledger.csv"), date="2026-06-05", skip_dashboard=True)
        assert any("daily_operations_runner.py" in command.args and "--full-dry-run" in command.args for command in daily_ops_cmds)
        assert any("evidence_gate.py" in command.args and "--near-close-window" in command.args for command in daily_ops_cmds)
        subscription_cmds = subscription_commands(skip_dashboard=True)
        assert any("data_subscription_evaluator.py" in command.args for command in subscription_cmds)
        free_cmds = free_historical_commands(str(root / "E0.csv"), skip_dashboard=True)
        assert any("football_data_free_importer.py" in command.args for command in free_cmds)
        same_manifest = run_report(
            same_day_commands(str(root / "reports" / "shadow_ledger.csv"), date="2026-06-04", skip_dashboard=True),
            root / "reports" / "same_day_manifest",
            Path.cwd(),
        )
        assert same_manifest["failed"] == 0
        try:
            closing_preview_commands("features.csv", "matches.csv", str(root / "data" / "preview.csv"))
            raise AssertionError("preview data non bloquee")
        except ValueError as exc:
            assert "data" in str(exc)
        assert "CLV / Closing Line Value" in html
        assert "CLV Readiness" in html
        assert "Validation statistique" in html
        assert "Understat xG Multi-Season Lab" in html
        assert "Big 5 xG Lab Summary" in html
        assert "Big 5 Completion Status" in html
        assert "League-by-league xG comparison" in html
        assert "League readiness table" in html
        assert "Closing Odds Recovery Plan" in html
        assert "CLV partielle / Closing odds" in html
        assert "Shadow Mode Evidence" in html
        assert "Operations Health" in html
        assert "Shadow Quality Audit" in html
        assert "Evidence Gate" in html
        assert "Evidence Acceleration / Proof Loop" in html
        assert "Sample Size Plan" in html
        assert "Shadow Message Preview" in html
        assert "Manual Workflow Checklist" in html
        assert "Odds Source Lab" in html
        assert "Odds Snapshot Coverage" in html
        assert "Near-Close Coverage" in html
        assert "Odds to Shadow Intake" in html
        assert "Closing Matcher Status" in html
        assert "Source Quality" in html
        assert "Odds Intake Workflow" in html
        assert "Soccer Odds API Availability" in html
        assert "API Shadow Selection" in html
        assert "Near-Close Pending Plan" in html
        assert "Real Guard Ledger Scope" in html
        assert "Event Lifecycle" in html
        assert "Near-Close Schedule" in html
        assert "Shadow Progress" in html
        assert "Result Capture Status" in html
        assert "Autopilot Recommendations" in html
        assert "Architecture canonique" in html
        assert "Pipeline contracts" in html
        assert "LLM analyst contract" in html
        assert "Restitution schema" in html
        assert "Progress loop" in html
        assert "Project scorecard" in html
        assert "Agent dry-run" in html
        assert "Next actions" in html
        assert "Real Matchday Collection" in html
        assert "Matchday Phase" in html
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
