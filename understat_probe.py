import argparse
import csv
import importlib.util
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


EXPECTED_COLUMNS = [
    "date",
    "league",
    "season",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "home_xg",
    "away_xg",
    "result",
    "source",
    "source_match_id",
]

LEAGUE_MAP = {
    "epl": "ENG-Premier League",
    "premier league": "ENG-Premier League",
    "england": "ENG-Premier League",
    "la liga": "ESP-La Liga",
    "laliga": "ESP-La Liga",
    "bundesliga": "GER-Bundesliga",
    "serie a": "ITA-Serie A",
    "ligue 1": "FRA-Ligue 1",
}

COLUMN_CANDIDATES = {
    "date": ("date", "datetime", "matchdate", "match_date"),
    "league": ("league", "competition", "comp"),
    "season": ("season", "year"),
    "home_team": ("home_team", "hometeam", "home", "h_team", "home_name", "home_name_"),
    "away_team": ("away_team", "awayteam", "away", "a_team", "away_name", "away_name_"),
    "home_goals": ("home_goals", "home_goal", "homegoals", "goals_home", "h_goals", "home_score", "fthg"),
    "away_goals": ("away_goals", "away_goal", "awaygoals", "goals_away", "a_goals", "away_score", "ftag"),
    "home_xg": ("home_xg", "homexg", "xg_home", "h_xg", "hxg", "xghome"),
    "away_xg": ("away_xg", "awayxg", "xg_away", "a_xg", "axg", "xgaway"),
    "source_match_id": ("source_match_id", "match_id", "game_id", "understat_id", "id"),
}

MISSING = {"", "na", "n/a", "nan", "none", "null", "-"}


def normalize_column(name: Any) -> str:
    text = str(name or "").strip().lower()
    return "".join(ch for ch in text if ch.isalnum())


def parse_float(value: Any) -> Optional[float]:
    text = str(value or "").strip().replace(",", ".")
    if text.lower() in MISSING:
        return None
    try:
        number = float(text)
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    return number


def parse_int(value: Any) -> Optional[int]:
    number = parse_float(value)
    if number is None:
        return None
    return int(number)


