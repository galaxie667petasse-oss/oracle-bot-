import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List

from odds_normalizer import normalize_odds_rows, write_normalized_csv
from odds_source_config import get_api_key_from_env, load_odds_source_config, validate_config


def _market_type(key: str) -> str:
    text = str(key or "").lower()
    if text == "h2h":
        return "h2h"
    if text in {"totals", "total"}:
        return "total"
    if text == "btts":
        return "btts"
    return text or "unknown"


def _side_from_outcome(name: str, home: str, away: str) -> str:
    text = str(name or "").strip()
    if text.lower() == str(home or "").lower():
        return "home"
    if text.lower() == str(away or "").lower():
        return "away"
    if text.lower() == "draw":
        return "draw"
    if text.lower().startswith("over"):
        return "over"
    if text.lower().startswith("under"):
        return "under"
    if text.lower() in {"yes", "no"}:
        return text.lower()
    return text


def normalize_the_odds_api_payload(payload: Any, near_close: bool = False) -> List[Dict[str, Any]]:
    events = payload if isinstance(payload, list) else payload.get("data") or []
    rows: List[Dict[str, Any]] = []
    for event in events:
        home = event.get("home_team") or ""
        away = event.get("away_team") or ""
        kickoff = event.get("commence_time") or ""
        for bookmaker in event.get("bookmakers") or []:
            bookmaker_name = bookmaker.get("title") or bookmaker.get("key") or ""
            for market in bookmaker.get("markets") or []:
                raw_market = market.get("key") or ""
                for outcome in market.get("outcomes") or []:
                    raw_side = outcome.get("name") or ""
                    rows.append({
                        "captured_at": event.get("captured_at") or "",
                        "source": "the_odds_api",
                        "source_event_id": event.get("id") or "",
                        "league": event.get("sport_title") or event.get("sport_key") or "",
                        "match_date": kickoff[:10] if kickoff else "",
                        "kickoff_time": kickoff,
                        "home_team": home,
                        "away_team": away,
                        "bookmaker": bookmaker_name,
                        "market_type": _market_type(raw_market),
                        "side": _side_from_outcome(raw_side, home, away),
                        "odds": outcome.get("price") or outcome.get("odd") or "",
                        "is_live": event.get("is_live") or "",
                        "is_near_close": "true" if near_close else (event.get("is_near_close") or ""),
                        "raw_market": raw_market,
                        "raw_side": raw_side,
                        "raw_payload_ref": str(event.get("id") or ""),
                    })
    return normalize_odds_rows(rows, source="the_odds_api")


def _csv_list(value: str) -> List[str]:
    return [item.strip().lower() for item in str(value or "").split(",") if item.strip()]


def _event_key(row: Dict[str, Any]) -> str:
    return str(row.get("source_event_id") or "").strip() or "|".join([
        str(row.get("match_date") or ""),
        str(row.get("league") or ""),
        str(row.get("home_team") or ""),
        str(row.get("away_team") or ""),
    ]).lower()


def _date_ok(row: Dict[str, Any], date_from: str = "", date_to: str = "", match_date: str = "") -> bool:
    value = str(row.get("match_date") or "").strip()
    if match_date:
        return value == match_date
    if date_from and value < date_from:
        return False
    if date_to and value > date_to:
        return False
    return True


def _limit_events(rows: Iterable[Dict[str, Any]], max_events: int = 0) -> List[Dict[str, Any]]:
    if not max_events:
        return list(rows)
    kept = []
    seen = []
    for row in rows:
        key = _event_key(row)
        if key not in seen:
            if len(seen) >= max_events:
                continue
            seen.append(key)
        kept.append(row)
    return kept


