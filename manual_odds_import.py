import argparse
import csv
from pathlib import Path
from typing import Any, Dict, List

from odds_normalizer import ODDS_COLUMNS, normalize_odds_rows, write_normalized_csv
from odds_snapshot_store import append_snapshot_rows


MANUAL_COLUMNS = [
    "captured_at",
    "source",
    "league",
    "match_date",
    "kickoff_time",
    "home_team",
    "away_team",
    "bookmaker",
    "market_type",
    "side",
    "odds",
    "is_live",
    "is_near_close",
    "notes",
]


def write_template(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le template manuel doit etre ecrit hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANUAL_COLUMNS)
        writer.writeheader()
    return target


def read_manual_csv(path: str) -> List[Dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"CSV manuel introuvable: {path}")
    with source.open(newline="", encoding="utf-8-sig") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def normalize_manual_csv(input_path: str) -> List[Dict[str, Any]]:
    rows = read_manual_csv(input_path)
    normalized = []
    for row in rows:
        payload = dict(row)
        payload["source"] = payload.get("source") or "manual_csv"
        payload["raw_payload_ref"] = payload.get("notes") or ""
        normalized.append(payload)
    return normalize_odds_rows(normalized, source="manual_csv")


def print_report(rows: List[Dict[str, Any]]) -> None:
    valid = sum(1 for row in rows if row.get("validation_status") == "valid")
    invalid = len(rows) - valid
    print("Import manuel de cotes Oracle")
    print(f"- Lignes lues: {len(rows)}")
    print(f"- Lignes valides: {valid}")
    print(f"- Lignes rejetees: {invalid}")
    if invalid:
        for row in rows:
            if row.get("validation_status") != "valid":
                print(f"  - Rejet: {row.get('home_team')} - {row.get('away_team')} | {row.get('validation_reason')}")
    print("- Observation de marche seulement, aucune mise conseillee.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Import CSV manuel de cotes vers snapshots Oracle.")
    parser.add_argument("--input", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--store", default="")
    parser.add_argument("--template", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.template:
            print(f"- Template manuel ecrit: {write_template(args.template)}")
            return 0
        if not args.input:
            raise ValueError("--input ou --template requis")
        rows = normalize_manual_csv(args.input)
        print_report(rows)
        if args.output:
            print(f"- CSV normalise ecrit: {write_normalized_csv(rows, args.output)}")
        if args.store:
            report = append_snapshot_rows(args.store, rows)
            print(f"- Store mis a jour: {report['store']} ({report['total_rows']} lignes)")
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
