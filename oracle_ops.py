import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from evidence_gate import build_evidence_gate, write_html as write_evidence_html, write_json as write_evidence_json
from sample_size_planner import build_sample_size_plan, write_html as write_plan_html, write_json as write_plan_json
from shadow_clv_report import build_shadow_clv_report, write_html as write_shadow_html, write_json as write_shadow_json
from shadow_ledger import summarize_ledger
from shadow_quality_audit import audit_shadow_ledger, write_html as write_quality_html, write_json as write_quality_json
from shadow_workflow import workflow_init
from shadow_templates import create_candidates_template, create_closing_template, create_results_template
from manual_odds_import import write_template as write_manual_odds_template
from odds_closing_matcher import match_closing_snapshots
from odds_intake_audit import build_intake_audit, write_html as write_intake_html, write_json as write_intake_json
from odds_lab_wizard import build_status as odds_wizard_status, dry_run_full as odds_wizard_dry_run, import_manual as odds_wizard_import_manual, make_templates as odds_wizard_templates, next_actions as odds_wizard_next, validate_manual as odds_wizard_validate_manual
from odds_snapshot_store import DEFAULT_STORE as DEFAULT_ODDS_STORE, init_store, summarize_snapshots
from odds_source_config import load_odds_source_config, validate_config, write_example
from odds_source_quality_report import build_quality_report, write_html as write_odds_quality_html, write_json as write_odds_quality_json
from odds_to_shadow import snapshots_to_shadow
from oracle_architecture_map import build_architecture_map, write_html as write_architecture_html, write_json as write_architecture_json
from oracle_project_scorecard import build_scorecard, write_html as write_scorecard_html, write_json as write_scorecard_json
from progress_loop import summarize_progress
from matchday_pack import create_pack as create_matchday_pack, pack_status as build_matchday_status
from matchday_runner import full_dry_run as matchday_full_dry_run, write_matchday_report
from matchday_status_report import build_status_report as build_matchday_status_report
from real_observation_guard import build_guard_report as build_real_guard, write_html as write_guard_html, write_json as write_guard_json
from test_archive_manager import archive_and_reset as archive_tests_and_reset
from api_odds_collection_runner import collect as api_collect, full_pre_match as api_full_pre_match
from event_lifecycle_manager import build_lifecycle_report, write_html as write_lifecycle_html, write_json as write_lifecycle_json
from near_close_workflow import build_status as near_close_status_report, suggest_commands as near_close_suggest_commands
from near_close_scheduler import build_schedule as build_near_close_schedule, write_html as write_schedule_html, write_json as write_schedule_json
from odds_autopilot_dryrun import build_autopilot_report, write_html as write_autopilot_html, write_json as write_autopilot_json
from result_capture_helper import write_template as write_results_due_template
from shadow_progress_dashboard import build_progress_dashboard, write_html as write_progress_html, write_json as write_progress_json
from soccer_odds_sport_scanner import scan_sports as scan_soccer_sports


KEY_MODULES = [
    "shadow_ledger.py",
    "closing_manual_import.py",
    "shadow_clv_report.py",
    "daily_shadow_candidates.py",
    "shadow_workflow.py",
    "shadow_templates.py",
    "results_manual_import.py",
    "shadow_quality_audit.py",
    "evidence_gate.py",
    "shadow_simulator.py",
    "sample_size_planner.py",
    "shadow_message_formatter.py",
    "odds_source_config.py",
    "odds_normalizer.py",
    "odds_snapshot_store.py",
    "manual_odds_import.py",
    "api_football_odds_adapter.py",
    "the_odds_api_adapter.py",
    "odds_to_shadow.py",
    "odds_closing_matcher.py",
    "odds_source_quality_report.py",
    "odds_lab_wizard.py",
    "odds_intake_audit.py",
    "odds_e2e_demo.py",
    "oracle_architecture_map.py",
    "pipeline_contracts.py",
    "llm_analyst_contract.py",
    "restitution_schema.py",
    "progress_loop.py",
    "oracle_project_scorecard.py",
    "agent_orchestrator_dryrun.py",
    "test_archive_manager.py",
    "real_observation_guard.py",
    "matchday_pack.py",
    "matchday_runner.py",
    "matchday_status_report.py",
    "soccer_odds_sport_scanner.py",
    "odds_shadow_selector.py",
    "near_close_workflow.py",
    "api_odds_collection_runner.py",
    "event_lifecycle_manager.py",
    "near_close_scheduler.py",
    "result_capture_helper.py",
    "shadow_progress_dashboard.py",
    "odds_autopilot_dryrun.py",
]


