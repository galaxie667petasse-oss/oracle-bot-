import argparse
import html
import json
from pathlib import Path
from typing import Any, Dict, List


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le rapport abonnement doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _collect_usage(reports_dir: str) -> Dict[str, Any]:
    root = Path(reports_dir)
    same_day = []
    next_days = []
    shadow = []
    for path in root.rglob("*.json") if root.exists() else []:
        name = path.name.lower()
        data = _read_json(path)
        if not data:
            continue
        if "api_football_same_day" in str(path).lower() or name == "summary.json" and "same_day" in str(path).lower():
            if "fixtures" in data or "odds_valid" in data:
                same_day.append(data)
        if "api_football_next_days" in str(path).lower() and ("dates_scanned" in data or "date_reports" in data):
            next_days.append(data)
        if name in {"shadow_clv_report.json", "shadow_progress_dashboard.json"}:
            shadow.append(data)
    return {"same_day": same_day, "next_days": next_days, "shadow": shadow}


def build_evaluation(usage_reports: str = "reports") -> Dict[str, Any]:
    usage = _collect_usage(usage_reports)
    same_day_calls = len(usage["same_day"])
    next_days_scanned = sum(int(item.get("dates_scanned") or item.get("days") or 0) for item in usage["next_days"])
    shadow_samples = [
        int(item.get("sample_size") or item.get("signals_total") or item.get("observations") or 0)
        for item in usage["shadow"]
    ]
    completed = max(shadow_samples or [0])
    requests_day_needed = max(3, next_days_scanned * 2 + 3)
    needs = {
        "requests_per_day_needed": requests_day_needed,
        "fixtures_calls": max(1, next_days_scanned or 1),
        "odds_calls": max(1, next_days_scanned or 1),
        "results_calls": 1,
        "near_close_calls": 1,
        "dates_scanned": next_days_scanned,
    }
    blockers = []
    if completed < 30:
        recommendation = "no_paid_needed_yet"
        blockers.append("moins de 30 observations completes")
    elif requests_day_needed <= 100:
        recommendation = "stay_free"
    elif requests_day_needed <= 300:
        recommendation = "API_Football_Pro"
    elif requests_day_needed <= 1000:
        recommendation = "API_Football_Ultra"
    else:
        recommendation = "API_Football_Mega"
    if completed == 0:
        blockers.append("preuve live non demarree")
    report = {
        "usage_reports": usage_reports,
        "same_day_reports": same_day_calls,
        "next_days_reports": len(usage["next_days"]),
        "shadow_completed_estimate": completed,
        "project_need": needs,
        "plans_evaluated": {
            "api_football": ["free", "pro", "ultra", "mega"],
            "the_odds_api": ["free", "paid_historical"],
        },
        "quota_status": "insuffisant_a_estimer" if not same_day_calls and not next_days_scanned else "usage_local_lu",
        "subscription_recommendation": recommendation,
        "recommendation": recommendation,
        "blockers": blockers,
        "message": "Un abonnement augmente la couverture et l'automatisation, pas la preuve d'edge.",
        "lab_only": True,
        "can_influence_picks": False,
    }
    return report


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>Data Subscription Evaluator</h1><pre>"
        + html.escape(json.dumps(report, ensure_ascii=False, indent=2))
        + "</pre><p>Couverture et automatisation seulement, pas preuve d'edge.</p></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Data subscription evaluator")
    print(f"- Recommendation: {report.get('recommendation')}")
    print(f"- Requests/day estimees: {(report.get('project_need') or {}).get('requests_per_day_needed')}")
    print(f"- Shadow complete estime: {report.get('shadow_completed_estimate')}")
    print("- Un abonnement ne valide aucun signal.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Evalue les quotas et abonnements data utiles au laboratoire.")
    parser.add_argument("--usage-reports", default="reports")
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = build_evaluation(args.usage_reports)
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
