import argparse
import csv
import html
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from odds_normalizer import ODDS_COLUMNS, normalize_decimal_odds, write_normalized_csv


FINISHED_STATUSES = {"FT", "AET", "PEN", "WO", "AWD", "CANC", "ABD"}
STARTED_STATUSES = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT", "SUSP"}
DEFAULT_INCLUDE_STATUSES = "NS,TBD"


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
    return str(value or "").strip().lower() in {"true", "1", "yes", "oui", "vrai"}


def _bool_arg(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "oui", "vrai"}:
        return True
    if text in {"false", "0", "no", "non", "faux"}:
        return False
    raise argparse.ArgumentTypeError("booleen attendu: true/false")


def _counts(rows: Iterable[Dict[str, Any]], key: str, limit: int = 30) -> Dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        counter[str(row.get(key) or "missing")] += 1
    return dict(counter.most_common(limit))


def _extract_status(row: Dict[str, Any]) -> str:
    direct = str(row.get("status") or row.get("fixture_status") or "").strip()
    if direct:
        return direct.upper()
    raw = str(row.get("raw_payload_ref") or "")
    for part in raw.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        if key.strip().lower() in {"status", "fixture_status"}:
            return value.strip().upper()
    return ""


def _status_allowed(
    row: Dict[str, Any],
    allow_finished: bool,
    allow_started: bool,
    include_statuses: str,
    fallback_if_status_missing: bool,
) -> Tuple[bool, str]:
    status = _extract_status(row)
    allowed_statuses = {item.strip().upper() for item in str(include_statuses or "").split(",") if item.strip()}
    if not status:
        if fallback_if_status_missing:
            return True, "status absent accepte par fallback"
        return False, "status absent"
    if status in FINISHED_STATUSES and not allow_finished:
        return False, "match termine exclu"
    if status in STARTED_STATUSES and not allow_started:
        return False, "match deja commence exclu"
    if allowed_statuses and status not in allowed_statuses:
        if status in FINISHED_STATUSES and allow_finished:
            return True, "status termine autorise"
        if status in STARTED_STATUSES and allow_started:
            return True, "status commence autorise"
        return False, "status exclu"
    return True, "status ok"


def _row_ok(
    row: Dict[str, Any],
    market: str,
    bookmaker: str,
    include_live: bool,
    include_draw: bool,
    date_min: str,
    allow_finished: bool,
    allow_started: bool,
    include_statuses: str,
    fallback_if_status_missing: bool,
) -> Tuple[bool, str]:
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
    status_ok, status_reason = _status_allowed(row, allow_finished, allow_started, include_statuses, fallback_if_status_missing)
    if not status_ok:
        return False, status_reason
    if date_min and str(row.get("match_date") or "") < date_min:
        return False, "date pas assez recente"
    if not row.get("home_team") or not row.get("away_team"):
        return False, "equipes absentes"
    try:
        normalize_decimal_odds(row.get("odds"))
    except Exception as exc:
        return False, str(exc)
    return True, "ok"


