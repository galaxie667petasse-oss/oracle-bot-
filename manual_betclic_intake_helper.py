import argparse
import csv
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from manual_odds_import import MANUAL_COLUMNS, normalize_manual_csv, read_manual_csv
from odds_normalizer import write_normalized_csv
from odds_to_shadow import snapshots_to_shadow


ALLOWED_SOURCES = {"manual", "betclic_manual"}


def _safe_path(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Les fichiers Betclic manuels doivent rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def write_betclic_template(path: str, date: str = "") -> Path:
    target = _safe_path(path)
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANUAL_COLUMNS)
        writer.writeheader()
        writer.writerow({
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            "source": "betclic_manual",
            "league": "",
            "match_date": date,
            "kickoff_time": "",
            "home_team": "",
            "away_team": "",
            "bookmaker": "Betclic",
            "market_type": "h2h",
            "side": "home",
            "odds": "",
            "is_live": "false",
            "is_near_close": "false",
            "notes": "observation manuelle visible, aucune mise",
        })
    return target


def validate_betclic_csv(path: str) -> Dict[str, Any]:
    rows = normalize_manual_csv(path)
    errors: List[str] = []
    invalid_lines = set()
    for idx, row in enumerate(rows, start=2):
        source = str(row.get("source") or "").strip().lower()
        book = str(row.get("bookmaker") or "").strip()
        if source not in ALLOWED_SOURCES:
            errors.append(f"ligne {idx}: source doit etre manual ou betclic_manual")
            invalid_lines.add(idx)
        if not book:
            errors.append(f"ligne {idx}: bookmaker manquant")
            invalid_lines.add(idx)
        if row.get("validation_status") != "valid":
            errors.append(f"ligne {idx}: {row.get('validation_reason')}")
            invalid_lines.add(idx)
    return {
        "input": path,
        "rows_read": len(rows),
        "valid_rows": len(rows) - len(invalid_lines),
        "errors": errors,
        "near_close_rows": sum(1 for row in rows if str(row.get("is_near_close") or "").lower() == "true"),
        "taken_rows": sum(1 for row in rows if str(row.get("is_near_close") or "").lower() != "true"),
        "rows": rows,
        "lab_only": True,
        "can_influence_picks": False,
    }


def to_matchday_pack(input_csv: str, pack: str) -> Dict[str, Any]:
    report = validate_betclic_csv(input_csv)
    if report["errors"]:
        return {"pack": pack, "created": False, "errors": report["errors"], "lab_only": True}
    target = Path(pack)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le pack matchday doit rester hors data/.")
    target.mkdir(parents=True, exist_ok=True)
    rows = read_manual_csv(input_csv)
    taken = [row for row in rows if str(row.get("is_near_close") or "").lower() != "true"]
    near = [row for row in rows if str(row.get("is_near_close") or "").lower() == "true"]
    for filename, subset in (("matchday_manual_odds.csv", taken), ("matchday_near_close.csv", near)):
        with (target / filename).open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=MANUAL_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(subset)
    with (target / "matchday_results.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["shadow_id", "result", "notes"])
        writer.writeheader()
    return {"pack": str(target), "created": True, "taken_rows": len(taken), "near_close_rows": len(near), "lab_only": True}


def to_shadow(input_csv: str, ledger: str, apply: bool = False) -> Dict[str, Any]:
    report = validate_betclic_csv(input_csv)
    if report["errors"]:
        return {"applied": False, "errors": report["errors"], "lab_only": True}
    with tempfile.TemporaryDirectory(prefix="oracle_betclic_") as tmp:
        normalized = Path(tmp) / "betclic_normalized.csv"
        write_normalized_csv(report["rows"], str(normalized))
        return snapshots_to_shadow(str(normalized), ledger, strategy_name="betclic_manual_shadow", dry_run=not apply)


def print_report(title: str, report: Dict[str, Any]) -> None:
    print(title)
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, ensure_ascii=False, indent=2))
    print("- Observation manuelle seulement, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Assistant intake manuel Betclic, laboratoire local.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--template", default="")
    group.add_argument("--validate", default="")
    group.add_argument("--to-matchday-pack", default="")
    group.add_argument("--to-shadow", default="")
    parser.add_argument("--date", default="")
    parser.add_argument("--pack", default="")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.template:
            print(f"- Template Betclic ecrit: {write_betclic_template(args.template, args.date)}")
        elif args.validate:
            print_report("Validation Betclic manuel", validate_betclic_csv(args.validate))
        elif args.to_matchday_pack:
            if not args.pack:
                raise ValueError("--pack requis avec --to-matchday-pack")
            print_report("Pack matchday Betclic", to_matchday_pack(args.to_matchday_pack, args.pack))
        elif args.to_shadow:
            print_report("Betclic vers shadow", to_shadow(args.to_shadow, args.ledger, apply=args.apply and not args.dry_run))
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
