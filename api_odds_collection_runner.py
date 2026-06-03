import argparse
import json
from typing import Any, Dict

from odds_shadow_selector import select_shadow_rows, write_summary
from odds_to_shadow import snapshots_to_shadow
from soccer_odds_sport_scanner import scan_sports
from the_odds_api_adapter import fetch_the_odds_api, filter_normalized_rows, normalize_the_odds_api_payload
from odds_normalizer import write_normalized_csv
from odds_source_config import load_odds_source_config


def collect(
    sport: str,
    regions: str,
    markets: str,
    output: str,
    allow_network: bool = False,
    near_close: bool = False,
    bookmaker: str = "",
    max_events: int = 0,
) -> Dict[str, Any]:
    if not allow_network:
        near_close_arg = " --near-close" if near_close else ""
        return {
            "dry_run": True,
            "message": "reseau refuse par defaut",
            "command": f"python the_odds_api_adapter.py --allow-network --sport {sport} --regions {regions} --markets {markets}{near_close_arg} --output {output}",
            "lab_only": True,
        }
    payload = fetch_the_odds_api(sport, regions, markets, load_odds_source_config())
    rows = normalize_the_odds_api_payload(payload, near_close=near_close)
    rows = filter_normalized_rows(rows, bookmaker=bookmaker, max_events=max_events)
    write_normalized_csv(rows, output)
    return {"dry_run": False, "rows": len(rows), "output": output, "lab_only": True}


def select(snapshots: str, output: str, summary_json: str = "", bookmaker: str = "", max_events: int = 0, one_side_per_event: bool = False) -> Dict[str, Any]:
    result = select_shadow_rows(snapshots, bookmaker=bookmaker, max_events=max_events, one_side_per_event=one_side_per_event)
    write_normalized_csv(result["rows"], output)
    if summary_json:
        write_summary(result["summary"], summary_json)
    return result["summary"]


def to_shadow(selection: str, ledger: str, apply: bool = False, strategy_name: str = "api_odds_shadow_v1") -> Dict[str, Any]:
    return snapshots_to_shadow("", ledger, selection_csv=selection, strategy_name=strategy_name, dry_run=not apply)


def full_pre_match(args) -> Dict[str, Any]:
    collect_path = args.output or "reports/api_odds_collect.csv"
    selection_path = "reports/api_shadow_selection.csv"
    summary_path = "reports/api_shadow_selection_summary.json"
    collected = collect(args.sport, args.regions, args.markets, collect_path, allow_network=args.allow_network, bookmaker=args.bookmaker, max_events=args.max_events)
    if collected.get("dry_run"):
        return {"collect": collected, "applied": False, "lab_only": True}
    selected = select(collect_path, selection_path, summary_path, bookmaker=args.bookmaker, max_events=args.max_events, one_side_per_event=True)
    shadow = to_shadow(selection_path, args.ledger, apply=args.apply, strategy_name=args.strategy_name)
    return {"collect": collected, "selection": selected, "to_shadow": shadow, "applied": args.apply, "lab_only": True}


def print_json(title: str, payload: Dict[str, Any]) -> None:
    print(title)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("- Observation shadow seulement, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Runner local de collecte API odds.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--scan-sports", action="store_true")
    group.add_argument("--collect", action="store_true")
    group.add_argument("--select", action="store_true")
    group.add_argument("--to-shadow", action="store_true")
    group.add_argument("--full-pre-match", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--sport", default="soccer_japan_j_league")
    parser.add_argument("--regions", default="eu")
    parser.add_argument("--markets", default="h2h")
    parser.add_argument("--output", default="")
    parser.add_argument("--snapshots", default="")
    parser.add_argument("--selection", default="")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--bookmaker", default="")
    parser.add_argument("--max-events", type=int, default=0)
    parser.add_argument("--one-side-per-event", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--strategy-name", default="api_odds_shadow_v1")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.scan_sports:
            payload = scan_sports(allow_network=args.allow_network, dry_run=not args.allow_network)
        elif args.collect:
            payload = collect(args.sport, args.regions, args.markets, args.output or "reports/api_odds_collect.csv", allow_network=args.allow_network, bookmaker=args.bookmaker, max_events=args.max_events)
        elif args.select:
            payload = select(args.snapshots, args.output or "reports/api_shadow_selection.csv", bookmaker=args.bookmaker, max_events=args.max_events, one_side_per_event=args.one_side_per_event)
        elif args.to_shadow:
            payload = to_shadow(args.selection, args.ledger, apply=args.apply, strategy_name=args.strategy_name)
        else:
            payload = full_pre_match(args)
        print_json("API Odds Collection Runner", payload)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
