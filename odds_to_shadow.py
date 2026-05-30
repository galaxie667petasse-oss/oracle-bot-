import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from odds_normalizer import normalize_decimal_odds
from odds_snapshot_store import load_snapshots
from shadow_ledger import add_shadow_entry, read_ledger


def _shadow_key(row: Dict[str, Any]) -> tuple:
    return (
        str(row.get("match_date") or "").strip().lower(),
        str(row.get("league") or "").strip().lower(),
        str(row.get("home_team") or "").strip().lower(),
        str(row.get("away_team") or "").strip().lower(),
        str(row.get("market_type") or "").strip().lower(),
        str(row.get("side") or "").strip().lower(),
        str(row.get("taken_odds") or row.get("odds") or "").strip().replace(",", "."),
    )


def snapshots_to_shadow(
    snapshots_path: str,
    ledger_path: str,
    mode: str = "observation",
    strategy_name: str = "odds_snapshot_watch",
    min_odds: float = 1.01,
    max_odds: float = 100.0,
    include_near_close: bool = False,
    source_filter: str = "",
    league_filter: str = "",
    bookmaker_filter: str = "",
    market_filter: str = "",
    max_rows: int = 0,
    reason_prefix: str = "observation depuis snapshot de cotes",
    dry_run: bool = False,
) -> Dict[str, Any]:
    snapshots = load_snapshots(snapshots_path)
    existing = read_ledger(ledger_path)
    existing_keys = {_shadow_key(row) for row in existing}
    added = 0
    ignored = 0
    near_close_ignored = 0
    invalid_ignored = 0
    duplicates = 0
    errors: List[str] = []
    would_add: List[Dict[str, Any]] = []
    status = mode if mode in {"observation", "watchlist", "rejected"} else "observation"
    for row in snapshots:
        try:
            if row.get("validation_status") != "valid":
                ignored += 1
                invalid_ignored += 1
                continue
            if str(row.get("is_near_close") or "").lower() == "true" and not include_near_close:
                ignored += 1
                near_close_ignored += 1
                continue
            if source_filter and row.get("source") != source_filter:
                ignored += 1
                continue
            if league_filter and row.get("league") != league_filter:
                ignored += 1
                continue
            if bookmaker_filter and row.get("bookmaker") != bookmaker_filter:
                ignored += 1
                continue
            if market_filter and row.get("market_type") != market_filter:
                ignored += 1
                continue
            odds = normalize_decimal_odds(row.get("odds"))
            if odds < min_odds or odds > max_odds:
                ignored += 1
                continue
            entry = {
                "match_date": row.get("match_date"),
                "league": row.get("league"),
                "home_team": row.get("home_team"),
                "away_team": row.get("away_team"),
                "market_type": row.get("market_type"),
                "side": row.get("side"),
                "taken_odds": odds,
                "bookmaker": row.get("bookmaker"),
                "strategy_name": strategy_name,
                "reason": f"{reason_prefix}, aucune mise",
                "status": status,
                "notes": f"source={row.get('source')}; snapshot_id={row.get('snapshot_id')}",
            }
            key = _shadow_key(entry)
            if key in existing_keys:
                duplicates += 1
                continue
            if dry_run:
                would_add.append(entry)
            else:
                add_shadow_entry(ledger_path, **entry)
                existing_keys.add(key)
            added += 1
            if max_rows and added >= max_rows:
                break
        except Exception as exc:
            errors.append(str(exc))
    return {
        "snapshots": snapshots_path,
        "ledger": ledger_path,
        "rows_read": len(snapshots),
        "snapshots_convertible": added + duplicates,
        "rows_added": added,
        "rows_ignored": ignored,
        "near_close_ignored": near_close_ignored,
        "invalid_ignored": invalid_ignored,
        "duplicates_ignored": duplicates,
        "errors": errors,
        "dry_run": dry_run,
        "would_add": would_add[:20],
        "lab_only": True,
        "can_influence_picks": False,
    }


def print_report(report: Dict[str, Any]) -> None:
    print("Odds to Shadow Oracle")
    print(f"- Snapshots lus: {report.get('rows_read')}")
    print(f"- Observations shadow {'simulees' if report.get('dry_run') else 'ajoutees'}: {report.get('rows_added')}")
    print(f"- Lignes ignorees: {report.get('rows_ignored')}")
    print(f"- Near-close ignores: {report.get('near_close_ignored')}")
    print(f"- Invalides ignores: {report.get('invalid_ignored')}")
    print(f"- Doublons ignores: {report.get('duplicates_ignored')}")
    print(f"- Erreurs: {len(report.get('errors') or [])}")
    print("- Statut: conversion en observation shadow seulement, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Convertit des snapshots de cotes en observations shadow.")
    parser.add_argument("--snapshots", required=True)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--mode", default="observation")
    parser.add_argument("--strategy-name", default="odds_snapshot_watch")
    parser.add_argument("--min-odds", type=float, default=1.01)
    parser.add_argument("--max-odds", type=float, default=100.0)
    parser.add_argument("--taken-only", action="store_true", help="Exclut les snapshots near-close (defaut)")
    parser.add_argument("--include-near-close", action="store_true", help="Autorise explicitement la conversion des near-close")
    parser.add_argument("--source-filter", default="")
    parser.add_argument("--league-filter", default="")
    parser.add_argument("--bookmaker-filter", default="")
    parser.add_argument("--market-filter", default="")
    parser.add_argument("--max-rows", type=int, default=0)
    parser.add_argument("--reason-prefix", default="observation depuis snapshot de cotes")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", default="")
    parser.add_argument("--summary-json", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = snapshots_to_shadow(
            args.snapshots,
            args.ledger,
            mode=args.mode,
            strategy_name=args.strategy_name,
            min_odds=args.min_odds,
            max_odds=args.max_odds,
            include_near_close=args.include_near_close,
            source_filter=args.source_filter,
            league_filter=args.league_filter,
            bookmaker_filter=args.bookmaker_filter,
            market_filter=args.market_filter,
            max_rows=args.max_rows,
            reason_prefix=args.reason_prefix,
            dry_run=args.dry_run,
        )
        print_report(report)
        output_path = args.summary_json or args.report
        if output_path:
            target = Path(output_path)
            if "data" in [part.lower() for part in target.parts]:
                raise ValueError("Le rapport odds_to_shadow doit rester hors data/.")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
