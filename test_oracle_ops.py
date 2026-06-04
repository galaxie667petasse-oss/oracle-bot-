import tempfile
from pathlib import Path

import oracle_ops
import odds_snapshot_store
import shadow_ledger


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".gitignore").write_text("reports/\nexternal_data/\n", encoding="utf-8")
        (root / "data").mkdir()
        features = root / "data" / "features_modern.csv"
        matches = root / "data" / "MATCHES.csv"
        features.write_text("date,home,away\n", encoding="utf-8")
        matches.write_text("date,home,away\n", encoding="utf-8")
        for module in oracle_ops.KEY_MODULES:
            (root / module).write_text("# module test\n", encoding="utf-8")
        ledger = root / "reports" / "shadow_ledger.csv"
        shadow_ledger.add_shadow_entry(str(ledger), match_date="2026-06-01", league="EPL", home="A", away="B", market="h2h", side="home", taken_odds="2.10")
        before_features = features.read_text(encoding="utf-8")
        before_matches = matches.read_text(encoding="utf-8")

        health = oracle_ops.build_health(root, str(ledger.relative_to(root)))
        assert health["status"] == "OK"
        daily = oracle_ops.daily_checklist("2026-06-01")
        assert len(daily["checklist"]) >= 6

        templates = oracle_ops.shadow_templates(str(ledger), str(root / "reports"))
        assert Path(templates["candidates"]).exists()
        full = oracle_ops.full_local(str(ledger), str(root / "reports"), skip_benchmark=True, skip_dashboard=True)
        assert full["shadow_summary"]["signals_total"] == 1
        assert full["quality"]["verdict"] in {"usable_with_warnings", "clean"}
        assert full["evidence"]["global_status"] in {"insufficient_evidence", "blocked", "promising_but_unvalidated"}
        assert full["optional"] == []
        odds_store = root / "reports" / "odds_snapshots.csv"
        odds_snapshot_store.append_snapshot_rows(str(odds_store), [{
            "captured_at": "2026-06-01T09:00:00",
            "source": "the_odds_api",
            "league": "J League",
            "match_date": "2026-06-01",
            "kickoff_time": "2026-06-01T10:00:00",
            "home_team": "A",
            "away_team": "B",
            "bookmaker": "Book",
            "market_type": "h2h",
            "side": "home",
            "odds": "2.10",
        }])
        odds_lab = oracle_ops.odds_lab(str(root / "reports"), str(odds_store))
        assert odds_lab["summary"]["rows_total"] == 1
        assert Path(odds_lab["template"]["manual_odds_template"]).exists()
        assert oracle_ops.odds_summary(str(odds_store))["rows_total"] == 1
        assert oracle_ops.odds_config_report()["config_ok"] is True
        status = oracle_ops.odds_wizard_status(str(odds_store), str(ledger), str(root / "reports"))
        assert status["snapshots_total"] == 1
        intake = oracle_ops.odds_intake_audit_report(str(root / "reports"), str(odds_store), str(ledger))
        assert intake["verdict"] in {"shadow_started", "no_data", "snapshots_only"}
        architecture = oracle_ops.architecture_report(str(root / "reports"))
        assert len(architecture["blocks"]) == 7
        scorecard = oracle_ops.scorecard_report(str(root / "reports"))
        assert scorecard["global_score"] > 0
        contracts = oracle_ops.contracts_report(str(root / "reports"))
        assert contracts["ok"]
        llm = oracle_ops.llm_contract_report(str(root / "reports"))
        assert llm["ok"]
        agent = oracle_ops.agent_dryrun_report(str(root / "reports"))
        assert agent["ok"]
        project_map = oracle_ops.project_map_report(str(root / "reports"), skip_dashboard=True)
        assert project_map["architecture_blocks"] == 7
        real_start = oracle_ops.real_start_report(str(root / "reports"), str(ledger), str(odds_store))
        assert "guard" in real_start
        api_status = oracle_ops.api_odds_status_report(str(root / "reports"), str(ledger), str(odds_store))
        assert api_status["odds_summary"]["rows_total"] == 1
        assert api_status["near_close"]["pending_closing_count"] == 1
        soccer_scan = oracle_ops.scan_soccer_sports(allow_network=False, dry_run=True)
        assert soccer_scan["active_sports"] == 0
        near_next = oracle_ops.near_close_suggest_commands(str(ledger))
        assert near_next["commands"]
        guard_ledger = oracle_ops.real_guard_ledger_report(str(root / "reports"), str(ledger), str(odds_store))
        assert guard_ledger["scope"] == "ledger"
        lifecycle = oracle_ops.lifecycle_report(str(root / "reports"), str(ledger))
        assert lifecycle["total_observations"] == 1
        schedule = oracle_ops.near_close_schedule_report(str(root / "reports"), str(ledger))
        assert schedule["pending_total"] == 1
        results_template = oracle_ops.results_template_report(str(root / "reports"), str(ledger))
        assert Path(results_template["template"]).exists()
        progress_shadow = oracle_ops.shadow_progress_report(str(root / "reports"), str(ledger))
        assert progress_shadow["observations"] == 1
        autopilot = oracle_ops.odds_autopilot_report(str(root / "reports"), str(ledger), str(odds_store))
        assert autopilot["safe_next_commands"]
        active = oracle_ops.active_soccer_sports_report(str(root / "reports"))
        assert active["dry_run"] is True
        coverage = oracle_ops.source_coverage_ops_report(str(root / "reports"))
        assert "source_recommendations" in coverage
        fixtures_report = oracle_ops.api_football_fixtures_ops_report(str(root / "reports"), "2026-06-03")
        assert fixtures_report["dry_run"] is True
        matchday_probe = oracle_ops.api_football_matchday_ops_report(str(root / "reports"), "2026-06-03")
        assert matchday_probe["total_fixtures"] == 0
        betclic_template = oracle_ops.manual_betclic_template_report(str(root / "reports"), "2026-06-03")
        assert Path(betclic_template["template"]).exists()
        catalog = oracle_ops.external_catalog_report(str(root / "reports"))
        assert catalog["summary"]["sources_count"] >= 5
        historical_file = root / "reports" / "historical_clv.csv"
        historical_file.write_text("match_date,league,home_team,away_team,bookmaker,market_type,side,opening_odds,closing_odds,clv_percent,result,profit_unit,source_row,is_valid,validation_reason\n2024-01-01,EPL,A,B,Book,h2h,home,2.0,1.9,0.052631,home,1.0,2,True,\n", encoding="utf-8")
        historical = oracle_ops.historical_clv_ops_report(str(root / "reports"), str(historical_file))
        assert historical["summary"]["sample"] == 1
        near_batch = oracle_ops.near_close_batch_ops_report(str(root / "reports"), str(ledger), str(odds_store), dry_run=True)
        assert near_batch["network_allowed"] is False
        proof = oracle_ops.proof_dashboard_report(str(root / "reports"))
        assert "global_status" in proof
        acceleration = oracle_ops.evidence_acceleration_report(str(root / "reports"), str(ledger), str(odds_store), historical_clv=str(historical_file))
        assert acceleration["lab_only"] is True
        same_day = oracle_ops.api_football_same_day_ops_report(str(root / "reports"), "2026-06-04", str(ledger))
        assert same_day["allow_network"] is False
        assert same_day["odds_valid"] == 0
        same_day_debug_missing = oracle_ops.api_football_same_day_debug_ops_report(str(root / "reports"), date="2026-06-04")
        assert same_day_debug_missing["available"] is False
        same_day_odds = root / "reports" / "api_football_same_day_2026_06_04" / "odds_enriched.csv"
        same_day_debug = oracle_ops.api_football_same_day_debug_ops_report(str(root / "reports"), odds=str(same_day_odds), date="2026-06-04")
        assert same_day_debug["available"] is True
        valid_odds = oracle_ops.api_football_valid_odds_ops_report(str(root / "reports"), str(odds_store))
        assert valid_odds["rows_read"] == 1
        near_today = oracle_ops.near_close_today_ops_report(str(root / "reports"), str(ledger), str(root / "missing_sport_map.json"), "2026-06-01")
        assert near_today["pending_today"] == 1
        assert oracle_ops.main(["--api-pre-match-jleague", "--ledger", str(ledger), "--snapshots", str(odds_store), "--reports-dir", str(root / "reports")]) == 0
        assert oracle_ops.main(["--lifecycle", "--ledger", str(ledger), "--reports-dir", str(root / "reports")]) == 0
        assert oracle_ops.main(["--near-close-schedule", "--ledger", str(ledger), "--reports-dir", str(root / "reports")]) == 0
        assert oracle_ops.main(["--results-template", "--ledger", str(ledger), "--reports-dir", str(root / "reports")]) == 0
        assert oracle_ops.main(["--shadow-progress", "--ledger", str(ledger), "--reports-dir", str(root / "reports")]) == 0
        assert oracle_ops.main(["--odds-autopilot", "--ledger", str(ledger), "--snapshots", str(odds_store), "--reports-dir", str(root / "reports")]) == 0
        assert oracle_ops.main(["--active-soccer-sports", "--reports-dir", str(root / "reports")]) == 0
        assert oracle_ops.main(["--source-coverage", "--reports-dir", str(root / "reports")]) == 0
        assert oracle_ops.main(["--api-football-fixtures", "--date", "2026-06-03", "--reports-dir", str(root / "reports")]) == 0
        assert oracle_ops.main(["--api-football-matchday", "--date", "2026-06-03", "--reports-dir", str(root / "reports")]) == 0
        assert oracle_ops.main(["--manual-betclic-template", "--date", "2026-06-03", "--reports-dir", str(root / "reports")]) == 0
        assert oracle_ops.main(["--external-evidence-catalog", "--reports-dir", str(root / "reports")]) == 0
        assert oracle_ops.main(["--historical-clv", "--historical-clv-file", str(historical_file), "--reports-dir", str(root / "reports")]) == 0
        assert oracle_ops.main(["--near-close-batch", "--ledger", str(ledger), "--snapshots", str(odds_store), "--reports-dir", str(root / "reports")]) == 0
        assert oracle_ops.main(["--proof-dashboard", "--reports-dir", str(root / "reports")]) == 0
        assert oracle_ops.main(["--evidence-acceleration", "--ledger", str(ledger), "--snapshots", str(odds_store), "--historical-clv-file", str(historical_file), "--reports-dir", str(root / "reports")]) == 0
        assert oracle_ops.main(["--api-football-results", "--date", "2026-06-03", "--reports-dir", str(root / "reports")]) == 0
        assert oracle_ops.main(["--api-football-same-day", "--date", "2026-06-04", "--ledger", str(ledger), "--reports-dir", str(root / "reports")]) == 0
        assert oracle_ops.main(["--api-football-same-day-debug", "--date", "2026-06-04", "--odds-csv", str(same_day_odds), "--reports-dir", str(root / "reports")]) == 0
        assert oracle_ops.main(["--api-football-valid-odds", "--odds-csv", str(odds_store), "--reports-dir", str(root / "reports")]) == 0
        assert oracle_ops.main(["--near-close-today", "--date", "2026-06-01", "--ledger", str(ledger), "--reports-dir", str(root / "reports")]) == 0
        matchday = oracle_ops.matchday_create_report("2026-06-01", str(root / "reports"))
        assert Path(matchday["output_dir"]).exists()
        matchday_status = oracle_ops.build_matchday_status(matchday["output_dir"])
        assert matchday_status["ready_for_dry_run"]
        precheck = oracle_ops.matchday_precheck_report(matchday["output_dir"])
        assert "phase_detected" in precheck
        next_report = oracle_ops.matchday_next_report(matchday["output_dir"])
        assert next_report["next_actions"]
        phase_report = oracle_ops.matchday_phase_report(matchday["output_dir"], str(ledger), str(odds_store), str(root / "reports"), "pre_match")
        assert phase_report["phase"]["phase"] == "pre_match"
        matchday_report = oracle_ops.matchday_report(matchday["output_dir"], str(ledger), str(odds_store), str(root / "reports"), phase="pre_match")
        assert "evidence" in matchday_report

        absent = oracle_ops.build_health(root / "absent", str(ledger))
        assert absent["status"] == "bloquant"
        assert features.read_text(encoding="utf-8") == before_features
        assert matches.read_text(encoding="utf-8") == before_matches

    print("test_oracle_ops ok")


if __name__ == "__main__":
    main()