def parse_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for candidate in (text, text[:10]):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y", "%Y%m%d"):
            try:
                return datetime.strptime(candidate, fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def check_soccerdata_available(module_name: str = "soccerdata") -> Dict[str, Any]:
    spec = importlib.util.find_spec(module_name)
    if spec is None:
        return {
            "available": False,
            "message": "soccerdata est absent. Installation locale optionnelle: python -m pip install soccerdata",
        }
    return {
        "available": True,
        "message": "soccerdata est installe. Les recuperations restent a lancer explicitement.",
    }


def parse_seasons(value: str) -> List[int]:
    seasons = []
    for item in str(value or "").split(","):
        item = item.strip()
        if not item:
            continue
        seasons.append(int(item))
    return seasons


def parse_leagues(value: str) -> Tuple[List[str], List[str]]:
    labels = []
    mapped = []
    for item in str(value or "").split(","):
        label = item.strip()
        if not label:
            continue
        key = label.lower()
        if key not in LEAGUE_MAP:
            raise ValueError(f"Ligue non supportee: {label}. Ligues: EPL, La Liga, Bundesliga, Serie A, Ligue 1.")
        labels.append(label)
        mapped.append(LEAGUE_MAP[key])
    return labels, mapped


def as_path(value: Any) -> Path:
    return value if isinstance(value, Path) else Path(str(value))


def ensure_directory(path: Any) -> Path:
    target = as_path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def validate_output_path(output: Any, create_parent: bool = True) -> Path:
    target = as_path(output)
    parts = [part.lower() for part in target.parts]
    if "data" in parts:
        raise ValueError("Sortie interdite dans data/. Utilisez external_data/understat_probe/.")
    if "external_data" not in parts or "understat_probe" not in parts:
        raise ValueError("La sortie Understat doit rester dans external_data/understat_probe/.")
    if create_parent:
        target.parent.mkdir(parents=True, exist_ok=True)
    return target


def validate_profile_path(profile: Any) -> Path:
    return as_path(profile)


def _value(row: Dict[str, Any], column: str) -> Any:
    return row.get(column, "")


def detect_mapping(columns: Iterable[Any]) -> Dict[str, str]:
    normalized = {normalize_column(column): str(column) for column in columns}
    mapping: Dict[str, str] = {}
    for target, candidates in COLUMN_CANDIDATES.items():
        for candidate in candidates:
            normalized_candidate = normalize_column(candidate)
            if normalized_candidate in normalized:
                mapping[target] = normalized[normalized_candidate]
                break
    return mapping


def _result(home_goals: Any, away_goals: Any) -> str:
    home = parse_int(home_goals)
    away = parse_int(away_goals)
    if home is None or away is None:
        return ""
    if home > away:
        return "H"
    if home < away:
        return "A"
    return "D"


def standardize_records(records: Sequence[Dict[str, Any]], default_league: str = "", default_season: str = "") -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    columns = sorted({str(key) for row in records for key in row.keys()})
    mapping = detect_mapping(columns)
    out: List[Dict[str, Any]] = []
    for row in records:
        home_goals = _value(row, mapping.get("home_goals", ""))
        away_goals = _value(row, mapping.get("away_goals", ""))
        item = {
            "date": parse_date(_value(row, mapping.get("date", ""))),
            "league": str(_value(row, mapping.get("league", "")) or default_league),
            "season": str(_value(row, mapping.get("season", "")) or default_season),
            "home_team": str(_value(row, mapping.get("home_team", ""))).strip(),
            "away_team": str(_value(row, mapping.get("away_team", ""))).strip(),
            "home_goals": "" if parse_int(home_goals) is None else parse_int(home_goals),
            "away_goals": "" if parse_int(away_goals) is None else parse_int(away_goals),
            "home_xg": "" if parse_float(_value(row, mapping.get("home_xg", ""))) is None else parse_float(_value(row, mapping.get("home_xg", ""))),
            "away_xg": "" if parse_float(_value(row, mapping.get("away_xg", ""))) is None else parse_float(_value(row, mapping.get("away_xg", ""))),
            "result": _result(home_goals, away_goals),
            "source": "understat_soccerdata",
            "source_match_id": str(_value(row, mapping.get("source_match_id", ""))).strip(),
        }
        out.append(item)
    recognized = set(mapping.values())
    meta = {
        "mapping": mapping,
        "unrecognized_columns": [column for column in columns if column not in recognized],
        "xg_available": bool(mapping.get("home_xg") and mapping.get("away_xg")),
    }
    deduped = deduplicate_and_sort(out)
    meta["duplicates_removed"] = len(out) - len(deduped)
    return deduped, meta


def deduplicate_and_sort(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        key = (
            str(row.get("date") or ""),
            str(row.get("home_team") or "").strip().lower(),
            str(row.get("away_team") or "").strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(row))
    return sorted(out, key=lambda item: (str(item.get("date") or ""), str(item.get("league") or ""), str(item.get("home_team") or "")))


def write_csv(rows: Sequence[Dict[str, Any]], output: Any) -> Path:
    target = validate_output_path(output)
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=EXPECTED_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in EXPECTED_COLUMNS})
    return target


def records_from_dataframe(dataframe: Any) -> List[Dict[str, Any]]:
    reset = dataframe.reset_index()
    reset.columns = [str(column[-1] if isinstance(column, tuple) else column) for column in reset.columns]
    return reset.to_dict("records")


def fetch_understat_records(league_values: Sequence[str], seasons: Sequence[int], cache_dir: Any = "") -> List[Dict[str, Any]]:
    import soccerdata as sd

    kwargs = {"leagues": list(league_values), "seasons": list(seasons)}
    if cache_dir:
        data_dir = ensure_directory(cache_dir)
        try:
            reader = sd.Understat(data_dir=data_dir, **kwargs)
        except TypeError:
            try:
                reader = sd.Understat(cache_dir=data_dir, **kwargs)
            except TypeError:
                reader = sd.Understat(**kwargs)
    else:
        reader = sd.Understat(**kwargs)
    for method_name in ("read_schedule", "read_games", "read_matches"):
        method = getattr(reader, method_name, None)
        if method is None:
            continue
        data = method()
        return records_from_dataframe(data)
    raise RuntimeError("soccerdata.Understat ne fournit pas read_schedule/read_games/read_matches dans cet environnement.")