def _select_one_side(
    rows: List[Dict[str, Any]],
    prefer_bookmaker: str = "",
    prefer_side: str = "",
    prefer_market: str = "h2h",
    include_draw: bool = False,
) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(_event_key(row), []).append(row)
    selected = []
    preferred_book = prefer_bookmaker.strip().lower()
    preferred_side = prefer_side.strip().lower()
    preferred_market = (prefer_market or "h2h").strip().lower()
    for key in grouped:
        candidates = [row for row in grouped[key] if row.get("validation_status") == "valid"]
        if not candidates:
            continue
        if not include_draw and preferred_side != "draw":
            non_draw = [row for row in candidates if str(row.get("side") or "").lower() != "draw"]
            if non_draw:
                candidates = non_draw
        candidates = sorted(
            candidates,
            key=lambda row: (
                0 if preferred_book and str(row.get("bookmaker") or "").lower() == preferred_book else 1,
                0 if str(row.get("market_type") or "").lower() == preferred_market else 1,
                0 if preferred_side and str(row.get("side") or "").lower() == preferred_side else 1,
                str(row.get("bookmaker") or "").lower(),
                str(row.get("side") or "").lower(),
                str(row.get("snapshot_id") or ""),
            ),
        )
        chosen = dict(candidates[0])
        reason = str(chosen.get("validation_reason") or "ok")
        if "selected_one_side_per_event" not in reason:
            chosen["validation_reason"] = reason + "; selected_one_side_per_event"
        selected.append(chosen)
    return selected


def filter_normalized_rows(
    rows: List[Dict[str, Any]],
    bookmaker: str = "",
    bookmakers: str = "",
    date_from: str = "",
    date_to: str = "",
    match_date: str = "",
    max_events: int = 0,
    one_side_per_event: bool = False,
    prefer_bookmaker: str = "",
    prefer_side: str = "",
    prefer_market: str = "h2h",
    include_draw: bool = False,
) -> List[Dict[str, Any]]:
    allowed_books = set(_csv_list(bookmakers))
    if bookmaker:
        allowed_books.add(bookmaker.strip().lower())
    out = []
    for row in rows:
        if allowed_books and str(row.get("bookmaker") or "").lower() not in allowed_books:
            continue
        if not _date_ok(row, date_from=date_from, date_to=date_to, match_date=match_date):
            continue
        out.append(row)
    out = _limit_events(out, max_events=max_events)
    if one_side_per_event:
        out = _select_one_side(
            out,
            prefer_bookmaker=prefer_bookmaker or bookmaker,
            prefer_side=prefer_side,
            prefer_market=prefer_market,
            include_draw=include_draw,
        )
    return out