def _status(ok: bool, warning: bool = False) -> str:
    if ok:
        return "OK"
    return "warning" if warning else "bloquant"


def _gitignore_contains(root: Path, pattern: str) -> bool:
    path = root / ".gitignore"
    if not path.exists():
        return False
    return pattern in path.read_text(encoding="utf-8", errors="ignore")


def build_health(root: Path = Path("."), ledger: str = "reports/shadow_ledger.csv") -> Dict[str, Any]:
    root = Path(root)
    checks = []
    def add(name: str, ok: bool, warning: bool = False, detail: str = "") -> None:
        checks.append({"name": name, "status": _status(ok, warning), "ok": ok, "detail": detail})
    for module in KEY_MODULES:
        add(f"module {module}", (root / module).exists())
    add("reports/ ignore", _gitignore_contains(root, "reports/"))
    add("external_data/ ignore", _gitignore_contains(root, "external_data/"))
    add("data/features_modern.csv present", (root / "data" / "features_modern.csv").exists(), warning=True)
    add("data/MATCHES.csv present", (root / "data" / "MATCHES.csv").exists(), warning=True)
    add("shadow ledger present", (root / ledger).exists(), warning=True)
    add("Railway non lance par ops", True, detail="oracle_ops ne demarre aucun service distant")
    add("Telegram non appele par ops", True, detail="oracle_ops ne charge pas de bot Telegram")
    blockers = [item for item in checks if item["status"] == "bloquant"]
    warnings = [item for item in checks if item["status"] == "warning"]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(root),
        "checks": checks,
        "status": "bloquant" if blockers else ("warning" if warnings else "OK"),
        "warnings": warnings,
        "blockers": blockers,
        "lab_only": True,
        "can_influence_picks": False,
    }


def daily_checklist(date: str = "") -> Dict[str, Any]:
    return {
        "date": date or datetime.now().strftime("%Y-%m-%d"),
        "checklist": [
            "generer ou lire les observations shadow",
            "verifier pending closing",
            "verifier pending results",
            "generer les templates",
            "generer le rapport shadow",
            "lire evidence gate",
            "ne pas conclure sans sample significatif",
        ],
        "message": "Routine locale: observation seulement, aucune mise conseillee.",
    }


def _reports_path(reports_dir: str, filename: str) -> str:
    return str(Path(reports_dir) / filename)


