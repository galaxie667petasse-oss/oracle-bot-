import argparse
import html
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from odds_source_config import load_odds_source_config
from the_odds_active_sports import build_report as build_active_sports_report, fetch_active_sports, read_fixture as read_active_fixture
from the_odds_api_adapter import fetch_the_odds_api, normalize_the_odds_api_payload, read_fixture


DEFAULT_SPORT_KEYS = [
    "soccer_epl",
    "soccer_france_ligue_one",
    "soccer_germany_bundesliga",
    "soccer_italy_serie_a",
    "soccer_spain_la_liga",
    "soccer_uefa_champs_league",
    "soccer_uefa_europa_league",
    "soccer_japan_j_league",
    "soccer_norway_eliteserien",
    "soccer_sweden_allsvenskan",
    "soccer_chile_campeonato",
    "soccer_china_superleague",
    "soccer_usa_mls",
    "soccer_brazil_campeonato",
    "soccer_argentina_primera_division",
    "soccer_finland_veikkausliiga",
    "soccer_korea_kleague1",
]


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le rapport scanner doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _fixture_path(fixtures_dir: str, sport_key: str) -> Path:
    return Path(fixtures_dir) / f"{sport_key}.json"


def _parse_date(value: Any):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date()
    except Exception:
        return None


def _priority(rows: List[Dict[str, Any]], now_date=None) -> str:
    now_date = now_date or datetime.now().date()
    if not rows:
        return "low"
    dates = sorted({_parse_date(row.get("match_date")) for row in rows if _parse_date(row.get("match_date"))})
    if not dates:
        return "medium"
    delta = (dates[0] - now_date).days
    if delta <= 3:
        return "high"
    if delta <= 14:
        return "medium"
    return "low"


def _filter_dates(rows: List[Dict[str, Any]], date_from: str = "", date_to: str = "", only_near_term_days: int = 0) -> List[Dict[str, Any]]:
    now_date = datetime.now().date()
    out = []
    for row in rows:
        d = _parse_date(row.get("match_date"))
        if date_from and str(row.get("match_date") or "") < date_from:
            continue
        if date_to and str(row.get("match_date") or "") > date_to:
            continue
        if only_near_term_days and d and d > now_date + timedelta(days=only_near_term_days):
            continue
        out.append(row)
    return out


def _near_term_events(rows: List[Dict[str, Any]], days: int = 14) -> int:
    now_date = datetime.now().date()
    events = set()
    for row in rows:
        d = _parse_date(row.get("match_date"))
        if d and d <= now_date + timedelta(days=days):
            events.add(row.get("source_event_id") or (row.get("match_date"), row.get("home_team"), row.get("away_team")))
    return len(events)


def _sport_report(
    sport_key: str,
    payload: Any,
    status: str = "ok",
    warning: str = "",
    date_from: str = "",
    date_to: str = "",
    only_near_term_days: int = 0,
) -> Dict[str, Any]:
    rows = normalize_the_odds_api_payload(payload)
    rows = _filter_dates(rows, date_from=date_from, date_to=date_to, only_near_term_days=only_near_term_days)
    dates = sorted({row.get("match_date") for row in rows if row.get("match_date")})
    events = sorted({row.get("source_event_id") for row in rows if row.get("source_event_id")})
    bookmakers: Dict[str, int] = {}
    for row in rows:
        book = row.get("bookmaker")
        if book:
            bookmakers[book] = bookmakers.get(book, 0) + 1
    return {
        "sport_key": sport_key,
        "request_status": status,
        "credits_remaining": None,
        "rows": len(rows),
        "normalized_rows": len(rows),
        "events": len(events),
        "distinct_events": len(events),
        "earliest_match_date": dates[0] if dates else None,
        "latest_match_date": dates[-1] if dates else None,
        "bookmakers_count": len(bookmakers),
        "top_bookmakers": sorted(bookmakers, key=bookmakers.get, reverse=True)[:10],
        "markets_found": sorted({row.get("market_type") for row in rows if row.get("market_type")}),
        "near_term_events": _near_term_events(rows),
        "usable_for_shadow": bool(rows),
        "priority": _priority(rows),
        "recommended_priority": _priority(rows),
        "warnings": [warning] if warning else [],
    }


