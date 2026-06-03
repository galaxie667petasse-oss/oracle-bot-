import argparse
import csv
import html
import json
from pathlib import Path
from typing import Any, Dict, List

from results_manual_import import VALID_RESULTS, import_manual_results, read_results_csv
from shadow_ledger import read_ledger


TEMPLATE_COLUMNS = ["shadow_id", "match_date", "league", "home_team", "away_team", "market_type", "side", "result", "notes"]


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Les sorties result capture doivent rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def due_result_rows(ledger: str) -> List[Dict[str, Any]]:
    return [row for row in read_ledger(ledger) if str(row.get("result") or "unknown").lower() == "unknown"]


def write_template(ledger: str, output: str) -> Dict[str, Any]:
    rows = due_result_rows(ledger)
    target = _safe_output(output)
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=TEMPLATE_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "shadow_id": row.get("shadow_id"),
                "match_date": row.get("match_date"),
                "league": row.get("league"),
                "home_team": row.get("home_team"),
                "away_team": row.get("away_team"),
                "market_type": row.get("market_type"),
                "side": row.get("side"),
                "result": "",
                "notes": "",
            })
    return {"ledger": ledger, "template": str(target), "rows_written": len(rows), "lab_only": True}


def validate_results(ledger: str, results_csv: str) -> Dict[str, Any]:
    ledger_rows = read_ledger(ledger)
    ids = {row.get("shadow_id") for row in ledger_rows}
    errors: List[str] = []
    valid_rows = 0
    for idx, row in enumerate(read_results_csv(results_csv), start=2):
        shadow_id = str(row.get("shadow_id") or "").strip()
        result = str(row.get("result") or "").strip().lower()
        if shadow_id not in ids:
            errors.append(f"ligne {idx}: shadow_id inconnu {shadow_id}")
            continue
        if result not in VALID_RESULTS:
            errors.append(f"ligne {idx}: resultat invalide {result}")
            continue
        valid_rows += 1
    return {
        "ledger": ledger,
        "results_csv": results_csv,
        "rows_read": valid_rows + len(errors),
        "valid_rows": valid_rows,
        "errors": errors,
        "ok": not errors,
        "lab_only": True,
        "can_influence_picks": False,
    }


def apply_results(ledger: str, results_csv: str, dry_run: bool = True) -> Dict[str, Any]:
    validation = validate_results(ledger, results_csv)
    if validation["errors"]:
        return {**validation, "dry_run": dry_run, "rows_updated": 0}
    import_report = import_manual_results(ledger, results_csv, dry_run=dry_run)
    return {**validation, **import_report}


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    errors = "".join(f"<li>{html.escape(str(item))}</li>" for item in report.get("errors") or [])
    target.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>Result Capture Helper</h1>"
        f"<p>OK: {report.get('ok')} | lignes valides: {report.get('valid_rows')} | mises a jour: {report.get('rows_updated', 0)}</p>"
        f"<ul>{errors}</ul><p>Observation shadow seulement, aucune mise.</p></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Result Capture Helper Oracle")
    if "template" in report:
        print(f"- Template: {report.get('template')}")
        print(f"- Lignes a renseigner: {report.get('rows_written')}")
    else:
        print(f"- CSV resultats: {report.get('results_csv')}")
        print(f"- OK: {report.get('ok')}")
        print(f"- Lignes valides: {report.get('valid_rows')}")
        print(f"- Mises a jour: {report.get('rows_updated', 0)}")
        for error in report.get("errors") or []:
            print(f"- Erreur: {error}")
    print("- Resultats manuels uniquement, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Prepare ou applique les resultats manuels du shadow ledger.")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--template", default="")
    parser.add_argument("--results", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.template:
            report = write_template(args.ledger, args.template)
        elif args.results:
            report = apply_results(args.ledger, args.results, dry_run=not args.apply)
        else:
            report = {"ledger": args.ledger, "due_results": len(due_result_rows(args.ledger)), "lab_only": True}
        if args.output:
            write_json(report, args.output)
        if args.html:
            write_html(report, args.html)
        print_report(report)
        return 0 if not report.get("errors") else 1
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