def run_subprocess(args: List[str]) -> Dict[str, Any]:
    completed = subprocess.run([sys.executable, *args], text=True, capture_output=True, encoding="utf-8", errors="replace", timeout=1800)
    return {
        "command": " ".join([sys.executable, *args]),
        "returncode": completed.returncode,
        "ok": completed.returncode == 0,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def shadow_templates(ledger: str, reports_dir: str) -> Dict[str, str]:
    reports = Path(reports_dir)
    reports.mkdir(parents=True, exist_ok=True)
    return {
        "candidates": str(create_candidates_template(str(reports / "shadow_candidates_template.csv"), force=True)),
        "closing": str(create_closing_template(str(reports / "manual_closing_import_template.csv"), ledger=ledger, force=True)),
        "results": str(create_results_template(str(reports / "manual_results_import_template.csv"), ledger=ledger, force=True)),
    }


def shadow_report(ledger: str, reports_dir: str) -> Dict[str, Any]:
    report = build_shadow_clv_report(ledger)
    write_shadow_json(report, _reports_path(reports_dir, "shadow_clv_report.json"))
    write_shadow_html(report, _reports_path(reports_dir, "shadow_clv_report.html"))
    return report


def quality_report(ledger: str, reports_dir: str) -> Dict[str, Any]:
    report = audit_shadow_ledger(ledger)
    write_quality_json(report, _reports_path(reports_dir, "shadow_quality_audit.json"))
    write_quality_html(report, _reports_path(reports_dir, "shadow_quality_audit.html"))
    return report


def evidence_report(reports_dir: str) -> Dict[str, Any]:
    report = build_evidence_gate(
        shadow_report_path=_reports_path(reports_dir, "shadow_clv_report.json"),
        quality_audit_path=_reports_path(reports_dir, "shadow_quality_audit.json"),
        big5_summary_path=_reports_path(reports_dir, "big5_xg_summary.json"),
        clv_readiness_path=_reports_path(reports_dir, "clv_readiness.json"),
        benchmark_summary_path=_reports_path(reports_dir, "benchmark_summary.json"),
    )
    write_evidence_json(report, _reports_path(reports_dir, "evidence_gate.json"))
    write_evidence_html(report, _reports_path(reports_dir, "evidence_gate.html"))
    return report


def sample_plan(reports_dir: str) -> Dict[str, Any]:
    report = build_sample_size_plan(shadow_report_path=_reports_path(reports_dir, "shadow_clv_report.json"))
    write_plan_json(report, _reports_path(reports_dir, "sample_size_plan.json"))
    write_plan_html(report, _reports_path(reports_dir, "sample_size_plan.html"))
    return report


def odds_config_report() -> Dict[str, Any]:
    config = load_odds_source_config()
    report = validate_config(config)
    return {
        "config_ok": report["ok"],
        "sources": report["sources"],
        "warnings": report["warnings"],
        "errors": report["errors"],
        "lab_only": True,
    }


def odds_template(reports_dir: str) -> Dict[str, Any]:
    reports = Path(reports_dir)
    reports.mkdir(parents=True, exist_ok=True)
    example = write_example("config/odds_sources.example.json", force=False)
    template = write_manual_odds_template(str(reports / "manual_odds_snapshot_template.csv"))
    return {"config_example": str(example), "manual_odds_template": str(template)}


def odds_summary(store: str = DEFAULT_ODDS_STORE) -> Dict[str, Any]:
    return summarize_snapshots(store)


def odds_quality(reports_dir: str, store: str = DEFAULT_ODDS_STORE) -> Dict[str, Any]:
    report = build_quality_report(store)
    write_odds_quality_json(report, _reports_path(reports_dir, "odds_source_quality.json"))
    write_odds_quality_html(report, _reports_path(reports_dir, "odds_source_quality.html"))
    return report


def odds_to_shadow_report(snapshots: str, ledger: str, reports_dir: str, apply: bool = False) -> Dict[str, Any]:
    report = snapshots_to_shadow(snapshots, ledger, dry_run=not apply)
    target = Path(_reports_path(reports_dir, "odds_to_shadow_report.json"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def closing_match_report(snapshots: str, ledger: str, reports_dir: str, apply: bool = False) -> Dict[str, Any]:
    report = match_closing_snapshots(ledger, snapshots, dry_run=not apply)
    target = Path(_reports_path(reports_dir, "odds_closing_matcher_report.json"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def odds_lab(reports_dir: str, store: str = DEFAULT_ODDS_STORE) -> Dict[str, Any]:
    Path(reports_dir).mkdir(parents=True, exist_ok=True)
    init_store(store)
    return {
        "config": odds_config_report(),
        "template": odds_template(reports_dir),
        "summary": odds_summary(store),
        "quality": odds_quality(reports_dir, store),
        "message": "Odds lab local: aucun reseau, aucune mise conseillee.",
    }


def odds_intake_audit_report(reports_dir: str, snapshots: str, ledger: str) -> Dict[str, Any]:
    report = build_intake_audit(snapshots, ledger)
    write_intake_json(report, _reports_path(reports_dir, "odds_intake_audit.json"))
    write_intake_html(report, _reports_path(reports_dir, "odds_intake_audit.html"))
    return report


def architecture_report(reports_dir: str) -> Dict[str, Any]:
    report = build_architecture_map(check_files=True)
    write_architecture_json(report, _reports_path(reports_dir, "architecture_map.json"))
    write_architecture_html(report, _reports_path(reports_dir, "architecture_map.html"))
    return report


def contracts_report(reports_dir: str) -> Dict[str, Any]:
    result = run_subprocess(["pipeline_contracts.py", "--list", "--json", _reports_path(reports_dir, "pipeline_contracts.json"), "--html", _reports_path(reports_dir, "pipeline_contracts.html")])
    return result


def scorecard_report(reports_dir: str) -> Dict[str, Any]:
    report = build_scorecard(reports_dir)
    write_scorecard_json(report, _reports_path(reports_dir, "project_scorecard.json"))
    write_scorecard_html(report, _reports_path(reports_dir, "project_scorecard.html"))
    return report


def llm_contract_report(reports_dir: str) -> Dict[str, Any]:
    result = run_subprocess(["llm_analyst_contract.py", "--show", "--template-json", _reports_path(reports_dir, "llm_analyst_input_template.json")])
    return result


def agent_dryrun_report(reports_dir: str) -> Dict[str, Any]:
    result = run_subprocess(["agent_orchestrator_dryrun.py", "--full"])
    target = Path(_reports_path(reports_dir, "agent_orchestrator_dryrun.txt"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text((result.get("stdout") or "") + (result.get("stderr") or ""), encoding="utf-8")
    return result


def project_map_report(reports_dir: str, skip_dashboard: bool = True) -> Dict[str, Any]:
    Path(reports_dir).mkdir(parents=True, exist_ok=True)
    architecture = architecture_report(reports_dir)
    scorecard = scorecard_report(reports_dir)
    evidence = evidence_report(reports_dir)
    optional = []
    if not skip_dashboard:
        optional.append(run_subprocess(["dashboard_builder.py", "--input", reports_dir]))
    return {
        "architecture_blocks": len(architecture.get("blocks") or []),
        "scorecard_global": scorecard.get("global_score"),
        "evidence_status": evidence.get("global_status"),
        "optional": optional,
        "lab_only": True,
    }


def real_start_report(reports_dir: str, ledger: str, snapshots: str) -> Dict[str, Any]:
    report = build_real_guard(ledger, snapshots)
    write_guard_json(report, _reports_path(reports_dir, "real_observation_guard.json"))
    write_guard_html(report, _reports_path(reports_dir, "real_observation_guard.html"))
    return {
        "guard": report,
        "recommendation": "archiver les tests" if report.get("verdict") in {"mixed_test_and_real", "needs_review", "invalid"} else "pret pour observations reelles",
        "message": "Observation seulement, aucune mise.",
    }


def real_guard_ledger_report(reports_dir: str, ledger: str, snapshots: str) -> Dict[str, Any]:
    report = build_real_guard(ledger, snapshots, phase="pre_match", scope="ledger")
    write_guard_json(report, _reports_path(reports_dir, "real_observation_guard.json"))
    write_guard_html(report, _reports_path(reports_dir, "real_observation_guard.html"))
    return report


def api_odds_status_report(reports_dir: str, ledger: str, snapshots: str) -> Dict[str, Any]:
    return {
        "odds_summary": summarize_snapshots(snapshots),
        "near_close": near_close_status_report(ledger),
        "real_guard_ledger": build_real_guard(ledger, snapshots, phase="pre_match", scope="ledger"),
        "lab_only": True,
    }


def lifecycle_report(reports_dir: str, ledger: str) -> Dict[str, Any]:
    report = build_lifecycle_report(ledger)
    write_lifecycle_json(report, _reports_path(reports_dir, "event_lifecycle.json"))
    write_lifecycle_html(report, _reports_path(reports_dir, "event_lifecycle.html"))
    return report


def near_close_schedule_report(reports_dir: str, ledger: str) -> Dict[str, Any]:
    report = build_near_close_schedule(ledger)
    write_schedule_json(report, _reports_path(reports_dir, "near_close_schedule.json"))
    write_schedule_html(report, _reports_path(reports_dir, "near_close_schedule.html"))
    return report


def results_template_report(reports_dir: str, ledger: str) -> Dict[str, Any]:
    return write_results_due_template(ledger, _reports_path(reports_dir, "manual_results_due.csv"))


def shadow_progress_report(reports_dir: str, ledger: str) -> Dict[str, Any]:
    report = build_progress_dashboard(
        ledger,
        lifecycle_path=_reports_path(reports_dir, "event_lifecycle.json"),
        evidence_path=_reports_path(reports_dir, "evidence_gate.json"),
    )
    write_progress_json(report, _reports_path(reports_dir, "shadow_progress_dashboard.json"))
    write_progress_html(report, _reports_path(reports_dir, "shadow_progress_dashboard.html"))
    return report


def odds_autopilot_report(reports_dir: str, ledger: str, snapshots: str) -> Dict[str, Any]:
    report = build_autopilot_report(ledger, snapshots, reports_dir)
    write_autopilot_json(report, _reports_path(reports_dir, "odds_autopilot_dryrun.json"))
    write_autopilot_html(report, _reports_path(reports_dir, "odds_autopilot_dryrun.html"))
    return report


def matchday_create_report(match_date: str, reports_dir: str) -> Dict[str, Any]:
    if not match_date:
        raise ValueError("--date requis avec --matchday")
    safe = match_date.replace("-", "_")
    return create_matchday_pack(match_date, str(Path(reports_dir) / f"matchday_{safe}"))


def matchday_report(pack: str, ledger: str, snapshots: str, reports_dir: str, phase: str = "full_day") -> Dict[str, Any]:
    return write_matchday_report(pack, ledger, snapshots, reports_dir, phase=phase)


def matchday_precheck_report(pack: str) -> Dict[str, Any]:
    return build_matchday_status_report(pack)


def matchday_next_report(pack: str) -> Dict[str, Any]:
    report = build_matchday_status_report(pack)
    return {
        "pack": pack,
        "phase_detected": report.get("phase_detected"),
        "warnings": report.get("warnings") or [],
        "blockers": report.get("blockers") or [],
        "next_actions": report.get("next_actions") or [],
        "lab_only": True,
    }


def matchday_phase_report(pack: str, ledger: str, snapshots: str, reports_dir: str, phase: str) -> Dict[str, Any]:
    return matchday_full_dry_run(pack, ledger, snapshots, reports_dir, phase=phase)


def full_local(ledger: str, reports_dir: str, skip_benchmark: bool = False, skip_dashboard: bool = False) -> Dict[str, Any]:
    Path(reports_dir).mkdir(parents=True, exist_ok=True)
    health = build_health(Path("."), ledger)
    summary = summarize_ledger(ledger)
    quality = quality_report(ledger, reports_dir)
    shadow = shadow_report(ledger, reports_dir)
    evidence = evidence_report(reports_dir)
    plan = sample_plan(reports_dir)
    optional = []
    if not skip_benchmark:
        optional.append(run_subprocess([
            "benchmark_governance.py",
            "--shadow-report", _reports_path(reports_dir, "shadow_clv_report.json"),
            "--evidence-gate", _reports_path(reports_dir, "evidence_gate.json"),
            "--summary-json", _reports_path(reports_dir, "benchmark_summary.json"),
            "--html", _reports_path(reports_dir, "benchmark_governance.html"),
            "--registry", _reports_path(reports_dir, "model_registry.json"),
        ]))
    if not skip_dashboard:
        optional.append(run_subprocess(["dashboard_builder.py", "--input", reports_dir]))
    return {
        "health": health,
        "shadow_summary": summary,
        "quality": quality,
        "shadow_report": shadow,
        "evidence": evidence,
        "sample_plan": plan,
        "optional": optional,
    }


def print_odds_report(title: str, report: Dict[str, Any]) -> None:
    print(f"Oracle Ops - {title}")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("- Laboratoire local: aucune mise conseillee, aucun reseau automatique.")


def print_health(report: Dict[str, Any]) -> None:
    print("Oracle Operations Center - Health")
    print(f"- Statut: {report.get('status')}")
    for check in report.get("checks") or []:
        print(f"- {check.get('status')}: {check.get('name')} {check.get('detail') or ''}".rstrip())
    print("- Mode local: aucune mise conseillee, aucun Telegram, aucun Railway.")


def print_daily(report: Dict[str, Any]) -> None:
    print("Oracle Operations Center - Daily checklist")
    print(f"- Date: {report.get('date')}")
    for idx, item in enumerate(report.get("checklist") or [], start=1):
        print(f"{idx}. {item}")
    print(f"- {report.get('message')}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Centre de controle local Oracle Bot.")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--health", action="store_true")
    actions.add_argument("--daily", action="store_true")
    actions.add_argument("--shadow-init", action="store_true")
    actions.add_argument("--shadow-summary", action="store_true")
    actions.add_argument("--shadow-report", action="store_true")
    actions.add_argument("--shadow-templates", action="store_true")
    actions.add_argument("--evidence", action="store_true")
    actions.add_argument("--big5-summary", action="store_true")
    actions.add_argument("--clv-readiness", action="store_true")
    actions.add_argument("--full-local", action="store_true")
    actions.add_argument("--odds-config", action="store_true")
    actions.add_argument("--odds-template", action="store_true")
    actions.add_argument("--odds-summary", action="store_true")
    actions.add_argument("--odds-quality", action="store_true")
    actions.add_argument("--odds-to-shadow", action="store_true")
    actions.add_argument("--closing-match", action="store_true")
    actions.add_argument("--odds-lab", action="store_true")
    actions.add_argument("--odds-status", action="store_true")
    actions.add_argument("--odds-wizard", action="store_true")
    actions.add_argument("--odds-validate-manual", default="")
    actions.add_argument("--odds-import-manual", default="")
    actions.add_argument("--odds-intake-audit", action="store_true")
    actions.add_argument("--odds-next", action="store_true")
    actions.add_argument("--architecture", action="store_true")
    actions.add_argument("--contracts", action="store_true")
    actions.add_argument("--scorecard", action="store_true")
    actions.add_argument("--progress", action="store_true")
    actions.add_argument("--llm-contract", action="store_true")
    actions.add_argument("--agent-dryrun", action="store_true")
    actions.add_argument("--project-map", action="store_true")
    actions.add_argument("--real-start", action="store_true")
    actions.add_argument("--matchday", action="store_true")
    actions.add_argument("--matchday-status", default="")
    actions.add_argument("--matchday-report", default="")
    actions.add_argument("--matchday-precheck", default="")
    actions.add_argument("--matchday-next", default="")
    actions.add_argument("--matchday-phase", default="")
    actions.add_argument("--scan-soccer-odds", action="store_true")
    actions.add_argument("--api-odds-status", action="store_true")
    actions.add_argument("--api-pre-match-jleague", action="store_true")
    actions.add_argument("--near-close-status", action="store_true")
    actions.add_argument("--near-close-next", action="store_true")
    actions.add_argument("--real-guard-ledger", action="store_true")
    actions.add_argument("--lifecycle", action="store_true")
    actions.add_argument("--near-close-schedule", action="store_true")
    actions.add_argument("--results-template", action="store_true")
    actions.add_argument("--shadow-progress", action="store_true")
    actions.add_argument("--odds-autopilot", action="store_true")
    actions.add_argument("--archive-tests", action="store_true")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--odds-store", default=DEFAULT_ODDS_STORE)
    parser.add_argument("--snapshots", default=DEFAULT_ODDS_STORE)
    parser.add_argument("--apply", action="store_true", help="Applique les changements ledger pour odds-to-shadow/closing-match")
    parser.add_argument("--skip-benchmark", action="store_true")
    parser.add_argument("--skip-dashboard", action="store_true")
    parser.add_argument("--date", default="")
    parser.add_argument("--phase", default="full_day")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.health:
            print_health(build_health(Path("."), args.ledger))
        elif args.daily:
            print_daily(daily_checklist(args.date))
        elif args.shadow_init:
            info = workflow_init(args.ledger)
            print("Oracle Ops - shadow init")
            print(json.dumps(info, ensure_ascii=False, indent=2))
        elif args.shadow_summary:
            print("Oracle Ops - shadow summary")
            print(json.dumps(summarize_ledger(args.ledger), ensure_ascii=False, indent=2))
        elif args.shadow_report:
            print("Oracle Ops - shadow report")
            print(json.dumps(shadow_report(args.ledger, args.reports_dir), ensure_ascii=False, indent=2))
        elif args.shadow_templates:
            print("Oracle Ops - shadow templates")
            print(json.dumps(shadow_templates(args.ledger, args.reports_dir), ensure_ascii=False, indent=2))
        elif args.evidence:
            print("Oracle Ops - evidence gate")
            print(json.dumps(evidence_report(args.reports_dir), ensure_ascii=False, indent=2))
        elif args.big5_summary:
            result = run_subprocess(["multi_league_xg_aggregator.py", "--reports-dir", args.reports_dir, "--output", _reports_path(args.reports_dir, "big5_xg_summary.json"), "--html", _reports_path(args.reports_dir, "big5_xg_summary.html")])
            print("Oracle Ops - Big 5 summary")
            print(result["stdout"] or result["stderr"])
            return 0 if result["ok"] else 1
        elif args.clv_readiness:
            result = run_subprocess(["clv_readiness_report.py", "--features", "data/features_modern.csv", "--output", _reports_path(args.reports_dir, "clv_readiness.json"), "--html", _reports_path(args.reports_dir, "clv_readiness.html")])
            print("Oracle Ops - CLV readiness")
            print(result["stdout"] or result["stderr"])
            return 0 if result["ok"] else 1
        elif args.full_local:
            print("Oracle Ops - full local")
            print(json.dumps(full_local(args.ledger, args.reports_dir, args.skip_benchmark, args.skip_dashboard), ensure_ascii=False, indent=2))
        elif args.odds_config:
            print_odds_report("odds config", odds_config_report())
        elif args.odds_template:
            print_odds_report("odds template", odds_template(args.reports_dir))
        elif args.odds_summary:
            print_odds_report("odds summary", odds_summary(args.odds_store))
        elif args.odds_quality:
            print_odds_report("odds quality", odds_quality(args.reports_dir, args.odds_store))
        elif args.odds_to_shadow:
            print_odds_report("odds to shadow", odds_to_shadow_report(args.snapshots, args.ledger, args.reports_dir, apply=args.apply))
        elif args.closing_match:
            print_odds_report("closing matcher", closing_match_report(args.snapshots, args.ledger, args.reports_dir, apply=args.apply))
        elif args.odds_lab:
            print_odds_report("odds lab", odds_lab(args.reports_dir, args.odds_store))
        elif args.odds_status:
            print_odds_report("odds status", odds_wizard_status(args.odds_store, args.ledger, args.reports_dir))
        elif args.odds_wizard:
            print("Oracle Ops - odds wizard")
            print("1. python oracle_ops.py --odds-template")
            print("2. Remplir reports/manual_odds_snapshot.csv")
            print("3. python oracle_ops.py --odds-validate-manual reports/manual_odds_snapshot.csv")
            print("4. python oracle_ops.py --odds-import-manual reports/manual_odds_snapshot.csv --apply")
            print("5. python oracle_ops.py --odds-to-shadow --apply apres dry-run propre")
            print("- Laboratoire local: aucune mise, aucun reseau.")
        elif args.odds_validate_manual:
            print_odds_report("odds validate manual", odds_wizard_validate_manual(args.odds_validate_manual))
        elif args.odds_import_manual:
            if not args.apply:
                print_odds_report("odds import manual dry-run", odds_wizard_validate_manual(args.odds_import_manual))
            else:
                print_odds_report("odds import manual", odds_wizard_import_manual(args.odds_import_manual, args.odds_store, allow_errors=False))
        elif args.odds_intake_audit:
            print_odds_report("odds intake audit", odds_intake_audit_report(args.reports_dir, args.snapshots, args.ledger))
        elif args.odds_next:
            print_odds_report("odds next", {"next_actions": odds_wizard_next(args.odds_store, args.ledger)})
        elif args.architecture:
            print_odds_report("architecture", architecture_report(args.reports_dir))
        elif args.contracts:
            print_odds_report("pipeline contracts", contracts_report(args.reports_dir))
        elif args.scorecard:
            print_odds_report("project scorecard", scorecard_report(args.reports_dir))
        elif args.progress:
            print_odds_report("progress loop", summarize_progress(_reports_path(args.reports_dir, "progress_loop.csv")))
        elif args.llm_contract:
            print_odds_report("LLM analyst contract", llm_contract_report(args.reports_dir))
        elif args.agent_dryrun:
            print_odds_report("agent dry-run", agent_dryrun_report(args.reports_dir))
        elif args.project_map:
            print_odds_report("project map", project_map_report(args.reports_dir, skip_dashboard=args.skip_dashboard))
        elif args.real_start:
            print_odds_report("real start", real_start_report(args.reports_dir, args.ledger, args.snapshots))
        elif args.matchday:
            print_odds_report("matchday", matchday_create_report(args.date, args.reports_dir))
        elif args.matchday_status:
            print_odds_report("matchday status", build_matchday_status(args.matchday_status))
        elif args.matchday_report:
            print_odds_report("matchday report", matchday_report(args.matchday_report, args.ledger, args.snapshots, args.reports_dir, phase=args.phase))
        elif args.matchday_precheck:
            print_odds_report("matchday precheck", matchday_precheck_report(args.matchday_precheck))
        elif args.matchday_next:
            print_odds_report("matchday next", matchday_next_report(args.matchday_next))
        elif args.matchday_phase:
            print_odds_report("matchday phase", matchday_phase_report(args.matchday_phase, args.ledger, args.snapshots, args.reports_dir, args.phase))
        elif args.scan_soccer_odds:
            print_odds_report("scan soccer odds", scan_soccer_sports(allow_network=False, dry_run=True))
        elif args.api_odds_status:
            print_odds_report("api odds status", api_odds_status_report(args.reports_dir, args.ledger, args.snapshots))
        elif args.api_pre_match_jleague:
            payload = {
                "dry_run": True,
                "command": "python api_odds_collection_runner.py --full-pre-match --sport soccer_japan_j_league --bookmaker Pinnacle --max-events 3 --allow-network",
                "message": "Dry-run par defaut: relancer explicitement avec --allow-network dans le runner si necessaire.",
            }
            print_odds_report("api pre-match jleague", payload)
        elif args.near_close_status:
            print_odds_report("near-close status", near_close_status_report(args.ledger))
        elif args.near_close_next:
            print_odds_report("near-close next", near_close_suggest_commands(args.ledger))
        elif args.real_guard_ledger:
            print_odds_report("real guard ledger", real_guard_ledger_report(args.reports_dir, args.ledger, args.snapshots))
        elif args.lifecycle:
            print_odds_report("event lifecycle", lifecycle_report(args.reports_dir, args.ledger))
        elif args.near_close_schedule:
            print_odds_report("near-close schedule", near_close_schedule_report(args.reports_dir, args.ledger))
        elif args.results_template:
            print_odds_report("results template", results_template_report(args.reports_dir, args.ledger))
        elif args.shadow_progress:
            print_odds_report("shadow progress", shadow_progress_report(args.reports_dir, args.ledger))
        elif args.odds_autopilot:
            print_odds_report("odds autopilot dry-run", odds_autopilot_report(args.reports_dir, args.ledger, args.snapshots))
        elif args.archive_tests:
            if not args.apply:
                print_odds_report("archive tests dry-run", {"dry_run": True, "message": "Relancer avec --apply pour archiver et reset."})
            else:
                print_odds_report("archive tests", archive_tests_and_reset(args.reports_dir, label="before_real_june"))
        else:
            print_health(build_health(Path("."), args.ledger))
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
