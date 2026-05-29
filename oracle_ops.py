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
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--skip-benchmark", action="store_true")
    parser.add_argument("--skip-dashboard", action="store_true")
    parser.add_argument("--date", default="")
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
        else:
            print_health(build_health(Path("."), args.ledger))
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
