import argparse
import csv
from pathlib import Path
from typing import Any, Dict, List

from shadow_ledger import LEDGER_COLUMNS, compute_clv, parse_decimal_odds, read_ledger, write_ledger


def read_import_csv(path: str) -> List[Dict[str, str]]:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"CSV closing manuel introuvable: {path}")
    with target.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        required = {"shadow_id", "closing_odds", "closing_source", "notes"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError("Colonnes manquantes dans le CSV closing: " + ", ".join(sorted(missing)))
        return [dict(row) for row in reader]


def import_manual_closing(ledger_path: str, closing_csv: str, dry_run: bool = False) -> Dict[str, Any]:
    ledger_rows = read_ledger(ledger_path)
    by_id = {row.get("shadow_id"): row for row in ledger_rows}
    imported = 0
    errors: List[str] = []
    for idx, item in enumerate(read_import_csv(closing_csv), start=2):
        shadow_id = str(item.get("shadow_id") or "").strip()
        if shadow_id not in by_id:
            errors.append(f"Ligne {idx}: shadow_id inconnu {shadow_id}")
            continue
        try:
            closing_odds = parse_decimal_odds(item.get("closing_odds"), "closing_odds")
            taken_odds = parse_decimal_odds(by_id[shadow_id].get("taken_odds"), "taken_odds")
        except Exception as exc:
            errors.append(f"Ligne {idx}: {exc}")
            continue
        by_id[shadow_id]["closing_odds"] = closing_odds
        by_id[shadow_id]["closing_source"] = str(item.get("closing_source") or "").strip()
        if str(item.get("notes") or "").strip():
            old_notes = str(by_id[shadow_id].get("notes") or "").strip()
            by_id[shadow_id]["notes"] = (old_notes + " | " if old_notes else "") + str(item.get("notes")).strip()
        by_id[shadow_id].update(compute_clv(taken_odds, closing_odds))
        imported += 1
    if not dry_run:
        write_ledger(ledger_rows, ledger_path)
    clvs = []
    for row in ledger_rows:
        if str(row.get("clv_available") or "").lower() == "true":
            try:
                clvs.append(float(row.get("clv_percent") or 0))
            except Exception:
                pass
    return {
        "ledger": ledger_path,
        "closing_csv": closing_csv,
        "dry_run": dry_run,
        "rows_imported": imported,
        "errors": errors,
        "signals_total": len(ledger_rows),
        "signals_with_clv": len(clvs),
        "clv_coverage": round(len(clvs) / len(ledger_rows) * 100.0, 2) if ledger_rows else 0.0,
        "clv_mean": round(sum(clvs) / len(clvs), 6) if clvs else None,
        "clv_positive_rate": round(sum(1 for value in clvs if value > 0) / len(clvs) * 100.0, 2) if clvs else None,
        "lab_only": True,
        "can_influence_picks": False,
    }


def print_summary(summary: Dict[str, Any]) -> None:
    print("Import closing manuel Oracle Bot")
    print(f"- Ledger: {summary.get('ledger')}")
    print(f"- CSV closing: {summary.get('closing_csv')}")
    print(f"- Dry-run: {summary.get('dry_run')}")
    print(f"- Lignes importees: {summary.get('rows_imported')}")
    print(f"- Erreurs: {len(summary.get('errors') or [])}")
    for error in summary.get("errors") or []:
        print(f"  - {error}")
    print(f"- CLV moyenne: {summary.get('clv_mean')}")
    print(f"- CLV positive: {summary.get('clv_positive_rate')}%")
    print(f"- Coverage CLV: {summary.get('clv_coverage')}%")
    print("- Observation seulement: aucune mise, aucun pick automatique.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Importe des closing odds manuelles dans le shadow ledger.")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv", help="Ledger shadow CSV")
    parser.add_argument("--closing-csv", required=True, help="CSV: shadow_id,closing_odds,closing_source,notes")
    parser.add_argument("--dry-run", action="store_true", help="Valide sans ecrire dans le ledger")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        summary = import_manual_closing(args.ledger, args.closing_csv, dry_run=args.dry_run)
        print_summary(summary)
        return 0 if not summary["errors"] else 1
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
