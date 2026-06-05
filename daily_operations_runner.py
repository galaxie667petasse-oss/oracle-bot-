import argparse
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from api_football_next_days_runner import run_next_days
from data_subscription_evaluator import build_evaluation
from evidence_gate import build_evidence_gate, write_html as write_evidence_html, write_json as write_evidence_json
from near_close_batch_runner import run_batch as run_near_close_batch
from near_close_window_planner import build_window_plan, write_html as write_window_html, write_json as write_window_json
from post_match_results_runner import run_post_match_results
from shadow_clv_report import build_shadow_clv_report, write_html as write_shadow_html, write_json as write_shadow_json
from source_coverage_report import build_source_coverage_report


def _safe_dir(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Daily operations doit ecrire hors data/.")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Daily operations doit ecrire hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _path(reports_dir: str, name: str) -> str:
    return str(Path(reports_dir) / name)


def run_daily_operations(
    date: str = "",
    reports_dir: str = "reports/daily_operations",
    ledger: str = "reports/shadow_ledger.csv",
    allow_network: bool = False,
    morning: bool = False,
    pre_close: bool = False,
    post_match: bool = False,
    full_dry_run: bool = False,
) -> Dict[str, Any]:
    active_date = date or datetime.now().strftime("%Y-%m-%d")
    out_dir = _safe_dir(reports_dir)
    phases: Dict[str, Any] = {}
    effective_network = bool(allow_network and not full_dry_run)
    if morning or full_dry_run:
        phases["morning"] = {
            "next_days": run_next_days(
                active_date,
                days=3,
                output_dir=str(out_dir / "next_days"),
                ledger=ledger,
                allow_network=effective_network,
                dry_run=True,
                apply=False,
            ),
            "source_coverage": build_source_coverage_report(),
        }
    if pre_close or full_dry_run:
        window = build_window_plan(ledger, hours_before=2)
        write_window_json(window, _path(str(out_dir), "near_close_window_plan.json"))
        write_window_html(window, _path(str(out_dir), "near_close_window_plan.html"))
        phases["pre_close"] = {
            "near_close_window": window,
            "near_close_batch": run_near_close_batch(ledger, output_dir=str(out_dir), allow_network=False, dry_run=True),
        }
    if post_match or full_dry_run:
        post = run_post_match_results(ledger, output_dir=str(out_dir / "post_match_results"), allow_network=False, dry_run=True, apply=False, dates_from_ledger=True)
        shadow = build_shadow_clv_report(ledger)
        write_shadow_json(shadow, _path(str(out_dir), "shadow_clv_report.json"))
        write_shadow_html(shadow, _path(str(out_dir), "shadow_clv_report.html"))
        evidence = build_evidence_gate(shadow_report_path=_path(str(out_dir), "shadow_clv_report.json"))
        write_evidence_json(evidence, _path(str(out_dir), "evidence_gate.json"))
        write_evidence_html(evidence, _path(str(out_dir), "evidence_gate.html"))
        phases["post_match"] = {"post_match_results": post, "shadow_report": shadow, "evidence_gate": evidence}
    subscription = build_evaluation(str(out_dir))
    report = {
        "date": active_date,
        "reports_dir": str(out_dir),
        "allow_network": effective_network,
        "full_dry_run": bool(full_dry_run),
        "phases": phases,
        "subscription_evaluator": subscription,
        "lab_only": True,
        "can_influence_picks": False,
        "message": "Daily operations local: observation shadow seulement.",
    }
    write_json(report, _path(str(out_dir), "daily_operations_summary.json"))
    write_html(report, _path(str(out_dir), "daily_operations_summary.html"))
    return report


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>Daily Operations Runner</h1><pre>"
        + html.escape(json.dumps(report, ensure_ascii=False, indent=2))
        + "</pre><p>Laboratoire local, aucune mise.</p></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Daily operations runner")
    print(f"- Date: {report.get('date')}")
    print(f"- Reseau autorise: {report.get('allow_network')}")
    print(f"- Phases: {', '.join((report.get('phases') or {}).keys()) or 'aucune'}")
    print(f"- Subscription: {(report.get('subscription_evaluator') or {}).get('recommendation')}")
    print("- Workflow local, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Commande centrale operations quotidiennes Oracle, reseau bloque par defaut.")
    parser.add_argument("--date", default="")
    parser.add_argument("--reports-dir", default="reports/daily_operations")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--morning", action="store_true")
    parser.add_argument("--pre-close", action="store_true")
    parser.add_argument("--post-match", action="store_true")
    parser.add_argument("--full-dry-run", action="store_true")
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = run_daily_operations(
            args.date,
            reports_dir=args.reports_dir,
            ledger=args.ledger,
            allow_network=args.allow_network,
            morning=args.morning,
            pre_close=args.pre_close,
            post_match=args.post_match,
            full_dry_run=args.full_dry_run or not any([args.morning, args.pre_close, args.post_match]),
        )
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
