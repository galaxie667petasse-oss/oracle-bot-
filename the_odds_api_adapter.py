import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

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


def normalize_the_odds_api_payload(payload: Any) -> List[Dict[str, Any]]:
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
                        "is_near_close": event.get("is_near_close") or "",
                        "raw_market": raw_market,
                        "raw_side": raw_side,
                        "raw_payload_ref": str(event.get("id") or ""),
                    })
    return normalize_odds_rows(rows, source="the_odds_api")


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
            print("- Aucun reseau lance. The Odds API free ne fournit pas l'historique complet.")
            return 0
        if args.from_fixture:
            rows = normalize_the_odds_api_payload(read_fixture(args.from_fixture))
            print(f"- Fixture lue: {args.from_fixture}")
            print(f"- Lignes normalisees: {len(rows)}")
            if args.output:
                print(f"- Sortie ecrite: {write_normalized_csv(rows, args.output)}")
            return 0
        if not args.allow_network:
            raise ValueError("Reseau refuse par defaut. Utiliser --dry-run ou --allow-network.")
        if not args.sport:
            raise ValueError("--sport requis pour --allow-network")
        rows = normalize_the_odds_api_payload(fetch_the_odds_api(args.sport, args.regions, args.markets, config))
        print(f"- Lignes normalisees: {len(rows)}")
        if args.output:
            print(f"- Sortie ecrite: {write_normalized_csv(rows, args.output)}")
        print("- Closing automatique fiable peut necessiter un plan payant ou une source historique documentee.")
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