def profile_csv(path: Any) -> Dict[str, Any]:
    target = validate_profile_path(path)
    if not target.exists():
        return {"path": str(target), "error": "fichier introuvable", "rows": 0, "verdict": "inutilisable"}
    with target.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        columns = reader.fieldnames or []
    date_values = [parse_date(row.get("date")) for row in rows]
    date_values = [value for value in date_values if value]
    seasons = sorted({str(row.get("season") or "") for row in rows if str(row.get("season") or "").strip()})
    leagues = sorted({str(row.get("league") or "") for row in rows if str(row.get("league") or "").strip()})
    teams = sorted({
        str(row.get("home_team") or "").strip()
        for row in rows if str(row.get("home_team") or "").strip()
    } | {
        str(row.get("away_team") or "").strip()
        for row in rows if str(row.get("away_team") or "").strip()
    })
    xg_rows = [
        row for row in rows
        if parse_float(row.get("home_xg")) is not None and parse_float(row.get("away_xg")) is not None
    ]
    missing = {}
    for column in EXPECTED_COLUMNS:
        missing[column] = sum(1 for row in rows if str(row.get(column) or "").strip().lower() in MISSING)
    by_season: Dict[str, int] = {}
    for row in rows:
        season = str(row.get("season") or "inconnue")
        by_season[season] = by_season.get(season, 0) + 1
    xg_rate = round(len(xg_rows) / len(rows) * 100.0, 2) if rows else 0.0
    missing_required = not date_values or missing.get("home_team", 0) == len(rows) or missing.get("away_team", 0) == len(rows)
    weak_sample = len(rows) < 300
    if not rows or missing_required:
        verdict = "inutilisable"
    elif xg_rate >= 80.0:
        verdict = "exploitable rolling xG"
    elif 30.0 <= xg_rate < 80.0:
        verdict = "fragile"
    else:
        verdict = "inutilisable"
    return {
        "path": str(target),
        "error": "",
        "rows": len(rows),
        "columns": columns,
        "date_min": min(date_values) if date_values else "",
        "date_max": max(date_values) if date_values else "",
        "seasons": seasons,
        "leagues": leagues,
        "teams": len(teams),
        "xg_available_rate": xg_rate,
        "missing_values": missing,
        "matches_by_season": by_season,
        "verdict": verdict,
        "sample_warning": "echantillon faible" if weak_sample else "",
    }


def print_check(module_name: str = "soccerdata") -> None:
    status = check_soccerdata_available(module_name)
    print("Probe Understat multi-saisons")
    print(f"- soccerdata disponible: {'oui' if status['available'] else 'non'}")
    print(f"- {status['message']}")
    print("- Rappel: soccerdata est optionnel et aucune donnee Understat ne modifie les picks.")


def print_profile(profile: Dict[str, Any]) -> None:
    print("Profil CSV Understat local")
    print(f"- Fichier: {profile.get('path')}")
    if profile.get("error"):
        print(f"- Erreur: {profile['error']}")
        return
    print(f"- Lignes: {profile.get('rows', 0)}")
    print(f"- Date min/max: {profile.get('date_min') or 'non detectee'} -> {profile.get('date_max') or 'non detectee'}")
    print(f"- Saisons: {', '.join(profile.get('seasons') or []) or 'non detectees'}")
    print(f"- Ligues: {', '.join(profile.get('leagues') or []) or 'non detectees'}")
    print(f"- Equipes: {profile.get('teams', 0)}")
    print(f"- Taux xG disponible: {profile.get('xg_available_rate', 0)}%")
    print("- Matchs par saison:")
    for season, count in sorted((profile.get("matches_by_season") or {}).items()):
        print(f"  - {season}: {count}")
    print("- Valeurs manquantes:")
    for column, count in (profile.get("missing_values") or {}).items():
        print(f"  - {column}: {count}")
    print(f"- Verdict: {profile.get('verdict')}")
    if profile.get("sample_warning"):
        print(f"- Avertissement: {profile.get('sample_warning')}")
    print("- Rappel: xG final doit devenir rolling pre-match avant tout modele.")


