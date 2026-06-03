import argparse
import html
import json
from pathlib import Path
from typing import Any, Dict, List

from event_lifecycle_manager import build_lifecycle_report
from evidence_gate import build_evidence_gate
from near_close_scheduler import build_schedule
from odds_lab_wizard import build_status as odds_status
from real_observation_guard import build_guard_report


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le rapport autopilot doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _commands_from_schedule(schedule: Dict[str, Any]) -> List[str]:
    commands = []
    for item in schedule.get("schedule") or []:
        collect = item.get("command_collect_near_close")
        dry = item.get("command_dry_run")
        if collect and "mapping sport_key requis" not in collect:
            commands.append(collect)
        if dry:
            commands.append(dry)
    return commands


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_autopilot_report(
    ledger: str = "reports/shadow_ledger.csv",
    snapshots: str = "reports/odds_snapshots.csv",
    reports_dir: str = "reports",
) -> Dict[str, Any]:
    lifecycle = build_lifecycle_report(ledger)
    schedule = build_schedule(ledger)
    guard = build_guard_report(ledger, snapshots, phase="pre_match", scope="ledger")
    status = odds_status(snapshots, ledger, reports_dir)
    lifecycle_report_path = Path(reports_dir) / "event_lifecycle.json"
    active_sports = _read_json(Path(reports_dir) / "the_odds_api_active_soccer_sports.json")
    source_coverage = _read_json(Path(reports_dir) / "source_coverage_report.json")
    evidence = build_evidence_gate(
        shadow_report_path=str(Path(reports_dir) / "shadow_clv_report.json"),
        quality_audit_path=str(Path(reports_dir) / "shadow_quality_audit.json"),
        big5_summary_path=str(Path(reports_dir) / "big5_xg_summary.json"),
        clv_readiness_path=str(Path(reports_dir) / "clv_readiness.json"),
        real_guard_path=str(Path(reports_dir) / "real_observation_guard.json"),
        matchday_status_path=str(Path(reports_dir) / "matchday_status.json"),
        lifecycle_path=str(lifecycle_report_path) if lifecycle_report_path.exists() else "",
    )
    pending_closing = lifecycle.get("pending_closing", 0)
    pending_results = lifecycle.get("pending_results", 0)
    blocked = [
        "appel reseau automatique",
        "conversion near-close en taken odds",
        "activation Telegram/Railway",
        "creation de mise ou staking",
    ]
    if pending_closing:
        blocked.append("ajout massif de nouvelles observations avant capture near-close")
    safe_commands = [
        f"python event_lifecycle_manager.py --ledger {ledger} --status",
        f"python near_close_scheduler.py --ledger {ledger} --commands",
        f"python real_observation_guard.py --ledger {ledger} --snapshots {snapshots} --phase pre_match --scope ledger",
    ] + _commands_from_schedule(schedule)[:6]
    if pending_results:
        safe_commands.append(f"python result_capture_helper.py --ledger {ledger} --template reports/manual_results_due.csv")
    if pending_closing:
        recommended = "collecter les near-close reelles avant d'ajouter plus d'observations"
    elif pending_results:
        recommended = "renseigner les resultats manuels avant nouvelle collecte"
    elif source_coverage.get("identified_gaps"):
        recommended = "utiliser intake manuel Betclic pour les matchs absents des APIs"
        safe_commands.append("python manual_betclic_intake_helper.py --template reports/betclic_manual_intake.csv --date YYYY-MM-DD")
    else:
        recommended = "preparer de nouvelles observations shadow limitees"
    return {
        "current_state": {
            "odds_status": status,
            "lifecycle_counts": lifecycle.get("status_counts"),
            "pending_closing": pending_closing,
            "pending_results": pending_results,
            "guard_verdict": guard.get("verdict"),
            "evidence_status": evidence.get("global_status"),
            "active_soccer_sports": active_sports.get("active_count"),
            "source_coverage_gaps": source_coverage.get("identified_gaps") or [],
        },
        "safe_next_commands": safe_commands,
        "blocked_actions": blocked,
        "recommended_human_action": recommended,
        "lifecycle": lifecycle,
        "near_close_schedule": schedule,
        "real_guard": guard,
        "evidence_summary": {
            "global_status": evidence.get("global_status"),
            "blockers": evidence.get("blockers") or [],
        },
        "active_sports_summary": {
            "available": bool(active_sports),
            "active_count": active_sports.get("active_count"),
        },
        "source_coverage_summary": {
            "available": bool(source_coverage),
            "gaps": source_coverage.get("identified_gaps") or [],
            "recommendations": source_coverage.get("source_recommendations") or [],
        },
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    commands = "".join(f"<li><code>{html.escape(str(cmd))}</code></li>" for cmd in report.get("safe_next_commands") or [])
    blocked = "".join(f"<li>{html.escape(str(item))}</li>" for item in report.get("blocked_actions") or [])
    target.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>Odds Autopilot Dry-Run</h1>"
        f"<p>Action humaine recommandee: {html.escape(str(report.get('recommended_human_action')))}</p>"
        f"<h2>Commandes sûres</h2><ul>{commands}</ul><h2>Actions bloquees</h2><ul>{blocked}</ul>"
        "<p>Dry-run local, aucun reseau et aucune mise.</p></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any]) -> None:
    state = report.get("current_state") or {}
    print("Odds Autopilot Dry-Run Oracle")
    print(f"- Pending closing: {state.get('pending_closing')}")
    print(f"- Pending results: {state.get('pending_results')}")
    print(f"- Guard: {state.get('guard_verdict')}")
    print(f"- Evidence: {state.get('evidence_status')}")
    print(f"- Action humaine recommandee: {report.get('recommended_human_action')}")
    for command in (report.get("safe_next_commands") or [])[:10]:
        print(f"- Commande sure: {command}")
    print("- Aucun reseau, aucune mise, aucun Telegram.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Autopilot dry-run odds, sans action risquee.")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--snapshots", default="reports/odds_snapshots.csv")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = build_autopilot_report(args.ledger, args.snapshots, args.reports_dir)
        if args.output:
            write_json(report, args.output)
        if args.html:
            write_html(report, args.html)
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
