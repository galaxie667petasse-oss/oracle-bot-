import argparse
import csv
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List

from odds_source_config import get_api_key_from_env, load_odds_source_config, validate_config
from team_name_normalizer import normalize_team_name


FIXTURE_COLUMNS = [
    "fixture_id",
    "date",
    "kickoff_time",
    "league_id",
    "league",
    "country",
    "home_team",
    "away_team",
    "status",
    "elapsed",
    "venue",
    "normalized_home",
    "normalized_away",
    "validation_status",
]


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Les fixtures API-Football doivent rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def read_fixture(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fetch_fixtures(date: str, config: Dict[str, Any], league_id: str = "", season: str = "") -> Dict[str, Any]:
    source = config.get("api_football") or {}
    key = get_api_key_from_env("api_football", config)
    if not key:
        raise ValueError("Cle API-Football absente dans l'environnement.")
    base_url = str(source.get("base_url") or "https://v3.football.api-sports.io").rstrip("/")
    params = {"date": date}
    if league_id:
        params["league"] = league_id
    if season:
        params["season"] = season
    request = urllib.request.Request(
        f"{base_url}/fixtures?{urllib.parse.urlencode(params)}",
        headers={"x-apisports-key": key},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_fixtures_payload(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for item in payload.get("response") or []:
        fixture = item.get("fixture") or {}
        league = item.get("league") or {}
        teams = item.get("teams") or {}
        status = fixture.get("status") or {}
        venue = fixture.get("venue") or {}
        home = (teams.get("home") or {}).get("name") or ""
        away = (teams.get("away") or {}).get("name") or ""
        kickoff = str(fixture.get("date") or "")
        row = {
            "fixture_id": str(fixture.get("id") or ""),
            "date": kickoff[:10] if kickoff else "",
            "kickoff_time": kickoff,
            "league_id": str(league.get("id") or ""),
            "league": str(league.get("name") or ""),
            "country": str(league.get("country") or ""),
            "home_team": home,
            "away_team": away,
            "status": str(status.get("short") or status.get("long") or ""),
            "elapsed": str(status.get("elapsed") or ""),
            "venue": str(venue.get("name") or ""),
            "normalized_home": normalize_team_name(home, league=league.get("name") or "") if home else "",
            "normalized_away": normalize_team_name(away, league=league.get("name") or "") if away else "",
            "validation_status": "valid" if home and away and kickoff else "invalid",
        }
        rows.append(row)
    return rows


def write_csv(rows: Iterable[Dict[str, Any]], output: str) -> Path:
    target = _safe_output(output)
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIXTURE_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in FIXTURE_COLUMNS})
    return target


def write_raw(payload: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def print_rows(rows: List[Dict[str, Any]], date: str = "") -> None:
    print("API-Football fixtures adapter")
    print(f"- Date: {date or 'fixture'}")
    print(f"- Fixtures normalisees: {len(rows)}")
    leagues = sorted({row.get("league") for row in rows if row.get("league")})
    print(f"- Ligues: {', '.join(leagues[:10]) or 'aucune'}")
    print("- Aucun reseau sans --allow-network.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Adaptateur fixtures API-Football, reseau desactive par defaut.")
    parser.add_argument("--check-config", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--date", default="")
    parser.add_argument("--league-id", default="")
    parser.add_argument("--season", default="")
    parser.add_argument("--from-fixture", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--raw-output", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        config = load_odds_source_config()
        if args.check_config:
            report = validate_config(config)
            print("API-Football fixtures adapter")
            print(f"- Configuration: {'OK' if report['ok'] else 'bloquante'}")
            print(f"- Cle API: {'presente' if get_api_key_from_env('api_football', config) else 'absente'}")
            print("- Aucun reseau lance par --check-config.")
            return 0 if report["ok"] else 1
        if args.dry_run:
            print("API-Football fixtures dry-run")
            print(f"- Date: {args.date or 'n/a'}")
            print("- Aucun reseau lance.")
            return 0
        if args.from_fixture:
            payload = read_fixture(args.from_fixture)
        else:
            if not args.allow_network:
                raise ValueError("Reseau refuse par defaut. Utiliser --dry-run, --from-fixture ou --allow-network.")
            if not args.date:
                raise ValueError("--date requis pour fixtures API-Football")
            payload = fetch_fixtures(args.date, config, league_id=args.league_id, season=args.season)
        rows = normalize_fixtures_payload(payload)
        if args.raw_output:
            print(f"- Raw output ecrit: {write_raw(payload, args.raw_output)}")
        if args.output:
            print(f"- CSV fixtures ecrit: {write_csv(rows, args.output)}")
        print_rows(rows, date=args.date)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
