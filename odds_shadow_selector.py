import argparse
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from odds_normalizer import ODDS_COLUMNS, write_normalized_csv
from odds_snapshot_store import load_snapshots
from shadow_ledger import read_ledger
from the_odds_api_adapter import filter_normalized_rows


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Les sorties selector doivent rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _event_count(rows: List[Dict[str, Any]]) -> int:
    return len({row.get("source_event_id") or (row.get("match_date"), row.get("league"), row.get("home_team"), row.get("away_team")) for row in rows})


def _event_key(row: Dict[str, Any]) -> tuple:
    return (
        str(row.get("match_date") or "").strip().lower(),
        str(row.get("league") or "").strip().lower(),
        str(row.get("home_team") or "").strip().lower(),
        str(row.get("away_team") or "").strip().lower(),
    )


def _date_in_window(row: Dict[str, Any], min_days_ahead: int = -1, max_days_ahead: int = -1) -> bool:
    if min_days_ahead < 0 and max_days_ahead < 0:
        return True
    text = str(row.get("match_date") or "").strip()
    if not text:
        return False
    try:
        date_value = datetime.fromisoformat(text[:10]).date()
    except Exception:
        return False
    today = datetime.now().date()
    if min_days_ahead >= 0 and date_value < today + timedelta(days=min_days_ahead):
        return False
    if max_days_ahead >= 0 and date_value > today + timedelta(days=max_days_ahead):
        return False
    return True


def _limit_by_field(rows: List[Dict[str, Any]], field: str, limit: int) -> List[Dict[str, Any]]:
    if not limit:
        return rows
    counts: Dict[str, int] = {}
    out = []
    for row in rows:
        key = str(row.get(field) or "")
        if counts.get(key, 0) >= limit:
            continue
        counts[key] = counts.get(key, 0) + 1
        out.append(row)
    return out


def select_shadow_rows(
    snapshots_path: str,
    market: str = "",
    league: str = "",
    bookmaker: str = "",
    date_from: str = "",
    date_to: str = "",
    max_events: int = 0,
    one_side_per_event: bool = False,
    prefer_side: str = "",
    prefer_bookmaker: str = "",
    include_draw: bool = False,
    exclude_events_from_ledger: str = "",
    min_days_ahead: int = -1,
    max_days_ahead: int = -1,
    max_per_league: int = 0,
    max_per_bookmaker: int = 0,
    prefer_earliest: bool = False,
) -> Dict[str, Any]:
    rows = load_snapshots(snapshots_path)
    excluded_events = {_event_key(row) for row in read_ledger(exclude_events_from_ledger)} if exclude_events_from_ledger else set()
    valid = []
    excluded_existing = 0
    for row in rows:
        if row.get("validation_status") != "valid":
            continue
        if str(row.get("is_near_close") or "").lower() == "true":
            continue
        if str(row.get("is_live") or "").lower() == "true":
            continue
        if market and row.get("market_type") != market:
            continue
        if league and row.get("league") != league:
            continue
        if excluded_events and _event_key(row) in excluded_events:
            excluded_existing += 1
            continue
        if not _date_in_window(row, min_days_ahead=min_days_ahead, max_days_ahead=max_days_ahead):
            continue
        valid.append(row)
    if prefer_earliest:
        valid = sorted(valid, key=lambda row: (row.get("match_date") or "", row.get("kickoff_time") or "", row.get("source_event_id") or "", row.get("bookmaker") or ""))
    selected = filter_normalized_rows(
        valid,
        bookmaker=bookmaker,
        date_from=date_from,
        date_to=date_to,
        max_events=max_events,
        one_side_per_event=one_side_per_event,
        prefer_bookmaker=prefer_bookmaker or bookmaker,
        prefer_side=prefer_side,
        prefer_market=market or "h2h",
        include_draw=include_draw,
    )
    if prefer_earliest:
        selected = sorted(selected, key=lambda row: (row.get("match_date") or "", row.get("kickoff_time") or "", row.get("source_event_id") or "", row.get("bookmaker") or ""))
    selected = _limit_by_field(selected, "league", max_per_league)
    selected = _limit_by_field(selected, "bookmaker", max_per_bookmaker)
    warnings = []
    if not selected:
        warnings.append("aucune ligne selectionnee")
    return {
        "rows": selected,
        "summary": {
            "snapshots": snapshots_path,
            "rows_read": len(rows),
            "valid_rows": len(valid),
            "selected_rows": len(selected),
            "distinct_events": _event_count(selected),
            "excluded_existing_events_rows": excluded_existing,
            "bookmakers": sorted({row.get("bookmaker") for row in selected if row.get("bookmaker")}),
            "leagues": sorted({row.get("league") for row in selected if row.get("league")}),
            "markets": sorted({row.get("market_type") for row in selected if row.get("market_type")}),
            "warnings": warnings,
            "lab_only": True,
            "can_influence_picks": False,
        },
    }


def write_summary(summary: Dict[str, Any], path: str) -> Path:
    target = _safe_output(path)
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def print_report(summary: Dict[str, Any]) -> None:
    print("Selection shadow depuis snapshots")
    print(f"- Lignes lues: {summary.get('rows_read')}")
    print(f"- Lignes valides candidates: {summary.get('valid_rows')}")
    print(f"- Lignes selectionnees: {summary.get('selected_rows')}")
    print(f"- Events distincts: {summary.get('distinct_events')}")
    print("- Observation shadow seulement, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Selectionne des observations shadow depuis snapshots.")
    parser.add_argument("--snapshots", required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--summary-json", default="")
    parser.add_argument("--bookmaker", default="")
    parser.add_argument("--market", default="")
    parser.add_argument("--league", default="")
    parser.add_argument("--date-from", default="")
    parser.add_argument("--date-to", default="")
    parser.add_argument("--max-events", type=int, default=0)
    parser.add_argument("--one-side-per-event", action="store_true")
    parser.add_argument("--prefer-side", default="")
    parser.add_argument("--prefer-bookmaker", default="")
    parser.add_argument("--include-draw", action="store_true")
    parser.add_argument("--exclude-events-from-ledger", default="")
    parser.add_argument("--min-days-ahead", type=int, default=-1)
    parser.add_argument("--max-days-ahead", type=int, default=-1)
    parser.add_argument("--max-per-league", type=int, default=0)
    parser.add_argument("--max-per-bookmaker", type=int, default=0)
    parser.add_argument("--prefer-earliest", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        result = select_shadow_rows(
            args.snapshots,
            market=args.market,
            league=args.league,
            bookmaker=args.bookmaker,
            date_from=args.date_from,
            date_to=args.date_to,
            max_events=args.max_events,
            one_side_per_event=args.one_side_per_event,
            prefer_side=args.prefer_side,
            prefer_bookmaker=args.prefer_bookmaker,
            include_draw=args.include_draw,
            exclude_events_from_ledger=args.exclude_events_from_ledger,
            min_days_ahead=args.min_days_ahead,
            max_days_ahead=args.max_days_ahead,
            max_per_league=args.max_per_league,
            max_per_bookmaker=args.max_per_bookmaker,
            prefer_earliest=args.prefer_earliest,
        )
        if args.output:
            write_normalized_csv(result["rows"], args.output)
        if args.summary_json:
            write_summary(result["summary"], args.summary_json)
        print_report(result["summary"])
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
