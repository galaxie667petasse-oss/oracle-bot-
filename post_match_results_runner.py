import argparse
import html
import json
from pathlib import Path
from typing import Any, Dict, List

from api_football_results_adapter import fetch_results, normalize_results_payload, read_fixture, write_csv, write_raw
from odds_source_config import load_odds_source_config
from shadow_ledger import read_ledger
from shadow_result_matcher import match_results


def _safe_dir(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le runner resultats doit ecrire hors data/.")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Les rapports resultats doivent rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def dates_missing_results(ledger: str) -> List[str]:
    dates = {
        str(row.get("match_date") or "").strip()
        for row in read_ledger(ledger)
        if str(row.get("match_date") or "").strip() and str(row.get("result") or "unknown").lower() == "unknown"
    }
    return sorted(dates)


def _fixture_path(directory: str, date: str) -> str:
    if not directory:
        return ""
    for name in (f"{date}.json", f"results_{date}.json", f"api_football_results_{date}.json"):
        path = Path(directory) / name
        if path.exists():
            return str(path)
    return ""


def run_post_match_results(
    ledger: str = "reports/shadow_ledger.csv",
    output_dir: str = "reports/post_match_results",
    allow_network: bool = False,
    dry_run: bool = True,
    apply: bool = False,
    dates_from_ledger: bool = False,
    dates: List[str] | None = None,
    results_json_dir: str = "",
) -> Dict[str, Any]:
    out_dir = _safe_dir(output_dir)
    dates_to_check = sorted(set(dates or []))
    if dates_from_ledger or not dates_to_check:
        dates_to_check = dates_missing_results(ledger)
    config = load_odds_source_config()
    date_reports: List[Dict[str, Any]] = []
    all_rows: List[Dict[str, Any]] = []
    for date in dates_to_check:
        payload_path = _fixture_path(results_json_dir, date)
        if payload_path:
            payload = read_fixture(payload_path)
        elif allow_network and not dry_run:
            payload = fetch_results(config, date=date)
        else:
            payload = {"response": []}
        raw_path = out_dir / f"results_{date}.json"
        csv_path = out_dir / f"results_{date}.csv"
        write_raw(payload, str(raw_path))
        rows = normalize_results_payload(payload)
        write_csv(rows, str(csv_path))
        all_rows.extend(rows)
        date_reports.append({
            "date": date,
            "result_file": str(csv_path),
            "raw_file": str(raw_path),
            "results_rows": len(rows),
        })
    combined_path = out_dir / "results_combined.csv"
    write_csv(all_rows, str(combined_path))
    match = match_results(ledger, str(combined_path), dry_run=not (apply and not dry_run))
    summary = {
        "ledger": ledger,
        "output_dir": str(out_dir),
        "allow_network": bool(allow_network and not dry_run),
        "dry_run": bool(dry_run),
        "applied": bool(apply and not dry_run),
        "dates_checked": dates_to_check,
        "result_files": [item.get("result_file") for item in date_reports],
        "combined_results_file": str(combined_path),
        "matched": match.get("matched"),
        "updated": match.get("updated"),
        "unmatched": match.get("unmatched"),
        "ambiguous": match.get("ambiguous"),
        "date_reports": date_reports,
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
        f"<tr><td>{html.escape(str(item.get('date')))}</td><td>{item.get('results_rows')}</td><td>{item.get('matched')}</td><td>{item.get('updated')}</td><td>{item.get('unmatched')}</td><td>{item.get('ambiguous')}</td></tr>"
        for item in report.get("date_reports") or []
    )
    target.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>Post-Match Results Runner</h1>"
        f"<p>Dates: {len(report.get('dates_checked') or [])}</p>"
        "<table border='1'><tr><th>Date</th><th>Rows</th><th>Matched</th><th>Updated</th><th>Unmatched</th><th>Ambiguous</th></tr>"
        + rows
        + "</table><p>Laboratoire local, aucun resultat invente.</p></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Post-match results runner")
    print(f"- Dates checked: {len(report.get('dates_checked') or [])}")
    print(f"- Matched: {report.get('matched')}")
    print(f"- Updated: {report.get('updated')}")
    print(f"- Unmatched: {report.get('unmatched')}")
    print(f"- Ambiguous: {report.get('ambiguous')}")
    print("- Aucun resultat invente, aucun reseau sans --allow-network.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Recupere/matche les resultats post-match API-Football, reseau bloque par defaut.")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--output-dir", default="reports/post_match_results")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dates-from-ledger", action="store_true")
    parser.add_argument("--date", action="append", default=[])
    parser.add_argument("--results-json-dir", default="")
    parser.add_argument("--summary-json", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = run_post_match_results(
            ledger=args.ledger,
            output_dir=args.output_dir,
            allow_network=args.allow_network,
            dry_run=bool(args.dry_run or not args.apply),
            apply=args.apply,
            dates_from_ledger=args.dates_from_ledger,
            dates=args.date,
            results_json_dir=args.results_json_dir,
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
