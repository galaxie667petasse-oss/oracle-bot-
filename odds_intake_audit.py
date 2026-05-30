import argparse
import html
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from odds_snapshot_store import load_snapshots
from shadow_ledger import read_ledger
from team_name_normalizer import normalize_team_name


def _key(row: Dict[str, Any]) -> Tuple[str, ...]:
    league = str(row.get("league") or "")
    return (
        str(row.get("match_date") or "").strip().lower(),
        league.strip().lower(),
        normalize_team_name(row.get("home_team") or "", league=league).lower(),
        normalize_team_name(row.get("away_team") or "", league=league).lower(),
        str(row.get("market_type") or "").strip().lower(),
        str(row.get("side") or "").strip().lower(),
    )


def build_intake_audit(snapshots_path: str, ledger_path: str) -> Dict[str, Any]:
    snapshots = load_snapshots(snapshots_path)
    ledger = read_ledger(ledger_path)
    valid = [row for row in snapshots if row.get("validation_status") == "valid"]
    invalid = [row for row in snapshots if row.get("validation_status") != "valid"]
    taken = [row for row in valid if str(row.get("is_near_close") or "").lower() != "true"]
    near_close = [row for row in valid if str(row.get("is_near_close") or "").lower() == "true"]
    taken_keys = {_key(row) for row in taken}
    near_keys = {_key(row) for row in near_close}
    ledger_keys = {_key(row) for row in ledger}
    linked = [row for row in ledger if _key(row) in taken_keys]
    closing_real = [row for row in ledger if str(row.get("closing_odds") or "").strip()]
    gaps = {
        "taken_without_near_close": len(taken_keys - near_keys),
        "near_close_without_taken": len(near_keys - taken_keys),
        "ledger_without_closing": sum(1 for row in ledger if not str(row.get("closing_odds") or "").strip()),
        "ledger_without_result": sum(1 for row in ledger if str(row.get("result") or "unknown").lower() == "unknown"),
    }
    if not snapshots and not ledger:
        verdict = "no_data"
    elif snapshots and not ledger:
        verdict = "snapshots_only"
    elif ledger and not closing_real:
        verdict = "shadow_started"
    elif closing_real:
        verdict = "closing_collection_started"
    else:
        verdict = "poor_quality"
    if invalid and len(invalid) > len(valid):
        verdict = "poor_quality"
    recommendations = []
    if not snapshots:
        recommendations.append("importer un CSV manuel de cotes")
    if taken and not near_close:
        recommendations.append("capturer des snapshots near-close horodates")
    if near_close and not ledger:
        recommendations.append("convertir les taken odds en observations shadow")
    if ledger and not closing_real:
        recommendations.append("matcher les near-close vers le ledger en dry-run")
    if gaps["ledger_without_result"]:
        recommendations.append("importer les resultats manuels")
    return {
        "snapshots": snapshots_path,
        "ledger": ledger_path,
        "snapshots_total": len(snapshots),
        "taken_snapshots": len(taken),
        "near_close_snapshots": len(near_close),
        "valid_odds": len(valid),
        "invalid_odds": len(invalid),
        "shadow_observations": len(ledger),
        "shadow_linked_to_snapshots": len(linked),
        "shadow_without_snapshot": max(0, len(ledger) - len(linked)),
        "near_close_matchable": len(taken_keys & near_keys),
        "closing_coverage_possible": round(len(taken_keys & near_keys) / len(taken_keys) * 100.0, 2) if taken_keys else 0.0,
        "closing_coverage_real": round(len(closing_real) / len(ledger) * 100.0, 2) if ledger else 0.0,
        "gaps": gaps,
        "verdict": verdict,
        "recommendations": recommendations,
        "lab_only": True,
        "can_influence_picks": False,
    }


def _safe(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le rapport intake odds doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = _safe(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = _safe(output)
    items = "".join(f"<li>{html.escape(str(item))}</li>" for item in report.get("recommendations") or [])
    target.write_text("\n".join([
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Odds Intake Audit</title></head><body>",
        "<h1>Odds Intake Audit</h1>",
        f"<p>Verdict: {html.escape(str(report.get('verdict')))}</p>",
        "<ul>",
        f"<li>Snapshots taken: {report.get('taken_snapshots')}</li>",
        f"<li>Snapshots near-close: {report.get('near_close_snapshots')}</li>",
        f"<li>Valid odds: {report.get('valid_odds')}</li>",
        f"<li>Invalid odds: {report.get('invalid_odds')}</li>",
        f"<li>Observations shadow liees: {report.get('shadow_linked_to_snapshots')}</li>",
        f"<li>Coverage closing possible: {report.get('closing_coverage_possible')}%</li>",
        f"<li>Coverage closing reelle: {report.get('closing_coverage_real')}%</li>",
        "</ul>",
        f"<h2>Recommandations</h2><ul>{items}</ul>",
        "<p>Laboratoire local, aucune mise.</p></body></html>",
    ]), encoding="utf-8")
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Audit intake odds Oracle")
    print(f"- Snapshots totaux: {report.get('snapshots_total')}")
    print(f"- Taken / near-close: {report.get('taken_snapshots')} / {report.get('near_close_snapshots')}")
    print(f"- Observations shadow: {report.get('shadow_observations')}")
    print(f"- Coverage closing possible: {report.get('closing_coverage_possible')}%")
    print(f"- Coverage closing reelle: {report.get('closing_coverage_real')}%")
    print(f"- Verdict: {report.get('verdict')}")
    for item in report.get("recommendations") or []:
        print(f"- Action: {item}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Audit local de la chaine odds intake.")
    parser.add_argument("--snapshots", default="reports/odds_snapshots.csv")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = build_intake_audit(args.snapshots, args.ledger)
        print_report(report)
        if args.output:
            print(f"- JSON ecrit: {write_json(report, args.output)}")
        if args.html:
            print(f"- HTML ecrit: {write_html(report, args.html)}")
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
