import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from odds_normalizer import ODDS_COLUMNS, normalize_decimal_odds, write_normalized_csv


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("La selection API-Football doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _load_rows(path: str) -> List[Dict[str, str]]:
    if not Path(path).exists():
        return []
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _is_true(value: Any) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "oui"}


def _status_finished(row: Dict[str, Any]) -> bool:
    status_blob = " ".join([str(row.get("status") or ""), str(row.get("fixture_status") or ""), str(row.get("raw_payload_ref") or "")]).upper()
    return any(token in status_blob for token in ("STATUS=FT", "STATUS=AET", "STATUS=PEN", " FT", " AET", " PEN"))


def _row_ok(
    row: Dict[str, Any],
    market: str,
    bookmaker: str,
    include_live: bool,
    include_draw: bool,
    exclude_finished: bool,
    date_min: str,
) -> tuple[bool, str]:
    if row.get("validation_status") != "valid":
        return False, "ligne invalide"
    if not include_live and _is_true(row.get("is_live")):
        return False, "live exclu"
    if _is_true(row.get("is_near_close")):
        return False, "near-close exclu comme taken odds"
    if market and row.get("market_type") != market:
        return False, "marche exclu"
    if bookmaker and str(row.get("bookmaker") or "").lower() != bookmaker.lower():
        return False, "bookmaker exclu"
    if not include_draw and row.get("side") == "draw":
        return False, "draw exclu"
    if exclude_finished and _status_finished(row):
        return False, "match termine exclu"
    if date_min and str(row.get("match_date") or "") < date_min:
        return False, "date pas assez recente"
    if not row.get("home_team") or not row.get("away_team"):
        return False, "equipes absentes"
    try:
        normalize_decimal_odds(row.get("odds"))
    except Exception as exc:
        return False, str(exc)
    return True, "ok"


def select_valid_odds(
    odds_path: str,
    market: str = "h2h",
    bookmaker: str = "",
    prefer_bookmaker: str = "",
    max_events: int = 3,
    one_side_per_event: bool = True,
    prefer_side: str = "",
    include_draw: bool = False,
    include_live: bool = False,
    exclude_finished: bool = True,
    date_min: str = "",
) -> Dict[str, Any]:
    rows = _load_rows(odds_path)
    date_min = date_min or _today()
    valid: List[Dict[str, Any]] = []
    rejected: Dict[str, int] = {}
    for row in rows:
        ok, reason = _row_ok(row, market, bookmaker, include_live, include_draw, exclude_finished, date_min)
        if ok:
            valid.append(row)
        else:
            rejected[reason] = rejected.get(reason, 0) + 1
    if prefer_bookmaker:
        valid.sort(key=lambda row: (str(row.get("bookmaker") or "").lower() != prefer_bookmaker.lower(), row.get("match_date") or "", row.get("kickoff_time") or ""))
    else:
        valid.sort(key=lambda row: (row.get("match_date") or "", row.get("kickoff_time") or "", row.get("source_event_id") or ""))
    selected: List[Dict[str, Any]] = []
    seen_events = set()
    if one_side_per_event:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in valid:
            grouped.setdefault(str(row.get("source_event_id") or row.get("snapshot_id") or ""), []).append(row)
        side_order = [prefer_side] if prefer_side else []
        side_order.extend(["home", "away", "draw"])
        for event_id, event_rows in sorted(grouped.items(), key=lambda item: (item[1][0].get("match_date") or "", item[1][0].get("kickoff_time") or "", item[0])):
            chosen = None
            for side in side_order:
                if not side:
                    continue
                chosen = next((row for row in event_rows if row.get("side") == side), None)
                if chosen:
                    break
            selected.append(chosen or event_rows[0])
            seen_events.add(event_id)
            if max_events and len(selected) >= max_events:
                break
    else:
        for row in valid:
            selected.append(row)
            seen_events.add(str(row.get("source_event_id") or row.get("snapshot_id") or ""))
            if max_events and len(seen_events) >= max_events:
                break
    return {
        "input": odds_path,
        "rows_read": len(rows),
        "valid_candidates": len(valid),
        "selected_rows": len(selected),
        "distinct_events": len({row.get("source_event_id") for row in selected if row.get("source_event_id")}),
        "rejection_reasons": rejected,
        "selection": selected,
        "filters": {
            "market": market,
            "bookmaker": bookmaker,
            "prefer_bookmaker": prefer_bookmaker,
            "max_events": max_events,
            "one_side_per_event": one_side_per_event,
            "prefer_side": prefer_side,
            "include_draw": include_draw,
            "include_live": include_live,
            "exclude_finished": exclude_finished,
            "date_min": date_min,
        },
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_selection(rows: Iterable[Dict[str, Any]], output: str) -> Path:
    target = _safe_output(output)
    return write_normalized_csv(rows, str(target))


def write_summary(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    payload = dict(report)
    payload["selection"] = payload.get("selection", [])[:20]
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Selection odds API-Football valides")
    print(f"- Lignes lues: {report.get('rows_read')}")
    print(f"- Candidates valides: {report.get('valid_candidates')}")
    print(f"- Lignes selectionnees: {report.get('selected_rows')}")
    print(f"- Events distincts: {report.get('distinct_events')}")
    print("- Selection observation shadow uniquement, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Selectionne des odds API-Football enrichies valides pour shadow.")
    parser.add_argument("--odds", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary-json", default="")
    parser.add_argument("--market", default="h2h")
    parser.add_argument("--bookmaker", default="")
    parser.add_argument("--prefer-bookmaker", default="")
    parser.add_argument("--max-events", type=int, default=3)
    parser.add_argument("--one-side-per-event", action="store_true", default=True)
    parser.add_argument("--prefer-side", default="")
    parser.add_argument("--include-draw", action="store_true")
    parser.add_argument("--include-live", action="store_true")
    parser.add_argument("--exclude-finished", action="store_true", default=True)
    parser.add_argument("--date-min", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = select_valid_odds(
            args.odds,
            market=args.market,
            bookmaker=args.bookmaker,
            prefer_bookmaker=args.prefer_bookmaker,
            max_events=args.max_events,
            one_side_per_event=args.one_side_per_event,
            prefer_side=args.prefer_side,
            include_draw=args.include_draw,
            include_live=args.include_live,
            exclude_finished=args.exclude_finished,
            date_min=args.date_min,
        )
        write_selection(report["selection"], args.output)
        if args.summary_json:
            write_summary(report, args.summary_json)
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
