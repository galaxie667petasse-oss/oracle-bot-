import argparse
import csv
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List

from odds_normalizer import ODDS_COLUMNS, normalize_odds_rows, write_normalized_csv
from odds_source_config import get_api_key_from_env, load_odds_source_config, validate_config


def _fixture_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in payload.get("response") or []:
        fixture = item.get("fixture") or {}
        league = item.get("league") or {}
        teams = item.get("teams") or {}
        home = (teams.get("home") or {}).get("name") or item.get("home_team") or ""
        away = (teams.get("away") or {}).get("name") or item.get("away_team") or ""
        kickoff = str(fixture.get("date") or "")
        match_date = kickoff[:10] if kickoff else str(item.get("match_date") or "")
        for bookmaker in item.get("bookmakers") or []:
            bookmaker_name = bookmaker.get("name") or bookmaker.get("title") or ""
            for bet in bookmaker.get("bets") or []:
                raw_market = bet.get("name") or bet.get("label") or ""
                for value in bet.get("values") or []:
                    raw_side = value.get("value") or value.get("label") or value.get("name") or ""
                    rows.append({
                        "captured_at": item.get("captured_at") or "",
                        "source": "api_football",
                        "source_event_id": fixture.get("id") or item.get("fixture_id") or "",
                        "league": league.get("name") or item.get("league") or "",
                        "match_date": match_date,
                        "kickoff_time": kickoff,
                        "home_team": home,
                        "away_team": away,
                        "bookmaker": bookmaker_name,
                        "market_type": raw_market,
                        "side": raw_side,
                        "odds": value.get("odd") or value.get("odds") or value.get("price") or "",
                        "is_live": item.get("is_live") or "",
                        "is_near_close": item.get("is_near_close") or "",
                        "raw_market": raw_market,
                        "raw_side": raw_side,
                        "raw_payload_ref": str(fixture.get("id") or ""),
                    })
    return rows


def normalize_api_football_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return normalize_odds_rows(_fixture_rows(payload), source="api_football")


def read_fixture(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fetch_api_football(league: str, date: str, config: Dict[str, Any]) -> Dict[str, Any]:
    source = config.get("api_football") or {}
    key = get_api_key_from_env("api_football", config)
    if not key:
        raise ValueError("Cle API-Football absente dans l'environnement.")
    base_url = str(source.get("base_url") or "https://v3.football.api-sports.io").rstrip("/")
    query = urllib.parse.urlencode({"league": league, "date": date})
    request = urllib.request.Request(f"{base_url}/odds?{query}", headers={"x-apisports-key": key})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def write_rows(rows: Iterable[Dict[str, Any]], output: str) -> Path:
    return write_normalized_csv(rows, output)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Adaptateur API-Football odds, reseau desactive par defaut.")
    parser.add_argument("--check-config", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--league", default="")
    parser.add_argument("--date", default="")
    parser.add_argument("--from-fixture", default="")
    parser.add_argument("--output", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        config = load_odds_source_config()
        if args.check_config:
            report = validate_config(config)
            print("API-Football odds adapter")
            print(f"- Configuration: {'OK' if report['ok'] else 'bloquante'}")
            print(f"- Cle API: {'presente' if get_api_key_from_env('api_football', config) else 'absente'}")
            print("- Aucun reseau lance par --check-config.")
            return 0 if report["ok"] else 1
        if args.dry_run:
            print("API-Football dry-run")
            print(f"- Ligue: {args.league or 'n/a'}")
            print(f"- Date: {args.date or 'n/a'}")
            print("- Aucun reseau lance. Ajouter --allow-network explicitement pour une vraie requete.")
            return 0
        if args.from_fixture:
            rows = normalize_api_football_payload(read_fixture(args.from_fixture))
            print(f"- Fixture lue: {args.from_fixture}")
            print(f"- Lignes normalisees: {len(rows)}")
            if args.output:
                print(f"- Sortie ecrite: {write_rows(rows, args.output)}")
            return 0
        if not args.allow_network:
            raise ValueError("Reseau refuse par defaut. Utiliser --dry-run ou --allow-network.")
        if not args.league or not args.date:
            raise ValueError("--league et --date requis pour --allow-network")
        rows = normalize_api_football_payload(fetch_api_football(args.league, args.date, config))
        print(f"- Lignes normalisees: {len(rows)}")
        if args.output:
            print(f"- Sortie ecrite: {write_rows(rows, args.output)}")
        print("- API-Football peut etre utile au laboratoire, mais ne prouve pas une closing historique parfaite.")
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
