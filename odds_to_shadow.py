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
    dry_run: bool = False,
) -> Dict[str, Any]:
    snapshots = load_snapshots(snapshots_path)
    existing = read_ledger(ledger_path)
    existing_keys = {_shadow_key(row) for row in existing}
    added = 0
    ignored = 0
    duplicates = 0
    errors: List[str] = []
    would_add: List[Dict[str, Any]] = []
    status = mode if mode in {"observation", "watchlist", "rejected"} else "observation"
    for row in snapshots:
        try:
            if row.get("validation_status") != "valid":
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
                "reason": "observation depuis snapshot de cotes, aucune mise conseillee",
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
        except Exception as exc:
            errors.append(str(exc))
    return {
        "snapshots": snapshots_path,
        "ledger": ledger_path,
        "rows_read": len(snapshots),
        "rows_added": added,
        "rows_ignored": ignored,
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
    print(f"- Doublons ignores: {report.get('duplicates_ignored')}")
    print(f"- Erreurs: {len(report.get('errors') or [])}")
    print("- Statut: observation shadow, aucune mise conseillee.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Convertit des snapshots de cotes en observations shadow.")
    parser.add_argument("--snapshots", required=True)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--mode", default="observation")
    parser.add_argument("--strategy-name", default="odds_snapshot_watch")
    parser.add_argument("--min-odds", type=float, default=1.01)
    parser.add_argument("--max-odds", type=float, default=100.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", default="")
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
            dry_run=args.dry_run,
        )
        print_report(report)
        if args.report:
            target = Path(args.report)
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
