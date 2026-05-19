import argparse
import csv
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

REQUIRED_COLUMNS = (
    "date",
    "home",
    "away",
    "competition",
    "market_type",
    "pari",
    "odds",
    "result",
    "bookmaker",
    "source",
    "visible",
)
OPTIONAL_COLUMNS = (
    "confidence",
    "danger",
    "value_score",
    "ev_pct",
    "p_market",
    "p_fused",
    "edge_pct",
    "decision",
)
CSV_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
DEFAULT_COMPETITIONS = ("PL", "PD", "SA", "BL1", "FL1", "ELC", "SD", "FL2", "PPL", "DED", "CL", "EL")

FOOTBALL_DATA_COMPS = {
    "PL": "PL",
    "PD": "PD",
    "SA": "SA",
    "BL1": "BL1",
    "FL1": "FL1",
    "ELC": "ELC",
    "SD": "SD",
    "FL2": "FL2",
    "PPL": "PPL",
    "DED": "DED",
    "CL": "CL",
    "EL": "EL",
}

API_FOOTBALL_LEAGUES = {
    "PL": 39,
    "PD": 140,
    "SA": 135,
    "BL1": 78,
    "FL1": 61,
    "ELC": 40,
    "SD": 141,
    "FL2": 62,
    "PPL": 94,
    "DED": 88,
    "CL": 2,
    "EL": 3,
}

THE_ODDS_SPORTS = {
    "PL": "soccer_epl",
    "PD": "soccer_spain_la_liga",
    "SA": "soccer_italy_serie_a",
    "BL1": "soccer_germany_bundesliga",
    "FL1": "soccer_france_ligue_one",
    "ELC": "soccer_efl_champ",
    "SD": "soccer_spain_segunda_division",
    "FL2": "soccer_france_ligue_two",
    "PPL": "soccer_portugal_primeira_liga",
    "DED": "soccer_netherlands_eredivisie",
    "CL": "soccer_uefa_champs_league",
    "EL": "soccer_uefa_europa_league",
}


@dataclass(frozen=True)
class Match:
    date: str
    home: str
    away: str
    competition: str
    home_goals: int
    away_goals: int
    kickoff: str = ""
    source: str = ""


@dataclass(frozen=True)
class Odd:
    price: float
    bookmaker: str
    source: str


class BuildStats:
    def __init__(self):
        self.result_matches = 0
        self.matches_with_odds = 0
        self.rows_created = 0
        self.rows_skipped = 0
        self.competitions = set()
        self.warnings = []

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        print(f"WARNING: {message}", file=sys.stderr)


def _parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _season_for(date_text: str) -> int:
    dt = _parse_date(date_text)
    return dt.year if dt.month >= 7 else dt.year - 1


def _http_json(url: str, params: Dict[str, Any], headers: Optional[Dict[str, str]] = None, timeout: int = 35) -> Tuple[int, Any, str]:
    full_url = f"{url}?{urlencode({k: v for k, v in params.items() if v is not None})}"
    request = Request(full_url, headers=headers or {})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            try:
                return response.status, json.loads(body), body[:500]
            except json.JSONDecodeError:
                return response.status, None, body[:500]
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, None, body[:500]
    except URLError as exc:
        return 0, None, str(exc)


def _is_finished(status: str) -> bool:
    return str(status).upper() in {"FT", "AET", "PEN", "FINISHED", "MATCH FINISHED"}


def _num(value: Any) -> Optional[float]:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if price <= 1.0:
        return None
    return price


def _norm_team(value: str) -> str:
    return " ".join(str(value or "").lower().replace("-", " ").split())


def _same_match(match: Match, event: Dict[str, Any]) -> bool:
    home = _norm_team(event.get("home_team") or event.get("home") or "")
    away = _norm_team(event.get("away_team") or event.get("away") or "")
    return bool(home and away and (_norm_team(match.home) in home or home in _norm_team(match.home)) and (_norm_team(match.away) in away or away in _norm_team(match.away)))