def _load_active_sport_keys(path: str, include_outrights: bool = False, exclude_winner_markets: bool = True) -> List[str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    sports = data.get("sports") or []
    keys = []
    for item in sports:
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        if not include_outrights and item.get("has_outrights"):
            continue
        if exclude_winner_markets and "winner" in key.lower():
            continue
        keys.append(key)
    if not sports and data.get("sport_keys"):
        keys = [str(key) for key in data.get("sport_keys") or [] if str(key)]
    return keys


def scan_sports(
    sport_keys: List[str] | None = None,
    regions: str = "eu",
    markets: str = "h2h",
    allow_network: bool = False,
    dry_run: bool = False,
    from_fixtures: str = "",
    active_sports_json: str = "",
    auto_active_sports: bool = False,
    include_outrights: bool = False,
    exclude_winner_markets: bool = True,
    max_sports: int = 0,
    date_from: str = "",
    date_to: str = "",
    only_near_term_days: int = 0,
) -> Dict[str, Any]:
    config = load_odds_source_config()
    active_report = {}
    if active_sports_json:
        active_report = json.loads(Path(active_sports_json).read_text(encoding="utf-8"))
        sports = _load_active_sport_keys(active_sports_json, include_outrights=include_outrights, exclude_winner_markets=exclude_winner_markets)
    elif auto_active_sports:
        if not allow_network:
            raise ValueError("--auto-active-sports exige --allow-network")
        active_report = build_active_sports_report(fetch_active_sports(config), group="Soccer")
        sports = [
            item["key"]
            for item in active_report.get("sports") or []
            if (include_outrights or not item.get("has_outrights")) and (not exclude_winner_markets or "winner" not in item.get("key", "").lower())
        ]
    else:
        sports = sport_keys or DEFAULT_SPORT_KEYS
    if max_sports:
        sports = sports[:max_sports]
    reports = []
    for sport in sports:
        if dry_run and not from_fixtures:
            reports.append({
                "sport_key": sport,
                "request_status": "dry_run",
                "credits_remaining": None,
                "normalized_rows": 0,
                "distinct_events": 0,
                "earliest_match_date": None,
                "latest_match_date": None,
                "bookmakers_count": 0,
                "top_bookmakers": [],
                "markets_found": [],
                "near_term_events": 0,
                "usable_for_shadow": False,
                "priority": "low",
                "recommended_priority": "low",
                "warnings": ["dry-run: aucun reseau"],
            })
            continue
        try:
            if from_fixtures:
                path = _fixture_path(from_fixtures, sport)
                if not path.exists():
                    reports.append(_sport_report(sport, [], status="fixture_absente", warning="fixture absente", date_from=date_from, date_to=date_to, only_near_term_days=only_near_term_days))
                    continue
                payload = read_fixture(str(path))
            else:
                if not allow_network:
                    raise ValueError("reseau refuse par defaut")
                payload = fetch_the_odds_api(sport, regions, markets, config)
            reports.append(_sport_report(sport, payload, date_from=date_from, date_to=date_to, only_near_term_days=only_near_term_days))
        except Exception as exc:
            reports.append(_sport_report(sport, [], status="erreur", warning=str(exc), date_from=date_from, date_to=date_to, only_near_term_days=only_near_term_days))
    active = [item for item in reports if item.get("normalized_rows", 0) > 0]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "regions": regions,
        "markets": markets,
        "allow_network": allow_network,
        "dry_run": dry_run,
        "sports": reports,
        "active_sports_json": active_sports_json,
        "auto_active_sports": auto_active_sports,
        "active_sports_report_present": bool(active_report),
        "active_sports": len(active),
        "high_priority": [item["sport_key"] for item in reports if item.get("recommended_priority") == "high"],
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    rows = "".join(
        f"<tr><td>{html.escape(item['sport_key'])}</td><td>{item['request_status']}</td><td>{item['normalized_rows']}</td><td>{item['distinct_events']}</td><td>{item['recommended_priority']}</td></tr>"
        for item in report.get("sports") or []
    )
    target.write_text(
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Soccer Odds Sport Scanner</title></head><body>"
        "<h1>Soccer Odds Sport Scanner</h1><table border='1'><tr><th>Sport</th><th>Status</th><th>Lignes</th><th>Events</th><th>Priorite</th></tr>"
        + rows
        + "</table><p>Observation seulement, aucune mise.</p></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Scanner sports soccer The Odds API")
    print(f"- Sports actifs: {report.get('active_sports')}")
    for item in report.get("sports") or []:
        print(f"- {item['sport_key']}: {item['normalized_rows']} lignes, {item['distinct_events']} events, priorite={item['recommended_priority']}")
    print("- Aucun reseau sans --allow-network.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Scanne les sport_keys soccer The Odds API.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--regions", default="eu")
    parser.add_argument("--markets", default="h2h")
    parser.add_argument("--sports", default="")
    parser.add_argument("--from-fixtures", default="")
    parser.add_argument("--active-sports-json", default="")
    parser.add_argument("--auto-active-sports", action="store_true")
    parser.add_argument("--include-outrights", action="store_true")
    parser.add_argument("--exclude-winner-markets", default="true")
    parser.add_argument("--max-sports", type=int, default=0)
    parser.add_argument("--date-from", default="")
    parser.add_argument("--date-to", default="")
    parser.add_argument("--only-near-term-days", type=int, default=0)
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        sports = [item.strip() for item in args.sports.split(",") if item.strip()] if args.sports else None
        exclude_winner = str(args.exclude_winner_markets).strip().lower() not in {"0", "false", "non", "no"}
        report = scan_sports(
            sports,
            args.regions,
            args.markets,
            allow_network=args.allow_network,
            dry_run=args.dry_run or (not args.allow_network and not args.from_fixtures),
            from_fixtures=args.from_fixtures,
            active_sports_json=args.active_sports_json,
            auto_active_sports=args.auto_active_sports,
            include_outrights=args.include_outrights,
            exclude_winner_markets=exclude_winner,
            max_sports=args.max_sports,
            date_from=args.date_from,
            date_to=args.date_to,
            only_near_term_days=args.only_near_term_days,
        )
        if args.output:
            write_json(report, args.output)
        if args.html:
            write_html(report, args.html)
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
