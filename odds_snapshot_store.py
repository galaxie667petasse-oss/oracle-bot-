import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from odds_normalizer import ODDS_COLUMNS, normalize_odds_rows


DEFAULT_STORE = "reports/odds_snapshots.csv"


def ensure_reports_path(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le store de snapshots ne doit jamais etre ecrit dans data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def init_store(path: str = DEFAULT_STORE) -> Path:
    target = ensure_reports_path(path)
    if not target.exists():
        with target.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=ODDS_COLUMNS)
            writer.writeheader()
    return target


def load_snapshots(path: str = DEFAULT_STORE) -> List[Dict[str, str]]:
    target = Path(path)
    if not target.exists():
        return []
    with target.open(newline="", encoding="utf-8-sig") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def write_snapshots(path: str, rows: Iterable[Dict[str, Any]]) -> Path:
    target = ensure_reports_path(path)
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=ODDS_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in ODDS_COLUMNS})
    return target


def append_snapshot_rows(store_path: str, rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    init_store(store_path)
    existing = load_snapshots(store_path)
    normalized = normalize_odds_rows(rows, source="manual_csv")
    all_rows = existing + normalized
    write_snapshots(store_path, all_rows)
    return {
        "store": store_path,
        "existing_rows": len(existing),
        "appended_rows": len(normalized),
        "total_rows": len(all_rows),
        "invalid_rows": sum(1 for row in normalized if row.get("validation_status") != "valid"),
        "lab_only": True,
    }


def append_csv(store_path: str, csv_path: str) -> Dict[str, Any]:
    source = Path(csv_path)
    if not source.exists():
        raise FileNotFoundError(f"CSV snapshots introuvable: {csv_path}")
    with source.open(newline="", encoding="utf-8-sig") as fh:
        rows = [dict(row) for row in csv.DictReader(fh)]
    return append_snapshot_rows(store_path, rows)


def summarize_snapshots(path: str = DEFAULT_STORE) -> Dict[str, Any]:
    rows = load_snapshots(path)
    ids = [row.get("snapshot_id", "") for row in rows]
    valid_rows = [row for row in rows if row.get("validation_status") == "valid"]
    dates = [row.get("match_date", "") for row in rows if row.get("match_date")]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "store": path,
        "rows_total": len(rows),
        "valid_rows": len(valid_rows),
        "invalid_rows": len(rows) - len(valid_rows),
        "sources": sorted({row.get("source", "") for row in rows if row.get("source")}),
        "bookmakers": sorted({row.get("bookmaker", "") for row in rows if row.get("bookmaker")}),
        "leagues": sorted({row.get("league", "") for row in rows if row.get("league")}),
        "markets": sorted({row.get("market_type", "") for row in rows if row.get("market_type")}),
        "near_close_rows": sum(1 for row in rows if str(row.get("is_near_close", "")).lower() == "true"),
        "date_min": min(dates) if dates else None,
        "date_max": max(dates) if dates else None,
        "duplicates": len(ids) - len(set(ids)),
        "lab_only": True,
        "can_influence_picks": False,
    }


def dedupe_snapshots(path: str = DEFAULT_STORE) -> Dict[str, Any]:
    rows = load_snapshots(path)
    seen = set()
    deduped = []
    for row in rows:
        key = row.get("snapshot_id") or json.dumps(row, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    write_snapshots(path, deduped)
    return {"store": path, "before": len(rows), "after": len(deduped), "removed": len(rows) - len(deduped)}


def export_snapshots(path: str, output: str) -> Path:
    rows = load_snapshots(path)
    return write_snapshots(output, rows)


def print_summary(summary: Dict[str, Any]) -> None:
    print("Resume snapshots de cotes Oracle")
    print(f"- Store: {summary.get('store')}")
    print(f"- Lignes totales: {summary.get('rows_total')}")
    print(f"- Lignes valides: {summary.get('valid_rows')}")
    print(f"- Lignes invalides: {summary.get('invalid_rows')}")
    print(f"- Sources: {', '.join(summary.get('sources') or []) or 'aucune'}")
    print(f"- Bookmakers: {', '.join(summary.get('bookmakers') or []) or 'aucun'}")
    print(f"- Marches: {', '.join(summary.get('markets') or []) or 'aucun'}")
    print(f"- Snapshots near-close: {summary.get('near_close_rows')}")
    print(f"- Doublons: {summary.get('duplicates')}")
    print("- Laboratoire local: aucune mise conseillee.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Store local des snapshots de cotes Oracle.")
    parser.add_argument("--store", default=DEFAULT_STORE)
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--append", default="")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--dedupe", action="store_true")
    parser.add_argument("--export", default="")
    parser.add_argument("--output", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.init:
            print(f"- Store initialise: {init_store(args.store)}")
        if args.append:
            report = append_csv(args.store, args.append)
            print(f"- Lignes ajoutees: {report['appended_rows']}")
            print(f"- Lignes invalides ajoutees: {report['invalid_rows']}")
        if args.dedupe:
            report = dedupe_snapshots(args.store)
            print(f"- Doublons retires: {report['removed']}")
        if args.export:
            print(f"- Export snapshots ecrit: {export_snapshots(args.store, args.export)}")
        if args.summary or not any((args.init, args.append, args.dedupe, args.export)):
            summary = summarize_snapshots(args.store)
            print_summary(summary)
            if args.output:
                target = ensure_reports_path(args.output)
                target.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