def read_fixture(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fetch_the_odds_api(sport: str, regions: str, markets: str, config: Dict[str, Any]) -> Any:
    source = config.get("the_odds_api") or {}
    key = get_api_key_from_env("the_odds_api", config)
    if not key:
        raise ValueError("Cle The Odds API absente dans l'environnement.")
    base_url = str(source.get("base_url") or "https://api.the-odds-api.com/v4").rstrip("/")
    query = urllib.parse.urlencode({
        "apiKey": key,
        "regions": regions,
        "markets": markets,
        "oddsFormat": source.get("odds_format") or "decimal",
    })
    request = urllib.request.Request(f"{base_url}/sports/{sport}/odds?{query}")
    with urllib.request.urlopen(request, timeout=30) as response:
        remaining = response.headers.get("x-requests-remaining")
        if remaining:
            print(f"- Credits restants declares par API: {remaining}")
        return json.loads(response.read().decode("utf-8"))


def _safe_write_raw(payload: Any, path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le raw dump doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _print_run_summary(args, raw_events: int, before: int, rows: List[Dict[str, Any]], output: str = "") -> None:
    events_after = len({_event_key(row) for row in rows})
    print("The Odds API adapter")
    print(f"- Sport: {args.sport or 'fixture'}")
    print(f"- Regions: {args.regions}")
    print(f"- Markets: {args.markets}")
    print(f"- Mode near-close: {'oui' if args.near_close else 'non'}")
    print(f"- Filtres: bookmaker={args.bookmaker or args.bookmakers or 'aucun'}, match-date={args.match_date or 'n/a'}, date-from={args.date_from or 'n/a'}, date-to={args.date_to or 'n/a'}")
    print(f"- Evenements bruts: {raw_events}")
    print(f"- Lignes normalisees avant filtres: {before}")
    print(f"- Lignes normalisees apres filtres: {len(rows)}")
    print(f"- Evenements conserves: {events_after}")
    print(f"- Sortie ecrite: {output or 'non'}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Adaptateur The Odds API, reseau desactive par defaut.")
    parser.add_argument("--check-config", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--sport", default="")
    parser.add_argument("--regions", default="eu")
    parser.add_argument("--markets", default="h2h,totals")
    parser.add_argument("--from-fixture", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--near-close", action="store_true")
    parser.add_argument("--bookmaker", default="")
    parser.add_argument("--bookmakers", default="")
    parser.add_argument("--match-date", default="")
    parser.add_argument("--date-from", default="")
    parser.add_argument("--date-to", default="")
    parser.add_argument("--max-events", type=int, default=0)
    parser.add_argument("--one-side-per-event", action="store_true")
    parser.add_argument("--prefer-bookmaker", default="")
    parser.add_argument("--prefer-side", default="")
    parser.add_argument("--prefer-market", default="h2h")
    parser.add_argument("--include-draw", action="store_true")
    parser.add_argument("--raw-dump", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        config = load_odds_source_config()
        if args.check_config:
            report = validate_config(config)
            print("The Odds API adapter")
            print(f"- Configuration: {'OK' if report['ok'] else 'bloquante'}")
            print(f"- Cle API: {'presente' if get_api_key_from_env('the_odds_api', config) else 'absente'}")
            print("- Aucun reseau lance par --check-config.")
            return 0 if report["ok"] else 1
        if args.dry_run:
            print("The Odds API dry-run")
            print(f"- Sport: {args.sport or 'n/a'}")
            print(f"- Regions: {args.regions}")
            print(f"- Markets: {args.markets}")
            print(f"- Mode near-close: {'oui' if args.near_close else 'non'}")
            print("- Aucun reseau lance. The Odds API free ne fournit pas l'historique complet.")
            return 0
        if args.from_fixture:
            payload = read_fixture(args.from_fixture)
            raw_events = len(payload if isinstance(payload, list) else payload.get("data") or [])
            rows = normalize_the_odds_api_payload(payload, near_close=args.near_close)
            before = len(rows)
            rows = filter_normalized_rows(
                rows,
                bookmaker=args.bookmaker,
                bookmakers=args.bookmakers,
                date_from=args.date_from,
                date_to=args.date_to,
                match_date=args.match_date,
                max_events=args.max_events,
                one_side_per_event=args.one_side_per_event,
                prefer_bookmaker=args.prefer_bookmaker,
                prefer_side=args.prefer_side,
                prefer_market=args.prefer_market,
                include_draw=args.include_draw,
            )
            if args.output:
                output = str(write_normalized_csv(rows, args.output))
            else:
                output = ""
            _print_run_summary(args, raw_events, before, rows, output)
            return 0
        if not args.allow_network:
            raise ValueError("Reseau refuse par defaut. Utiliser --dry-run ou --allow-network.")
        if not args.sport:
            raise ValueError("--sport requis pour --allow-network")
        payload = fetch_the_odds_api(args.sport, args.regions, args.markets, config)
        if args.raw_dump:
            print(f"- Raw dump ecrit: {_safe_write_raw(payload, args.raw_dump)}")
        raw_events = len(payload if isinstance(payload, list) else payload.get("data") or [])
        rows = normalize_the_odds_api_payload(payload, near_close=args.near_close)
        before = len(rows)
        rows = filter_normalized_rows(
            rows,
            bookmaker=args.bookmaker,
            bookmakers=args.bookmakers,
            date_from=args.date_from,
            date_to=args.date_to,
            match_date=args.match_date,
            max_events=args.max_events,
            one_side_per_event=args.one_side_per_event,
            prefer_bookmaker=args.prefer_bookmaker,
            prefer_side=args.prefer_side,
            prefer_market=args.prefer_market,
            include_draw=args.include_draw,
        )
        if args.output:
            output = str(write_normalized_csv(rows, args.output))
        else:
            output = ""
        _print_run_summary(args, raw_events, before, rows, output)
        print("- Closing automatique fiable peut necessiter un plan payant ou une source historique documentee.")
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
