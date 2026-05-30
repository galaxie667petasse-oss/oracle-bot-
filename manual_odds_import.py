import argparse
import csv
import json
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


def ensure_safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Les sorties odds manuelles doivent rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def write_template(path: str) -> Path:
    target = ensure_safe_output(path)
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANUAL_COLUMNS)
        writer.writeheader()
    return target


def read_manual_csv(path: str) -> List[Dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"CSV manuel introuvable: {path}")
    with source.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        missing = [column for column in MANUAL_COLUMNS if column not in (reader.fieldnames or [])]
        if missing:
            raise ValueError("Colonnes manquantes dans le CSV manuel: " + ", ".join(missing))
        return [dict(row) for row in reader]


def normalize_manual_csv(input_path: str) -> List[Dict[str, Any]]:
    rows = read_manual_csv(input_path)
    normalized = []
    for row in rows:
        payload = dict(row)
        payload["source"] = payload.get("source") or "manual_csv"
        payload["raw_payload_ref"] = payload.get("notes") or ""
        normalized.append(payload)
    return normalize_odds_rows(normalized, source="manual_csv")


def split_rows(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    return {
        "valid": [row for row in rows if row.get("validation_status") == "valid"],
        "rejected": [row for row in rows if row.get("validation_status") != "valid"],
    }


def build_summary(input_path: str, rows: List[Dict[str, Any]], output_path: str = "", store_path: str = "") -> Dict[str, Any]:
    split = split_rows(rows)
    rejection_reasons: Dict[str, int] = {}
    for row in split["rejected"]:
        reason = row.get("validation_reason") or "inconnu"
        rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
    return {
        "input_path": input_path,
        "rows_read": len(rows),
        "valid_rows": len(split["valid"]),
        "rejected_rows": len(split["rejected"]),
        "rejection_reasons": rejection_reasons,
        "markets": sorted({row.get("market_type") for row in rows if row.get("market_type")}),
        "sides": sorted({row.get("side") for row in rows if row.get("side")}),
        "bookmakers": sorted({row.get("bookmaker") for row in rows if row.get("bookmaker")}),
        "near_close_count": sum(1 for row in rows if str(row.get("is_near_close") or "").lower() == "true"),
        "taken_count": sum(1 for row in rows if str(row.get("is_near_close") or "").lower() != "true"),
        "invalid_odds_count": sum(1 for row in split["rejected"] if "cote" in str(row.get("validation_reason") or "").lower()),
        "output_path": output_path,
        "store_path": store_path,
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_rejects(rows: List[Dict[str, Any]], path: str) -> Path:
    return write_normalized_csv(split_rows(rows)["rejected"], path)


def write_valid(rows: List[Dict[str, Any]], path: str) -> Path:
    return write_normalized_csv(split_rows(rows)["valid"], path)


def write_summary_json(summary: Dict[str, Any], path: str) -> Path:
    target = ensure_safe_output(path)
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


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
    print("- Observation de marche seulement, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Import CSV manuel de cotes vers snapshots Oracle.")
    parser.add_argument("--input", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--store", default="")
    parser.add_argument("--template", default="")
    parser.add_argument("--rejects-output", default="")
    parser.add_argument("--valid-output", default="")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--summary-json", default="")
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
        split = split_rows(rows)
        if args.output:
            print(f"- CSV normalise ecrit: {write_normalized_csv(rows, args.output)}")
        if args.valid_output:
            print(f"- CSV lignes valides ecrit: {write_valid(rows, args.valid_output)}")
        if args.rejects_output:
            print(f"- CSV rejets ecrit: {write_rejects(rows, args.rejects_output)}")
        summary = build_summary(args.input, rows, output_path=args.output or args.valid_output, store_path=args.store)
        if args.summary_json:
            print(f"- Resume JSON ecrit: {write_summary_json(summary, args.summary_json)}")
        if args.strict and split["rejected"]:
            print("- Mode strict: import refuse car au moins une ligne est rejetee.")
            return 2
        if args.store:
            report = append_snapshot_rows(args.store, split["valid"])
            print(f"- Store mis a jour: {report['store']} ({report['total_rows']} lignes)")
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
