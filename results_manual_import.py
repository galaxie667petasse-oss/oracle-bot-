import argparse
import csv
from pathlib import Path
from typing import Any, Dict, List

from shadow_ledger import read_ledger, write_ledger


VALID_RESULTS = {"win", "loss", "push", "void", "unknown"}


def read_results_csv(path: str) -> List[Dict[str, str]]:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"CSV resultats manuel introuvable: {path}")
    with target.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        required = {"shadow_id", "result", "notes"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError("Colonnes manquantes dans le CSV resultats: " + ", ".join(sorted(missing)))
        return [dict(row) for row in reader]


def import_manual_results(ledger_path: str, results_csv: str, dry_run: bool = False) -> Dict[str, Any]:
    rows = read_ledger(ledger_path)
    by_id = {row.get("shadow_id"): row for row in rows}
    updated = 0
    errors: List[str] = []
    counts = {key: 0 for key in sorted(VALID_RESULTS)}
    for idx, item in enumerate(read_results_csv(results_csv), start=2):
        shadow_id = str(item.get("shadow_id") or "").strip()
        result = str(item.get("result") or "").strip().lower()
        if shadow_id not in by_id:
            errors.append(f"Ligne {idx}: shadow_id inconnu {shadow_id}")
            continue
        if result not in VALID_RESULTS:
            errors.append(f"Ligne {idx}: resultat invalide {result}")
            continue
        by_id[shadow_id]["result"] = result
        if result in {"win", "loss", "push", "void"}:
            by_id[shadow_id]["status"] = "settled"
        if str(item.get("notes") or "").strip():
            old_notes = str(by_id[shadow_id].get("notes") or "").strip()
            by_id[shadow_id]["notes"] = (old_notes + " | " if old_notes else "") + str(item.get("notes")).strip()
        counts[result] += 1
        updated += 1
    if not dry_run:
        write_ledger(rows, ledger_path)
    return {
        "ledger": ledger_path,
        "results_csv": results_csv,
        "dry_run": dry_run,
        "rows_updated": updated,
        "errors": errors,
        "result_counts": counts,
        "lab_only": True,
        "can_influence_picks": False,
    }


def print_summary(summary: Dict[str, Any]) -> None:
    print("Import resultats manuel Oracle Bot")
    print(f"- Ledger: {summary.get('ledger')}")
    print(f"- CSV resultats: {summary.get('results_csv')}")
    print(f"- Dry-run: {summary.get('dry_run')}")
    print(f"- Lignes mises a jour: {summary.get('rows_updated')}")
    print(f"- Erreurs: {len(summary.get('errors') or [])}")
    for error in summary.get("errors") or []:
        print(f"  - {error}")
    print(f"- Comptes resultats: {summary.get('result_counts')}")
    print("- Mode shadow : observation seulement, aucune mise conseillee.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Importe des resultats manuels dans le shadow ledger.")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--results-csv", required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        summary = import_manual_results(args.ledger, args.results_csv, dry_run=args.dry_run)
        print_summary(summary)
        return 0 if not summary["errors"] else 1
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
