import argparse
import html
import json
from pathlib import Path
from typing import Any, Dict

from event_lifecycle_manager import build_lifecycle_report
from shadow_clv_report import build_shadow_clv_report
from shadow_ledger import summarize_ledger


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le dashboard shadow progress doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _read_json(path: str) -> Dict[str, Any]:
    if not path or not Path(path).exists():
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def build_progress_dashboard(ledger: str, lifecycle_path: str = "", evidence_path: str = "") -> Dict[str, Any]:
    ledger_summary = summarize_ledger(ledger)
    shadow_report = build_shadow_clv_report(ledger)
    lifecycle = _read_json(lifecycle_path) or build_lifecycle_report(ledger)
    evidence = _read_json(evidence_path)
    sample = int(ledger_summary.get("signals_total") or 0)
    thresholds = {str(target): {"target": target, "current": sample, "remaining": max(0, target - sample), "progress_percent": round(min(sample / target, 1.0) * 100, 2)} for target in (30, 100, 500, 1000)}
    return {
        "ledger": ledger,
        "observations": sample,
        "pending_closing": lifecycle.get("pending_closing", 0),
        "pending_results": lifecycle.get("pending_results", 0),
        "completed": lifecycle.get("completed", 0),
        "clv_coverage": shadow_report.get("clv_coverage"),
        "roi_coverage": round((shadow_report.get("settled_signals") or 0) / sample * 100, 2) if sample else 0.0,
        "clv_mean": shadow_report.get("clv_mean"),
        "roi": shadow_report.get("roi"),
        "next_near_close": lifecycle.get("due_now") or [],
        "results_to_fill": lifecycle.get("due_results") or [],
        "evidence_status": evidence.get("global_status"),
        "evidence_blockers": evidence.get("blockers") or [],
        "sample_progress": thresholds,
        "status": "observation seulement",
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    blockers = "".join(f"<li>{html.escape(str(item))}</li>" for item in report.get("evidence_blockers") or [])
    progress = "".join(
        f"<li>{key}: {value['current']}/{value['target']} ({value['progress_percent']}%), reste {value['remaining']}</li>"
        for key, value in (report.get("sample_progress") or {}).items()
    )
    target.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>Shadow Progress Dashboard</h1>"
        f"<p>Observations: {report.get('observations')} | Pending closing: {report.get('pending_closing')} | Pending results: {report.get('pending_results')} | Complete: {report.get('completed')}</p>"
        f"<p>CLV coverage: {report.get('clv_coverage')}% | ROI coverage: {report.get('roi_coverage')}%</p>"
        f"<h2>Sample progress</h2><ul>{progress}</ul><h2>Evidence blockers</h2><ul>{blockers or '<li>Aucun rapport evidence</li>'}</ul>"
        "<p>Statut: observation seulement, preuve insuffisante.</p></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Shadow Progress Dashboard Oracle")
    print(f"- Observations: {report.get('observations')}")
    print(f"- Pending closing: {report.get('pending_closing')}")
    print(f"- Pending results: {report.get('pending_results')}")
    print(f"- CLV coverage: {report.get('clv_coverage')}%")
    print(f"- Evidence: {report.get('evidence_status')}")
    print("- Statut: observation seulement, preuve insuffisante.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Dashboard shadow progress local.")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--lifecycle", default="")
    parser.add_argument("--evidence", default="")
    parser.add_argument("--output", default="reports/shadow_progress_dashboard.html")
    parser.add_argument("--json", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = build_progress_dashboard(args.ledger, args.lifecycle, args.evidence)
        if args.json:
            write_json(report, args.json)
        if args.output:
            write_html(report, args.output)
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
