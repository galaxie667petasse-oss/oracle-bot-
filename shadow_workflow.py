import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from closing_manual_import import import_manual_closing
from shadow_clv_report import build_shadow_clv_report, write_html as write_shadow_html, write_json as write_shadow_json
from shadow_ledger import init_ledger, pending_closing, pending_results, read_ledger, summarize_ledger
from shadow_templates import create_closing_template, create_results_template, create_candidates_template


DEFAULT_LEDGER = "reports/shadow_ledger.csv"
DEFAULT_CLOSING_TEMPLATE = "reports/manual_closing_import_template.csv"
DEFAULT_RESULTS_TEMPLATE = "reports/manual_results_import_template.csv"
DEFAULT_CANDIDATES_TEMPLATE = "reports/shadow_candidates_template.csv"
DEFAULT_SHADOW_REPORT_JSON = "reports/shadow_clv_report.json"
DEFAULT_SHADOW_REPORT_HTML = "reports/shadow_clv_report.html"


def ensure_not_data(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le workflow shadow ne doit pas ecrire dans data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def print_safety() -> None:
    print("Mode shadow : observation seulement, aucune mise conseillee.")


def _ledger_dir(ledger: str) -> Path:
    return Path(ledger).parent if Path(ledger).parent != Path("") else Path("reports")


def _template_paths_for_ledger(ledger: str) -> Dict[str, str]:
    base = _ledger_dir(ledger)
    return {
        "candidates": str(base / "shadow_candidates_template.csv"),
        "closing": str(base / "manual_closing_import_template.csv"),
        "results": str(base / "manual_results_import_template.csv"),
    }


def workflow_init(ledger: str = DEFAULT_LEDGER, force_templates: bool = False) -> Dict[str, Any]:
    ledger_path = init_ledger(ledger)
    created = [str(ledger_path)]
    template_paths = _template_paths_for_ledger(ledger)
    for creator, path in [
        (create_candidates_template, template_paths["candidates"]),
        (create_closing_template, template_paths["closing"]),
        (create_results_template, template_paths["results"]),
    ]:
        target = Path(path)
        if force_templates or not target.exists():
            if creator is create_candidates_template:
                created.append(str(creator(path, force=True)))
            else:
                created.append(str(creator(path, ledger=ledger, force=True)))
    return {"ledger": str(ledger_path), "created": created}


def workflow_today(ledger: str = DEFAULT_LEDGER, date: str = "") -> Dict[str, Any]:
    date = date or datetime.now().strftime("%Y-%m-%d")
    rows = [row for row in read_ledger(ledger) if str(row.get("match_date") or "")[:10] == date]
    closing = [row for row in rows if not str(row.get("closing_odds") or "").strip()]
    results = [row for row in rows if str(row.get("result") or "unknown").lower() == "unknown"]
    return {
        "date": date,
        "rows": rows,
        "today_count": len(rows),
        "pending_closing": len(closing),
        "pending_results": len(results),
    }


def make_closing_template(ledger: str = DEFAULT_LEDGER, output: str = "", force: bool = True) -> Path:
    output = output or _template_paths_for_ledger(ledger)["closing"]
    ensure_not_data(output)
    return create_closing_template(output, ledger=ledger, force=force)


def make_results_template(ledger: str = DEFAULT_LEDGER, output: str = "", force: bool = True) -> Path:
    output = output or _template_paths_for_ledger(ledger)["results"]
    ensure_not_data(output)
    return create_results_template(output, ledger=ledger, force=force)


def make_shadow_report(ledger: str = DEFAULT_LEDGER, output: str = DEFAULT_SHADOW_REPORT_JSON, html: str = DEFAULT_SHADOW_REPORT_HTML) -> Dict[str, Any]:
    ensure_not_data(output)
    ensure_not_data(html)
    report = build_shadow_clv_report(ledger)
    write_shadow_json(report, output)
    write_shadow_html(report, html)
    return report


def run_optional_command(args: List[str]) -> Dict[str, Any]:
    completed = subprocess.run([sys.executable, *args], text=True, capture_output=True, encoding="utf-8", errors="replace", timeout=1800)
    return {
        "command": " ".join([sys.executable, *args]),
        "returncode": completed.returncode,
        "ok": completed.returncode == 0,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def workflow_full(ledger: str, skip_benchmark: bool = False, skip_dashboard: bool = False) -> Dict[str, Any]:
    init_info = workflow_init(ledger)
    closing_template = make_closing_template(ledger)
    results_template = make_results_template(ledger)
    report_dir = _ledger_dir(ledger)
    report_json = str(report_dir / "shadow_clv_report.json")
    report_html = str(report_dir / "shadow_clv_report.html")
    report = make_shadow_report(ledger, output=report_json, html=report_html)
    optional = []
    if not skip_benchmark:
        optional.append(run_optional_command([
            "benchmark_governance.py",
            "--shadow-report",
            report_json,
            "--summary-json",
            str(report_dir / "benchmark_summary.json"),
            "--html",
            str(report_dir / "benchmark_governance.html"),
            "--registry",
            str(report_dir / "model_registry.json"),
        ]))
    if not skip_dashboard:
        optional.append(run_optional_command(["dashboard_builder.py", "--input", str(report_dir)]))
    return {
        "init": init_info,
        "closing_template": str(closing_template),
        "results_template": str(results_template),
        "report": report,
        "optional": optional,
    }


def print_today(info: Dict[str, Any]) -> None:
    print("Shadow workflow - observations du jour")
    print(f"- Date: {info.get('date')}")
    print(f"- Observations shadow: {info.get('today_count')}")
    print(f"- Pending closing: {info.get('pending_closing')}")
    print(f"- Pending result: {info.get('pending_results')}")
    for row in info.get("rows") or []:
        print(f"  - {row.get('shadow_id')} | {row.get('home_team')} - {row.get('away_team')} | {row.get('market_type')} {row.get('side')} | statut={row.get('status')}")
    print_safety()


def print_summary(summary: Dict[str, Any]) -> None:
    print("Shadow workflow - resume")
    print(f"- Signaux shadow: {summary.get('signals_total')}")
    print(f"- Signaux avec CLV: {summary.get('signals_with_clv')}")
    print(f"- Coverage CLV: {summary.get('clv_coverage')}%")
    print(f"- CLV moyenne: {summary.get('clv_mean')}")
    print_safety()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Workflow quotidien shadow mode Oracle Bot.")
    parser.add_argument("--ledger", default=DEFAULT_LEDGER)
    parser.add_argument("--date", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-benchmark", action="store_true")
    parser.add_argument("--skip-dashboard", action="store_true")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--init", action="store_true")
    action.add_argument("--today", action="store_true")
    action.add_argument("--summary", action="store_true")
    action.add_argument("--make-closing-template", action="store_true")
    action.add_argument("--import-closing", default="")
    action.add_argument("--report", action="store_true")
    action.add_argument("--full", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.init:
            info = workflow_init(args.ledger)
            print("Shadow workflow initialise")
            for item in info["created"]:
                print(f"- Pret: {item}")
            print("- Commandes utiles: shadow_ledger.py --add-csv, closing_manual_import.py, results_manual_import.py, shadow_clv_report.py")
            print_safety()
        elif args.today:
            print_today(workflow_today(args.ledger, args.date))
        elif args.summary:
            print_summary(summarize_ledger(args.ledger))
        elif args.make_closing_template:
            path = make_closing_template(args.ledger)
            print(f"- Template closing ecrit: {path}")
            print_safety()
        elif args.import_closing:
            summary = import_manual_closing(args.ledger, args.import_closing, dry_run=args.dry_run)
            print(f"- Import closing lignes: {summary.get('rows_imported')}, erreurs: {len(summary.get('errors') or [])}")
            for error in summary.get("errors") or []:
                print(f"  - {error}")
            print_safety()
            return 0 if not summary.get("errors") else 1
        elif args.report:
            report = make_shadow_report(args.ledger)
            print(f"- Rapport shadow genere: {DEFAULT_SHADOW_REPORT_JSON} / {DEFAULT_SHADOW_REPORT_HTML}")
            print(f"- Verdict: {report.get('verdict')}")
            print_safety()
        elif args.full:
            info = workflow_full(args.ledger, skip_benchmark=args.skip_benchmark, skip_dashboard=args.skip_dashboard)
            print("Shadow workflow complet")
            print(f"- Ledger: {info['init'].get('ledger')}")
            print(f"- Template closing: {info.get('closing_template')}")
            print(f"- Template resultats: {info.get('results_template')}")
            print(f"- Verdict shadow: {(info.get('report') or {}).get('verdict')}")
            for optional in info.get("optional") or []:
                print(f"- Commande optionnelle OK={optional.get('ok')}: {optional.get('command')}")
            print_safety()
        else:
            print_summary(summarize_ledger(args.ledger))
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
