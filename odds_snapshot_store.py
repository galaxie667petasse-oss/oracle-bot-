import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from odds_normalizer import ODDS_COLUMNS, VALID_MARKETS, VALID_SIDES, normalize_decimal_odds, normalize_odds_rows, validate_odds_row


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
    taken_rows = [row for row in valid_rows if str(row.get("is_near_close", "")).lower() != "true"]
    near_close_rows = [row for row in valid_rows if str(row.get("is_near_close", "")).lower() == "true"]
    dates = [row.get("match_date", "") for row in rows if row.get("match_date")]
    matches = {
        (row.get("match_date"), row.get("league"), row.get("normalized_home") or row.get("home_team"), row.get("normalized_away") or row.get("away_team"))
        for row in valid_rows
    }
    if not rows:
        clv_potential = "no_snapshots"
    elif taken_rows and near_close_rows:
        clv_potential = "taken_and_near_close_possible"
    elif near_close_rows:
        clv_potential = "near_close_only"
    else:
        clv_potential = "taken_only"
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
        "taken_count": len(taken_rows),
        "near_close_rows": len(near_close_rows),
        "date_min": min(dates) if dates else None,
        "date_max": max(dates) if dates else None,
        "matches_count": len(matches),
        "markets_count": len({row.get("market_type") for row in valid_rows if row.get("market_type")}),
        "duplicates": len(ids) - len(set(ids)),
        "duplicate_count": len(ids) - len(set(ids)),
        "clv_readiness_potential": clv_potential,
        "lab_only": True,
        "can_influence_picks": False,
    }


def _parse_date(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        datetime.fromisoformat(text[:10])
        return True
    except Exception:
        return False


def validate_store(path: str = DEFAULT_STORE) -> Dict[str, Any]:
    rows = load_snapshots(path)
    errors: List[str] = []
    warnings: List[str] = []
    if not Path(path).exists():
        warnings.append("store absent")
    ids = []
    for idx, row in enumerate(rows, start=2):
        missing = [column for column in ODDS_COLUMNS if column not in row]
        if missing:
            errors.append(f"ligne {idx}: colonnes manquantes {', '.join(missing)}")
            continue
        ids.append(row.get("snapshot_id") or "")
        try:
            normalize_decimal_odds(row.get("odds"))
        except Exception as exc:
            errors.append(f"ligne {idx}: odds invalide ({exc})")
        if not _parse_date(row.get("captured_at")):
            errors.append(f"ligne {idx}: captured_at invalide")
        if not _parse_date(row.get("match_date")):
            errors.append(f"ligne {idx}: match_date invalide")
        if row.get("market_type") not in VALID_MARKETS:
            errors.append(f"ligne {idx}: market_type invalide")
        if row.get("side") not in VALID_SIDES:
            errors.append(f"ligne {idx}: side invalide")
        if str(row.get("is_near_close") or "").lower() not in {"true", "false", ""}:
            errors.append(f"ligne {idx}: is_near_close invalide")
        if not row.get("normalized_home") or not row.get("normalized_away"):
            warnings.append(f"ligne {idx}: equipes normalisees absentes")
    duplicate_count = len(ids) - len(set(ids))
    if duplicate_count:
        warnings.append(f"doublons snapshot_id: {duplicate_count}")
    return {
        "store": path,
        "rows_total": len(rows),
        "errors": errors,
        "warnings": warnings,
        "duplicate_count": duplicate_count,
        "valid": not errors,
        "summary": summarize_snapshots(path),
        "lab_only": True,
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


def repair_dedupe(path: str = DEFAULT_STORE) -> Dict[str, Any]:
    return dedupe_snapshots(path)


def filter_snapshots(
    path: str = DEFAULT_STORE,
    market: str = "",
    league: str = "",
    source: str = "",
    near_close_only: bool = False,
) -> List[Dict[str, str]]:
    rows = load_snapshots(path)
    out = []
    for row in rows:
        if market and row.get("market_type") != market:
            continue
        if league and row.get("league") != league:
            continue
        if source and row.get("source") != source:
            continue
        if near_close_only and str(row.get("is_near_close") or "").lower() != "true":
            continue
        out.append(row)
    return out


def export_near_close(path: str, output: str) -> Path:
    return write_snapshots(output, filter_snapshots(path, near_close_only=True))


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
    print(f"- Snapshots taken: {summary.get('taken_count')}")
    print(f"- Potentiel CLV: {summary.get('clv_readiness_potential')}")
    print(f"- Doublons: {summary.get('duplicates')}")
    print("- Laboratoire local: aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Store local des snapshots de cotes Oracle.")
    parser.add_argument("--store", default=DEFAULT_STORE)
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--append", default="")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--dedupe", action="store_true")
    parser.add_argument("--repair-dedupe", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--filter", action="store_true")
    parser.add_argument("--market", default="")
    parser.add_argument("--league", default="")
    parser.add_argument("--source", default="")
    parser.add_argument("--near-close-only", action="store_true")
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
        if args.dedupe or args.repair_dedupe:
            report = dedupe_snapshots(args.store)
            print(f"- Doublons retires: {report['removed']}")
        if args.validate:
            report = validate_store(args.store)
            print(f"- Validation store: {'OK' if report['valid'] else 'erreurs'}")
            for error in report["errors"]:
                print(f"  - Erreur: {error}")
            for warning in report["warnings"]:
                print(f"  - Warning: {warning}")
            if args.output:
                target = ensure_reports_path(args.output)
                target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if args.filter:
            if not args.output:
                raise ValueError("--output requis avec --filter")
            rows = filter_snapshots(args.store, market=args.market, league=args.league, source=args.source, near_close_only=args.near_close_only)
            print(f"- Lignes filtrees: {len(rows)}")
            print(f"- Export filtre: {write_snapshots(args.output, rows)}")
        if args.near_close_only and not args.filter:
            if not args.output:
                raise ValueError("--output requis avec --near-close-only")
            print(f"- Export near-close: {export_near_close(args.store, args.output)}")
        if args.export:
            print(f"- Export snapshots ecrit: {export_snapshots(args.store, args.export)}")
        if args.summary or not any((args.init, args.append, args.dedupe, args.repair_dedupe, args.validate, args.filter, args.near_close_only, args.export)):
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
