import argparse
import csv
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List

from odds_source_config import get_api_key_from_env, load_odds_source_config, validate_config
from team_name_normalizer import normalize_team_name


RESULT_COLUMNS = [
    "fixture_id",
    "date",
    "kickoff_time",
    "league_id",
    "league",
    "country",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "status",
    "is_finished",
    "normalized_home",
    "normalized_away",
    "validation_status",
]

FINISHED_STATUS = {"FT", "AET", "PEN"}


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Les resultats API-Football doivent rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def read_fixture(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fetch_results(config: Dict[str, Any], date: str = "", fixture_id: str = "", league_id: str = "", season: str = "") -> Dict[str, Any]:
    source = config.get("api_football") or {}
    key = get_api_key_from_env("api_football", config)
    if not key:
        raise ValueError("Cle API-Football absente dans l'environnement.")
    base_url = str(source.get("base_url") or "https://v3.football.api-sports.io").rstrip("/")
    params: Dict[str, str] = {}
    if fixture_id:
        params["id"] = fixture_id
    if date:
        params["date"] = date
    if league_id:
        params["league"] = league_id
    if season:
        params["season"] = season
    if not params:
        raise ValueError("date, fixture-id ou league-id requis pour resultats API-Football.")
    request = urllib.request.Request(
        f"{base_url}/fixtures?{urllib.parse.urlencode(params)}",
        headers={"x-apisports-key": key},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_results_payload(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for item in payload.get("response") or []:
        fixture = item.get("fixture") or {}
        league = item.get("league") or {}
        teams = item.get("teams") or {}
        goals = item.get("goals") or {}
        score = item.get("score") or {}
        status = fixture.get("status") or {}
        short_status = str(status.get("short") or "")
        home = str((teams.get("home") or {}).get("name") or "")
        away = str((teams.get("away") or {}).get("name") or "")
        home_goals = goals.get("home")
        away_goals = goals.get("away")
        if home_goals is None:
            home_goals = ((score.get("fulltime") or {}).get("home"))
        if away_goals is None:
            away_goals = ((score.get("fulltime") or {}).get("away"))
        kickoff = str(fixture.get("date") or "")
        finished = short_status.upper() in FINISHED_STATUS and home_goals is not None and away_goals is not None
        rows.append({
            "fixture_id": str(fixture.get("id") or ""),
            "date": kickoff[:10] if kickoff else "",
            "kickoff_time": kickoff,
            "league_id": str(league.get("id") or ""),
            "league": str(league.get("name") or ""),
            "country": str(league.get("country") or ""),
            "home_team": home,
            "away_team": away,
            "home_goals": "" if home_goals is None else str(home_goals),
            "away_goals": "" if away_goals is None else str(away_goals),
            "status": short_status,
            "is_finished": "True" if finished else "False",
            "normalized_home": normalize_team_name(home, league=league.get("name") or "") if home else "",
            "normalized_away": normalize_team_name(away, league=league.get("name") or "") if away else "",
            "validation_status": "valid" if home and away and kickoff else "invalid",
        })
    return rows


def write_csv(rows: Iterable[Dict[str, Any]], output: str) -> Path:
    target = _safe_output(output)
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=RESULT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in RESULT_COLUMNS})
    return target


def write_raw(payload: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def print_rows(rows: List[Dict[str, Any]]) -> None:
    print("API-Football results adapter")
    print(f"- Resultats normalises: {len(rows)}")
    print(f"- Matchs termines: {sum(1 for row in rows if row.get('is_finished') == 'True')}")
    print("- Aucun reseau sans --allow-network.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Adaptateur resultats API-Football, reseau desactive par defaut.")
    parser.add_argument("--check-config", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--date", default="")
    parser.add_argument("--fixture-id", default="")
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
            print("API-Football results adapter")
            print(f"- Configuration: {'OK' if report['ok'] else 'bloquante'}")
            print(f"- Cle API: {'presente' if get_api_key_from_env('api_football', config) else 'absente'}")
            print("- Aucun reseau lance par --check-config.")
            return 0 if report["ok"] else 1
        if args.dry_run:
            print("API-Football results dry-run")
            print(f"- Date: {args.date or 'n/a'}")
            print("- Aucun reseau lance.")
            return 0
        if args.from_fixture:
            payload = read_fixture(args.from_fixture)
        else:
            if not args.allow_network:
                raise ValueError("Reseau refuse par defaut. Utiliser --dry-run, --from-fixture ou --allow-network.")
            payload = fetch_results(config, date=args.date, fixture_id=args.fixture_id, league_id=args.league_id, season=args.season)
        rows = normalize_results_payload(payload)
        if args.raw_output:
            print(f"- Raw output ecrit: {write_raw(payload, args.raw_output)}")
        if args.output:
            print(f"- CSV resultats ecrit: {write_csv(rows, args.output)}")
        print_rows(rows)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