def _snapshot_time(match: Match) -> str:
    if match.kickoff:
        try:
            kickoff = datetime.fromisoformat(match.kickoff.replace("Z", "+00:00")).astimezone(timezone.utc)
            return (kickoff - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pass
    return f"{match.date}T12:00:00Z"


class FootballDataResultsClient:
    def __init__(self, api_key: str, stats: BuildStats):
        self.api_key = api_key
        self.stats = stats

    def fetch(self, date_from: str, date_to: str, competitions: Iterable[str]) -> List[Match]:
        if not self.api_key:
            return []
        matches = []
        headers = {"X-Auth-Token": self.api_key}
        for comp in competitions:
            code = FOOTBALL_DATA_COMPS.get(comp)
            if not code:
                continue
            url = f"https://api.football-data.org/v4/competitions/{code}/matches"
            status, data, raw = _http_json(url, {"dateFrom": date_from, "dateTo": date_to}, headers)
            if status != 200 or not isinstance(data, dict):
                self.stats.warn(f"football-data.org refuse {comp} ({status}): {raw[:180]}")
                continue
            for item in data.get("matches", []) or []:
                score = (item.get("score") or {}).get("fullTime") or {}
                hg, ag = score.get("home"), score.get("away")
                if item.get("status") != "FINISHED" or hg is None or ag is None:
                    self.stats.rows_skipped += 1
                    continue
                utc_date = item.get("utcDate") or ""
                date_text = utc_date[:10] if utc_date else item.get("matchday", date_from)
                matches.append(Match(
                    date=date_text,
                    home=((item.get("homeTeam") or {}).get("name") or "").strip(),
                    away=((item.get("awayTeam") or {}).get("name") or "").strip(),
                    competition=comp,
                    home_goals=int(hg),
                    away_goals=int(ag),
                    kickoff=utc_date,
                    source="football_data",
                ))
            self.stats.competitions.add(comp)
            time.sleep(0.15)
        return matches


class APIFootballResultsClient:
    def __init__(self, api_key: str, stats: BuildStats):
        self.api_key = api_key
        self.stats = stats

    def fetch(self, date_from: str, date_to: str, competitions: Iterable[str]) -> List[Match]:
        if not self.api_key:
            return []
        matches = []
        headers = {"x-apisports-key": self.api_key}
        seasons = range(_season_for(date_from), _season_for(date_to) + 1)
        for comp in competitions:
            league_id = API_FOOTBALL_LEAGUES.get(comp)
            if not league_id:
                continue
            for season in seasons:
                status, data, raw = _http_json(
                    "https://v3.football.api-sports.io/fixtures",
                    {"league": league_id, "season": season, "from": date_from, "to": date_to},
                    headers,
                )
                if status != 200 or not isinstance(data, dict):
                    self.stats.warn(f"API-Football refuse {comp} saison {season} ({status}): {raw[:180]}")
                    continue
                for item in data.get("response", []) or []:
                    fixture = item.get("fixture") or {}
                    teams = item.get("teams") or {}
                    goals = item.get("goals") or {}
                    hg, ag = goals.get("home"), goals.get("away")
                    if not _is_finished((fixture.get("status") or {}).get("short", "")) or hg is None or ag is None:
                        self.stats.rows_skipped += 1
                        continue
                    kickoff = fixture.get("date") or ""
                    matches.append(Match(
                        date=kickoff[:10],
                        home=((teams.get("home") or {}).get("name") or "").strip(),
                        away=((teams.get("away") or {}).get("name") or "").strip(),
                        competition=comp,
                        home_goals=int(hg),
                        away_goals=int(ag),
                        kickoff=kickoff,
                        source="api_football",
                    ))
                self.stats.competitions.add(comp)
                time.sleep(0.15)
        return matches


class HistoricalOddsProvider:
    def get_match_odds(self, match: Match) -> Dict[str, Odd]:
        return {}

    def get_historical_odds(self, match: Match, market_type: str) -> Optional[float]:
        odd = self.get_match_odds(match).get(market_type)
        return odd.price if odd else None


class TheOddsAPIHistoricalProvider(HistoricalOddsProvider):
    unavailable_statuses = {401, 402, 403, 422}

    def __init__(self, api_key: str, stats: BuildStats, regions: str = "eu", bookmaker_preference: Tuple[str, ...] = ("pinnacle",)):
        self.api_key = api_key
        self.stats = stats
        self.regions = regions
        self.bookmaker_preference = bookmaker_preference
        self._disabled = False
        self._cache: Dict[Tuple[str, str, str, str], Dict[str, Odd]] = {}

    def get_match_odds(self, match: Match) -> Dict[str, Odd]:
        if not self.api_key or self._disabled:
            return {}
        sport = THE_ODDS_SPORTS.get(match.competition)
        if not sport:
            self.stats.warn(f"aucun sport The Odds API configuré pour {match.competition}")
            return {}
        cache_key = (sport, match.date, match.home, match.away)
        if cache_key in self._cache:
            return self._cache[cache_key]
        params = {
            "apiKey": self.api_key,
            "regions": self.regions,
            "markets": "h2h,totals,btts",
            "oddsFormat": "decimal",
            "dateFormat": "iso",
            "date": _snapshot_time(match),
        }
        status, data, raw = _http_json(f"https://api.the-odds-api.com/v4/historical/sports/{sport}/odds", params)
        if status in self.unavailable_statuses:
            self._disabled = True
            self.stats.warn(
                "historique des cotes The Odds API indisponible pour cette clé/ce plan "
                f"({status}). Aucune cote ne sera inventée; lignes ignorées sans odds. Réponse: {raw[:180]}"
            )
            return {}
        if status != 200 or not isinstance(data, dict):
            self.stats.warn(f"cotes historiques non récupérées pour {match.home} - {match.away} ({status}): {raw[:180]}")
            return {}
        events = data.get("data") or []
        event = next((item for item in events if _same_match(match, item)), None)
        if not event:
            self._cache[cache_key] = {}
            return {}
        odds = _extract_the_odds_markets(event, match)
        self._cache[cache_key] = odds
        return odds


class OddspapiHistoricalProvider(HistoricalOddsProvider):
    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def get_match_odds(self, match: Match) -> Dict[str, Odd]:
        return {}


class SportsGameOddsHistoricalProvider(HistoricalOddsProvider):
    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def get_match_odds(self, match: Match) -> Dict[str, Odd]:
        return {}


def _bookmakers(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    books = list(event.get("bookmakers") or [])
    books.sort(key=lambda b: 0 if str(b.get("key")).lower() == "pinnacle" else 1)
    return books


def _outcome_price(outcomes: List[Dict[str, Any]], *names: str, point: Optional[float] = None) -> Optional[float]:
    wanted = {name.lower() for name in names}
    for outcome in outcomes or []:
        name = str(outcome.get("name") or "").lower()
        if name not in wanted:
            continue
        if point is not None:
            try:
                if abs(float(outcome.get("point")) - point) > 0.01:
                    continue
            except (TypeError, ValueError):
                continue
        price = _num(outcome.get("price"))
        if price is not None:
            return price
    return None


def _add_odd(out: Dict[str, Odd], key: str, price: Optional[float], bookmaker: str) -> None:
    if price is not None:
        out[key] = Odd(price=price, bookmaker=bookmaker, source="the_odds_api_historical")


def _extract_the_odds_markets(event: Dict[str, Any], match: Match) -> Dict[str, Odd]:
    out: Dict[str, Odd] = {}
    for bookmaker in _bookmakers(event):
        title = bookmaker.get("title") or bookmaker.get("key") or "bookmaker"
        for market in bookmaker.get("markets") or []:
            key = market.get("key")
            outcomes = market.get("outcomes") or []
            if key == "h2h":
                _add_odd(out, "h2h_home", _outcome_price(outcomes, match.home, "home"), title)
                _add_odd(out, "draw", _outcome_price(outcomes, "draw", "nul"), title)
                _add_odd(out, "h2h_away", _outcome_price(outcomes, match.away, "away"), title)
            elif key == "totals":
                _add_odd(out, "over25", _outcome_price(outcomes, "over", point=2.5), title)
                _add_odd(out, "under25", _outcome_price(outcomes, "under", point=2.5), title)
            elif key == "btts":
                _add_odd(out, "btts_yes", _outcome_price(outcomes, "yes", "oui"), title)
                _add_odd(out, "btts_no", _outcome_price(outcomes, "no", "non"), title)
        if out:
            return out
    return out


def get_historical_odds(match: Match, market_type: str, provider: Optional[HistoricalOddsProvider] = None) -> Optional[float]:
    provider = provider or HistoricalOddsProvider()
    return provider.get_historical_odds(match, market_type)


def _market_specs(match: Match) -> List[Tuple[str, str, str, str]]:
    return [
        ("h2h_home", "h2h", f"Victoire {match.home}", "h2h_home"),
        ("h2h_away", "h2h", f"Victoire {match.away}", "h2h_away"),
        ("draw", "draw", "Match nul", "draw"),
        ("over25", "total", "Plus de 2.5 buts", "over25"),
        ("under25", "total", "Moins de 2.5 buts", "under25"),
        ("btts_yes", "btts", "Les deux équipes marquent - Oui", "btts_yes"),
        ("btts_no", "btts", "Les deux équipes marquent - Non", "btts_no"),
    ]


def result_for_market(match: Match, market_key: str) -> str:
    total = match.home_goals + match.away_goals
    checks = {
        "h2h_home": match.home_goals > match.away_goals,
        "h2h_away": match.away_goals > match.home_goals,
        "draw": match.home_goals == match.away_goals,
        "over25": total >= 3,
        "under25": total <= 2,
        "btts_yes": match.home_goals > 0 and match.away_goals > 0,
        "btts_no": match.home_goals == 0 or match.away_goals == 0,
    }
    return "win" if checks.get(market_key, False) else "loss"


def rows_for_match(match: Match, odds: Dict[str, Odd], stats: Optional[BuildStats] = None) -> List[Dict[str, Any]]:
    rows = []
    for odds_key, market_type, pari, market_key in _market_specs(match):
        odd = odds.get(odds_key)
        if not odd or _num(odd.price) is None:
            if stats:
                stats.rows_skipped += 1
            continue
        rows.append({
            "date": match.date,
            "home": match.home,
            "away": match.away,
            "competition": match.competition,
            "market_type": market_type,
            "pari": pari,
            "odds": round(float(odd.price), 2),
            "result": result_for_market(match, market_key),
            "bookmaker": odd.bookmaker,
            "source": odd.source,
            "visible": "non",
            "decision": "REFUSE",
        })
    return rows


def dedupe_rows(rows: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    seen = set()
    out = []
    skipped = 0
    for row in rows:
        key = (row.get("date"), row.get("home"), row.get("away"), row.get("market_type"), row.get("pari"))
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        out.append(row)
    return out, skipped


def _dedupe_matches(matches: Iterable[Match]) -> List[Match]:
    seen = set()
    out = []
    for match in matches:
        if not match.home or not match.away:
            continue
        key = (match.date, _norm_team(match.home), _norm_team(match.away), match.competition)
        if key in seen:
            continue
        seen.add(key)
        out.append(match)
    return out


def write_csv(rows: List[Dict[str, Any]], output: str) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in CSV_COLUMNS})


def build_dataset(date_from: str, date_to: str, output: str, competitions: Iterable[str], do_import: bool = False) -> BuildStats:
    stats = BuildStats()
    competitions = tuple(competitions)
    fd_key = os.getenv("FOOTBALL_DATA_KEY", "").strip()
    football_key = (os.getenv("FOOTBALL_KEY", "") or os.getenv("API_FOOTBALL_KEY", "") or os.getenv("APISPORTS_KEY", "")).strip()
    odds_key = (os.getenv("ODDSPAPI_KEY", "") or os.getenv("ODDS_API_KEY", "") or os.getenv("THE_ODDS_API_KEY", "")).strip()

    matches = []
    matches.extend(FootballDataResultsClient(fd_key, stats).fetch(date_from, date_to, competitions))
    matches.extend(APIFootballResultsClient(football_key, stats).fetch(date_from, date_to, competitions))
    matches = _dedupe_matches(matches)
    stats.result_matches = len(matches)

    if not fd_key and not football_key:
        stats.warn("aucune clé FOOTBALL_DATA_KEY ou FOOTBALL_KEY/API_FOOTBALL_KEY/APISPORTS_KEY: aucun résultat récupéré")
    if not odds_key:
        stats.warn("aucune clé ODDSPAPI_KEY/ODDS_API_KEY/THE_ODDS_API_KEY: aucune cote historique récupérée")

    odds_provider = TheOddsAPIHistoricalProvider(odds_key, stats)
    all_rows = []
    for match in matches:
        odds = odds_provider.get_match_odds(match)
        if not odds:
            stats.rows_skipped += 1
            continue
        stats.matches_with_odds += 1
        all_rows.extend(rows_for_match(match, odds, stats))
        time.sleep(0.15)

    rows, duplicate_count = dedupe_rows(all_rows)
    stats.rows_skipped += duplicate_count
    stats.rows_created = len(rows)
    write_csv(rows, output)

    if do_import:
        if rows:
            from backtest_import import import_csv
            imported, skipped, samples = import_csv(output)
            print(f"Import mémoire terminé: {imported} lignes importées, {skipped} doublons déjà présents, {samples} résultats appris.")
        else:
            print("Import ignoré: aucune ligne avec vraies cotes historiques dans le CSV.")
    return stats


def print_summary(stats: BuildStats, date_from: str, date_to: str, output: str) -> None:
    comps = ", ".join(sorted(stats.competitions)) if stats.competitions else "aucune"
    print("")
    print("Résumé dataset historique")
    print(f"- Période couverte: {date_from} -> {date_to}")
    print(f"- Compétitions couvertes: {comps}")
    print(f"- Matchs résultats récupérés: {stats.result_matches}")
    print(f"- Matchs avec cotes trouvées: {stats.matches_with_odds}")
    print(f"- Lignes CSV créées: {stats.rows_created}")
    print(f"- Lignes ignorées: {stats.rows_skipped}")
    print(f"- Fichier: {output}")
    if stats.warnings:
        print("- Warnings:")
        for warning in stats.warnings[:10]:
            print(f"  - {warning}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Construit un CSV historique avec résultats et vraies cotes historiques.")
    parser.add_argument("--from", dest="date_from", required=True, help="Date de début YYYY-MM-DD")
    parser.add_argument("--to", dest="date_to", required=True, help="Date de fin YYYY-MM-DD")
    parser.add_argument("--output", default="data/historical_backtest.csv", help="Chemin CSV de sortie")
    parser.add_argument("--competitions", default=",".join(DEFAULT_COMPETITIONS), help="Codes compétitions séparés par virgules")
    parser.add_argument("--import", dest="do_import", action="store_true", help="Importe le CSV généré via backtest_import.py")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    _parse_date(args.date_from)
    _parse_date(args.date_to)
    competitions = [c.strip().upper() for c in args.competitions.split(",") if c.strip()]
    stats = build_dataset(args.date_from, args.date_to, args.output, competitions, args.do_import)
    print_summary(stats, args.date_from, args.date_to, args.output)


if __name__ == "__main__":
    main()
