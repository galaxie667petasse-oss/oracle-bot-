import argparse
import html
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from odds_source_config import load_odds_source_config
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


def _priority(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "low"
    dates = sorted({row.get("match_date") for row in rows if row.get("match_date")})
    if len(rows) > 50 and dates:
        try:
            first = datetime.fromisoformat(dates[0][:10]).date()
            if first <= (datetime.now().date() + timedelta(days=14)):
                return "high"
        except Exception:
            pass
    return "medium"


def _sport_report(sport_key: str, payload: Any, status: str = "ok", warning: str = "") -> Dict[str, Any]:
    rows = normalize_the_odds_api_payload(payload)
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
        "normalized_rows": len(rows),
        "distinct_events": len(events),
        "earliest_match_date": dates[0] if dates else None,
        "latest_match_date": dates[-1] if dates else None,
        "bookmakers_count": len(bookmakers),
        "top_bookmakers": sorted(bookmakers, key=bookmakers.get, reverse=True)[:10],
        "markets_found": sorted({row.get("market_type") for row in rows if row.get("market_type")}),
        "usable_for_shadow": bool(rows),
        "recommended_priority": _priority(rows),
        "warnings": [warning] if warning else [],
    }


def scan_sports(
    sport_keys: List[str] | None = None,
    regions: str = "eu",
    markets: str = "h2h",
    allow_network: bool = False,
    dry_run: bool = False,
    from_fixtures: str = "",
) -> Dict[str, Any]:
    sports = sport_keys or DEFAULT_SPORT_KEYS
    reports = []
    config = load_odds_source_config()
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
                "usable_for_shadow": False,
                "recommended_priority": "low",
                "warnings": ["dry-run: aucun reseau"],
            })
            continue
        try:
            if from_fixtures:
                path = _fixture_path(from_fixtures, sport)
                if not path.exists():
                    reports.append(_sport_report(sport, [], status="fixture_absente", warning="fixture absente"))
                    continue
                payload = read_fixture(str(path))
            else:
                if not allow_network:
                    raise ValueError("reseau refuse par defaut")
                payload = fetch_the_odds_api(sport, regions, markets, config)
            reports.append(_sport_report(sport, payload))
        except Exception as exc:
            reports.append(_sport_report(sport, [], status="erreur", warning=str(exc)))
    active = [item for item in reports if item.get("normalized_rows", 0) > 0]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "regions": regions,
        "markets": markets,
        "allow_network": allow_network,
        "dry_run": dry_run,
        "sports": reports,
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
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        sports = [item.strip() for item in args.sports.split(",") if item.strip()] if args.sports else None
        report = scan_sports(sports, args.regions, args.markets, allow_network=args.allow_network, dry_run=args.dry_run or not args.allow_network, from_fixtures=args.from_fixtures)
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