def _debug_summary(rows: List[Dict[str, Any]], selected: List[Dict[str, Any]], rejected: Dict[str, int], filters: Dict[str, Any]) -> Dict[str, Any]:
    statuses = [_extract_status(row) or "missing" for row in rows]
    h2h_rows = [row for row in rows if row.get("market_type") == "h2h"]
    valid_h2h_rows = [row for row in h2h_rows if row.get("validation_status") == "valid"]
    not_finished = [row for row in valid_h2h_rows if _extract_status(row) not in FINISHED_STATUSES]
    include_statuses = {item.strip().upper() for item in str(filters.get("include_statuses") or "").split(",") if item.strip()}
    future_or_not_started = [
        row for row in not_finished
        if not _extract_status(row) or not include_statuses or _extract_status(row) in include_statuses
    ]
    status_missing = statuses.count("missing")
    warnings = []
    if status_missing:
        warnings.append("status absent sur certaines lignes: fallback applique si autorise")
    if not selected:
        warnings.append("selection vide: lire rejection_reasons avant toute action")
    return {
        "rows_read": len(rows),
        "validation_status_counts": _counts(rows, "validation_status"),
        "market_type_counts": _counts(rows, "market_type"),
        "side_counts": _counts(rows, "side"),
        "bookmaker_counts": _counts(rows, "bookmaker"),
        "status_counts": dict(Counter(statuses).most_common(30)),
        "h2h_rows": len(h2h_rows),
        "h2h_valid_rows": len(valid_h2h_rows),
        "valid_h2h_rows": len(valid_h2h_rows),
        "valid_h2h_not_finished_rows": len(not_finished),
        "valid_h2h_future_or_not_started_rows": len(future_or_not_started),
        "rejected_finished": rejected.get("match termine exclu", 0),
        "rejected_started": rejected.get("match deja commence exclu", 0),
        "rejected_live": rejected.get("live exclu", 0),
        "rejected_near_close": rejected.get("near-close exclu comme taken odds", 0),
        "rejected_draw": rejected.get("draw exclu", 0),
        "rejected_missing_teams": rejected.get("equipes absentes", 0),
        "rejected_bad_odds": sum(count for reason, count in rejected.items() if "cote" in reason),
        "selected_rows": len(selected),
        "distinct_events": len({row.get("source_event_id") for row in selected if row.get("source_event_id")}),
        "warnings": warnings,
        "lab_only": True,
        "can_influence_picks": False,
    }


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
    allow_finished: bool = False,
    allow_started: bool = False,
    include_statuses: str = DEFAULT_INCLUDE_STATUSES,
    fallback_if_status_missing: bool = True,
) -> Dict[str, Any]:
    rows = _load_rows(odds_path)
    date_min = date_min or _today()
    if not exclude_finished:
        allow_finished = True
    valid: List[Dict[str, Any]] = []
    rejected: Dict[str, int] = {}
    for row in rows:
        ok, reason = _row_ok(
            row,
            market,
            bookmaker,
            include_live,
            include_draw,
            date_min,
            allow_finished,
            allow_started,
            include_statuses,
            fallback_if_status_missing,
        )
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
    filters = {
        "market": market,
        "bookmaker": bookmaker,
        "prefer_bookmaker": prefer_bookmaker,
        "max_events": max_events,
        "one_side_per_event": one_side_per_event,
        "prefer_side": prefer_side,
        "include_draw": include_draw,
        "include_live": include_live,
        "exclude_finished": exclude_finished,
        "allow_finished": allow_finished,
        "allow_started": allow_started,
        "include_statuses": include_statuses,
        "fallback_if_status_missing": fallback_if_status_missing,
        "date_min": date_min,
    }
    debug = _debug_summary(rows, selected, rejected, filters)
    return {
        "input": odds_path,
        "rows_read": len(rows),
        "valid_candidates": len(valid),
        "selected_rows": len(selected),
        "distinct_events": len({row.get("source_event_id") for row in selected if row.get("source_event_id")}),
        "rejection_reasons": dict(sorted(rejected.items(), key=lambda item: item[1], reverse=True)),
        "selection": selected,
        "filters": filters,
        "debug": debug,
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


def write_debug(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    payload = dict(report.get("debug") or {})
    payload["input"] = report.get("input")
    payload["rejection_reasons"] = report.get("rejection_reasons") or {}
    payload["filters"] = report.get("filters") or {}
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    debug = report.get("debug") or {}
    target.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>API-Football valid odds debug</h1><pre>"
        + html.escape(json.dumps(debug, ensure_ascii=False, indent=2))
        + "</pre><p>Observation shadow seulement, aucune mise.</p></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any]) -> None:
    debug = report.get("debug") or {}
    print("Selection odds API-Football valides")
    print(f"- Lignes lues: {report.get('rows_read')}")
    print(f"- Candidates valides: {report.get('valid_candidates')}")
    print(f"- H2H valides: {debug.get('valid_h2h_rows')}")
    print(f"- H2H valides non termines: {debug.get('valid_h2h_not_finished_rows')}")
    print(f"- Lignes selectionnees: {report.get('selected_rows')}")
    print(f"- Events distincts: {report.get('distinct_events')}")
    if not report.get("selected_rows"):
        top_reasons = list((report.get("rejection_reasons") or {}).items())[:5]
        for reason, count in top_reasons:
            print(f"- Rejet principal: {reason} ({count})")
    for warning in debug.get("warnings") or []:
        print(f"- Warning: {warning}")
    print("- Selection observation shadow uniquement, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Selectionne des odds API-Football enrichies valides pour shadow.")
    parser.add_argument("--odds", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary-json", default="")
    parser.add_argument("--debug-summary-json", default="")
    parser.add_argument("--html", default="")
    parser.add_argument("--market", default="h2h")
    parser.add_argument("--bookmaker", default="")
    parser.add_argument("--prefer-bookmaker", default="")
    parser.add_argument("--max-events", type=int, default=3)
    parser.add_argument("--one-side-per-event", action="store_true", default=True)
    parser.add_argument("--prefer-side", default="")
    parser.add_argument("--include-draw", action="store_true")
    parser.add_argument("--include-live", action="store_true")
    parser.add_argument("--allow-finished", nargs="?", const="true", default="false", type=lambda value: _bool_arg(value, False))
    parser.add_argument("--allow-started", nargs="?", const="true", default="false", type=lambda value: _bool_arg(value, False))
    parser.add_argument("--include-statuses", default=DEFAULT_INCLUDE_STATUSES)
    parser.add_argument("--fallback-if-status-missing", type=lambda value: _bool_arg(value, True), default=True)
    parser.add_argument("--exclude-finished", action="store_true", default=True)
    parser.add_argument("--date", default="")
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
            date_min=args.date_min or args.date,
            allow_finished=args.allow_finished,
            allow_started=args.allow_started,
            include_statuses=args.include_statuses,
            fallback_if_status_missing=args.fallback_if_status_missing,
        )
        write_selection(report["selection"], args.output)
        if args.summary_json:
            write_summary(report, args.summary_json)
        if args.debug_summary_json:
            write_debug(report, args.debug_summary_json)
        if args.html:
            write_html(report, args.html)
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