def print_fetch_summary(rows: Sequence[Dict[str, Any]], meta: Dict[str, Any], output: Path) -> None:
    print("Export Understat local termine")
    print(f"- Fichier ecrit: {output}")
    print(f"- Lignes exportees: {len(rows)}")
    print(f"- xG detecte: {'oui' if meta.get('xg_available') else 'non'}")
    print(f"- Doublons retires: {meta.get('duplicates_removed', 0)}")
    if meta.get("unrecognized_columns"):
        print("- Colonnes non reconnues:")
        for column in meta["unrecognized_columns"][:30]:
            print(f"  - {column}")
    if not meta.get("xg_available"):
        print("- Attention: xG absent, fichier inutilisable pour rolling xG.")
    print("- Aucune DB, aucun pick et aucun fichier data/ n'a ete modifie.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Probe local optionnel Understat via soccerdata, sans Telegram ni DB.")
    parser.add_argument("--check", action="store_true", help="Verifie si soccerdata est installe")
    parser.add_argument("--profile", default="", help="Profile un CSV Understat local deja exporte")
    parser.add_argument("--league", default="", help="Ligue ou liste separee par virgules: EPL, La Liga, Bundesliga, Serie A, Ligue 1")
    parser.add_argument("--seasons", default="", help="Saisons separees par virgules, ex: 2020,2021,2022")
    parser.add_argument("--output", default="", help="Sortie CSV dans external_data/understat_probe/")
    parser.add_argument("--dry-run", action="store_true", help="Affiche ce qui serait recupere sans lancer soccerdata")
    parser.add_argument("--cache-dir", default="external_data/soccerdata_cache", help="Cache local soccerdata si supporte")
    parser.add_argument("--limit-seasons", type=int, default=5, help="Limite de saisons autorisee pour eviter une recuperation trop large")
    return parser.parse_args(argv)


def main(argv=None, soccerdata_module: str = "soccerdata") -> int:
    args = parse_args(argv)
    if args.check:
        print_check(soccerdata_module)
        return 0
    if args.profile:
        print_profile(profile_csv(args.profile))
        return 0
    if not args.league or not args.seasons or not args.output:
        print("Erreur: utilisez --check, --profile, ou bien --league + --seasons + --output.")
        return 1
    try:
        league_labels, league_values = parse_leagues(args.league)
        seasons = parse_seasons(args.seasons)
        if len(seasons) > 5:
            print(f"Attention: {len(seasons)} saisons demandees. Recuperation large; verifiez que c'est volontaire.")
        if len(seasons) > args.limit_seasons:
            print(f"Erreur: {len(seasons)} saisons depassent --limit-seasons={args.limit_seasons}.")
            return 1
        if len(league_values) > 1:
            print("Attention: plusieurs ligues demandees. Le volume et les noms d'equipes peuvent compliquer la jointure.")
        output = validate_output_path(args.output, create_parent=not args.dry_run)
        print("Probe Understat multi-saisons")
        print(f"- Ligues demandees: {', '.join(league_labels)}")
        print(f"- Ligues soccerdata: {', '.join(league_values)}")
        print(f"- Saisons: {', '.join(str(season) for season in seasons)}")
        cache_dir = as_path(args.cache_dir)
        print(f"- Cache: {cache_dir}")
        print(f"- Sortie: {output}")
        if args.dry_run:
            print("- Dry-run: aucune recuperation soccerdata, aucun fichier cree.")
            return 0
        status = check_soccerdata_available(soccerdata_module)
        if not status["available"]:
            print(f"- {status['message']}")
            print("- Aucun fichier cree.")
            return 0
        try:
            raw_records = fetch_understat_records(league_values, seasons, cache_dir)
        except Exception as exc:
            print(f"soccerdata est installe mais la recuperation a echoue : {exc}")
            return 1
        default_league = league_labels[0] if len(league_labels) == 1 else ""
        default_season = str(seasons[0]) if len(seasons) == 1 else ""
        rows, meta = standardize_records(raw_records, default_league=default_league, default_season=default_season)
        written = write_csv(rows, str(output))
        print_fetch_summary(rows, meta, written)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
