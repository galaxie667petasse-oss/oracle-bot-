import argparse
import html
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from api_football_same_day_runner import run_same_day
from shadow_ledger import pending_closing


def _safe_dir(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le runner next-days doit ecrire hors data/.")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Les rapports next-days doivent rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _date_range(start_date: str, days: int) -> List[str]:
    if days <= 0:
        raise ValueError("--days doit etre positif")
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    return [(start + timedelta(days=offset)).isoformat() for offset in range(days)]


def _fixture_path(directory: str, date: str) -> str:
    if not directory:
        return ""
    for name in (f"{date}.json", f"fixtures_{date}.json", f"api_football_fixtures_{date}.json"):
        path = Path(directory) / name
        if path.exists():
            return str(path)
    return ""


def _odds_path(directory: str, date: str) -> str:
    if not directory:
        return ""
    for name in (f"{date}.json", f"odds_{date}.json", f"api_football_odds_{date}.json"):
        path = Path(directory) / name
        if path.exists():
            return str(path)
    return ""


def run_next_days(
    start_date: str,
    days: int = 3,
    output_dir: str = "reports/api_football_next_days",
    ledger: str = "reports/shadow_ledger.csv",
    allow_network: bool = False,
    dry_run: bool = True,
    apply: bool = False,
    max_events_per_day: int = 3,
    max_total_events: int = 5,
    force_lab: bool = False,
    fixtures_json_dir: str = "",
    odds_json_dir: str = "",
    debug_network: bool = False,
) -> Dict[str, Any]:
    if not start_date:
        raise ValueError("--start-date requis")
    if max_events_per_day <= 0:
        raise ValueError("--max-events-per-day doit etre positif")
    if max_total_events <= 0:
        raise ValueError("--max-total-events doit etre positif")
    pending_before = len(pending_closing(ledger))
    effective_apply = bool(apply and not dry_run)
    effective_network = bool(allow_network)
    if effective_apply and pending_before > 20 and not force_lab:
        raise ValueError("Apply refuse: pending closing > 20. Utiliser --force-lab seulement apres revue humaine.")

    out_dir = _safe_dir(output_dir)
    dates = _date_range(start_date, days)
    reports: List[Dict[str, Any]] = []
    remaining = max_total_events
    total_selected = 0
    total_added = 0
    network_debug: List[Dict[str, Any]] = []
    for date in dates:
        if remaining <= 0:
            reports.append({
                "date": date,
                "skipped": True,
                "reason": "max_total_events atteint",
                "lab_only": True,
                "can_influence_picks": False,
            })
            continue
        per_day = min(max_events_per_day, remaining)
        day_output_dir = str(out_dir / date.replace("-", "_"))
        fixtures_json = _fixture_path(fixtures_json_dir, date)
        odds_json = _odds_path(odds_json_dir, date)
        network_debug.append({
            "date": date,
            "internal_call": "run_same_day",
            "allow_network_propagated": effective_network,
            "output_dir": day_output_dir,
            "fixtures_json": fixtures_json,
            "odds_json": odds_json,
            "lab_only": True,
            "can_influence_picks": False,
        })
        report = run_same_day(
            date,
            output_dir=day_output_dir,
            ledger=ledger,
            fixtures_json=fixtures_json,
            odds_json=odds_json,
            allow_network=effective_network,
            apply=effective_apply,
            max_events=per_day,
            debug=True,
        )
        if effective_network and not bool(report.get("allow_network")):
            raise RuntimeError("Erreur: --allow-network demande mais non propage. Verifier argparse/runner config.")
        selected = int(report.get("selection_rows") or 0)
        added = int(report.get("would_add_or_added") or 0)
        total_selected += selected
        total_added += added
        remaining = max(0, max_total_events - total_selected)
        reports.append(report)

    summary = {
        "start_date": start_date,
        "days": days,
        "dates": dates,
        "output_dir": str(out_dir),
        "allow_network": effective_network,
        "network_requested": bool(allow_network),
        "network_message": "reseau autorise explicitement" if effective_network else "reseau non autorise: ajouter --allow-network pour interroger API-Football",
        "dry_run": bool(dry_run),
        "applied": effective_apply,
        "pending_closing_before": pending_before,
        "max_events_per_day": max_events_per_day,
        "max_total_events": max_total_events,
        "dates_scanned": len(dates),
        "fixtures_total": sum(int(item.get("fixtures") or 0) for item in reports),
        "odds_valid_total": sum(int(item.get("odds_valid") or 0) for item in reports),
        "h2h_valid_not_finished_total": sum(int(item.get("valid_h2h_not_finished_rows") or 0) for item in reports),
        "selected_total": total_selected,
        "would_add_or_added_total": total_added,
        "date_reports": reports,
        "debug_network": bool(debug_network),
        "network_debug": network_debug if debug_network else [],
        "message": "Next-days API-Football: observation shadow seulement, laboratoire local.",
        "lab_only": True,
        "can_influence_picks": False,
    }
    write_json(summary, str(out_dir / "summary.json"))
    write_html(summary, str(out_dir / "summary.html"))
    return summary


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item.get('date')))}</td>"
        f"<td>{html.escape(str(item.get('fixtures', '')))}</td>"
        f"<td>{html.escape(str(item.get('odds_valid', '')))}</td>"
        f"<td>{html.escape(str(item.get('valid_h2h_not_finished_rows', '')))}</td>"
        f"<td>{html.escape(str(item.get('selection_rows', '')))}</td>"
        f"<td>{html.escape(str(item.get('would_add_or_added', '')))}</td>"
        "</tr>"
        for item in report.get("date_reports") or []
    )
    target.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>API-Football Next Days</h1>"
        f"<p>Dates scannees: {report.get('dates_scanned')}</p>"
        f"<p>Selection totale: {report.get('selected_total')}</p>"
        "<table border='1'><tr><th>Date</th><th>Fixtures</th><th>Odds valides</th><th>H2H non termines</th><th>Selection</th><th>Ajout/would add</th></tr>"
        + rows
        + "</table><p>Laboratoire local, aucune mise.</p></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("API-Football next-days runner")
    print(f"- Start date: {report.get('start_date')}")
    print(f"- Days: {report.get('days')}")
    print(f"- Reseau autorise: {report.get('allow_network')}")
    if not report.get("allow_network"):
        print("- Reseau non autorise: aucun appel API-Football reel.")
    if report.get("debug_network"):
        for item in report.get("network_debug") or []:
            print(
                f"- Debug reseau {item.get('date')}: {item.get('internal_call')} "
                f"allow_network={item.get('allow_network_propagated')} "
                f"output_dir={item.get('output_dir')}"
            )
            print(f"  fixtures_json={item.get('fixtures_json') or 'aucun'}")
            print(f"  odds_json={item.get('odds_json') or 'aucun'}")
    for item in report.get("date_reports") or []:
        print(
            f"- {item.get('date')}: fixtures={item.get('fixtures', 0)}, "
            f"odds_valid={item.get('odds_valid', 0)}, "
            f"h2h_non_termines={item.get('valid_h2h_not_finished_rows', 0)}, "
            f"selection={item.get('selection_rows', 0)}, added/would_add={item.get('would_add_or_added', 0)}"
        )
    print(f"- Selection totale: {report.get('selected_total')}")
    print("- Observation shadow seulement, laboratoire local.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Scanner API-Football sur plusieurs jours futurs, reseau bloque par defaut.")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--force-lab", action="store_true")
    parser.add_argument("--max-events-per-day", type=int, default=3)
    parser.add_argument("--max-total-events", type=int, default=5)
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--output-dir", default="reports/api_football_next_days")
    parser.add_argument("--fixtures-json-dir", default="")
    parser.add_argument("--odds-json-dir", default="")
    parser.add_argument("--debug-network", action="store_true")
    parser.add_argument("--summary-json", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        effective_dry_run = bool(args.dry_run or not args.apply)
        report = run_next_days(
            args.start_date,
            days=args.days,
            output_dir=args.output_dir,
            ledger=args.ledger,
            allow_network=args.allow_network,
            dry_run=effective_dry_run,
            apply=args.apply,
            max_events_per_day=args.max_events_per_day,
            max_total_events=args.max_total_events,
            force_lab=args.force_lab,
            fixtures_json_dir=args.fixtures_json_dir,
            odds_json_dir=args.odds_json_dir,
            debug_network=args.debug_network,
        )
        if args.summary_json:
            write_json(report, args.summary_json)
        if args.html:
            write_html(report, args.html)
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
