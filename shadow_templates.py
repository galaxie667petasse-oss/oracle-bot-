import argparse
import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List

from shadow_ledger import CANDIDATE_IMPORT_COLUMNS, read_ledger


RESULT_COLUMNS = ["shadow_id", "result", "notes"]
CLOSING_COLUMNS = ["shadow_id", "closing_odds", "closing_source", "notes"]


def ensure_reports_path(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Les templates shadow ne doivent pas etre ecrits dans data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _write_template(path: str, columns: List[str], rows: Iterable[Dict[str, Any]], force: bool = False) -> Path:
    target = ensure_reports_path(path)
    if target.exists() and not force:
        raise FileExistsError(f"Template deja present: {target}. Utiliser --force pour remplacer.")
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})
    return target


def create_candidates_template(path: str, force: bool = False) -> Path:
    return _write_template(path, CANDIDATE_IMPORT_COLUMNS, [], force=force)


def create_closing_template(path: str, ledger: str = "", force: bool = False) -> Path:
    rows = []
    if ledger:
        for row in read_ledger(ledger):
            if not str(row.get("closing_odds") or "").strip():
                rows.append({"shadow_id": row.get("shadow_id", ""), "closing_odds": "", "closing_source": "", "notes": ""})
    return _write_template(path, CLOSING_COLUMNS, rows, force=force)


def create_results_template(path: str, ledger: str = "", force: bool = False) -> Path:
    rows = []
    if ledger:
        for row in read_ledger(ledger):
            if str(row.get("result") or "unknown").lower() == "unknown":
                rows.append({"shadow_id": row.get("shadow_id", ""), "result": "", "notes": ""})
    return _write_template(path, RESULT_COLUMNS, rows, force=force)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Genere des templates CSV shadow pour saisie manuelle.")
    parser.add_argument("--candidates-template", default="")
    parser.add_argument("--closing-template", default="")
    parser.add_argument("--results-template", default="")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        created = []
        if args.candidates_template:
            created.append(create_candidates_template(args.candidates_template, force=args.force))
        if args.closing_template:
            created.append(create_closing_template(args.closing_template, ledger=args.ledger, force=args.force))
        if args.results_template:
            created.append(create_results_template(args.results_template, ledger=args.ledger, force=args.force))
        if not created:
            raise ValueError("Aucun template demande.")
        print("Templates shadow Oracle Bot")
        for path in created:
            print(f"- Template ecrit: {path}")
        print("- Mode shadow : observation seulement, aucune mise conseillee.")
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
