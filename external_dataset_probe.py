import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


SUPPORTED_EXTENSIONS = {".csv", ".json", ".jsonl"}
MISSING_MARKERS = {"", "na", "n/a", "nan", "null", "none", "-"}


COLUMN_PATTERNS = {
    "date": ("date", "matchdate", "utcdate", "kickoff", "time"),
    "home_team": ("hometeam", "home", "squadhome", "home_team", "homeclub", "teamhome"),
    "away_team": ("awayteam", "away", "squadaway", "away_team", "awayclub", "teamaway"),
    "score": ("score", "fthg", "ftag", "fthome", "ftaway", "fulltime", "result"),
    "xg": ("xg", "expectedgoals", "home_xg", "away_xg", "xga", "npxg"),
    "shots": ("shots", "totalshots", "home_shots", "away_shots"),
    "shots_on_target": ("hometarget", "awaytarget", "targetdiff", "totaltarget", "sot", "shotson", "shotsontarget", "on target"),
    "possession": ("possession", "poss", "pos"),
    "lineups": ("lineup", "lineups", "startingxi", "starter", "formation", "eleven"),
    "player_stats": ("player", "players", "minutes", "goals", "assists", "xag", "passes", "tackles"),
    "odds": ("odds", "odd", "b365", "maxhome", "maxdraw", "maxaway", "over25", "under25", "price"),
    "competition": ("competition", "league", "division", "comp", "season"),
    "team_stats": ("team", "squad", "home", "away", "corners", "cards", "fouls", "elo"),
}

POST_MATCH_KEYWORDS = (
    "score",
    "result",
    "fthg",
    "ftag",
    "fthome",
    "ftaway",
    "xg",
    "xga",
    "shots",
    "target",
    "corners",
    "cards",
    "yellow",
    "red",
    "goals",
)

PRE_MATCH_KEYWORDS = (
    "odds",
    "odd",
    "price",
    "elo",
    "form",
    "fixture",
    "date",
    "league",
    "competition",
    "team",
)


def normalize_column(name: Any) -> str:
    text = str(name or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def normalize_team_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\b(fc|afc|cf|sc|the)\b", "", text)
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def _is_missing(value: Any) -> bool:
    return str(value or "").strip().lower() in MISSING_MARKERS


def _parse_float(value: Any) -> Optional[float]:
    text = str(value or "").strip().replace(",", ".")
    if text.lower() in MISSING_MARKERS:
        return None
    try:
        number = float(text)
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    return number


def _parse_date(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    from datetime import datetime

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y", "%Y%m%d"):
        try:
            return datetime.strptime(text[:10], fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return None


def detect_columns(columns: Iterable[str]) -> Dict[str, List[str]]:
    detected = {key: [] for key in COLUMN_PATTERNS}
    for column in columns:
        normalized = normalize_column(column)
        readable = str(column)
        if normalized in {"home", "hometeam", "hometeamname", "squadhome", "homeclub", "teamhome", "homename"}:
            detected["home_team"].append(readable)
        if normalized in {"away", "awayteam", "awayteamname", "squadaway", "awayclub", "teamaway", "awayname"}:
            detected["away_team"].append(readable)
        for category, patterns in COLUMN_PATTERNS.items():
            if category in ("home_team", "away_team"):
                continue
            if any(normalize_column(pattern) in normalized for pattern in patterns):
                if category == "date" and "updated" in normalized:
                    continue
                if category == "odds" and "result" in normalized:
                    continue
                detected[category].append(readable)
    return detected


def classify_column_timing(columns: Iterable[str]) -> Dict[str, List[str]]:
    post_match: List[str] = []
    pre_match: List[str] = []
    ambiguous: List[str] = []
    for column in columns:
        normalized = normalize_column(column)
        is_post = any(normalize_column(keyword) in normalized for keyword in POST_MATCH_KEYWORDS)
        is_pre = any(normalize_column(keyword) in normalized for keyword in PRE_MATCH_KEYWORDS)
        if is_post and not is_pre:
            post_match.append(str(column))
        elif is_pre and not is_post:
            pre_match.append(str(column))
        elif is_post and is_pre:
            ambiguous.append(str(column))
    return {"post_match": post_match, "pre_match_possible": pre_match, "ambiguous": ambiguous}


def _anonymized_example(row: Dict[str, Any], detected: Dict[str, List[str]]) -> Dict[str, Any]:
    keys = []
    for category in ("date", "competition", "home_team", "away_team", "score", "xg", "shots", "shots_on_target", "odds"):
        keys.extend(detected.get(category, [])[:2])
    example: Dict[str, Any] = {}
    for key in keys:
        if key not in row:
            continue
        value = row.get(key)
        if key in detected.get("home_team", []) or key in detected.get("away_team", []):
            value = f"equipe_{abs(hash(str(value))) % 10000}"
        example[key] = value
    return example


def _empty_profile(path: str, error: str = "") -> Dict[str, Any]:
    return {
        "path": path,
        "type": Path(path).suffix.lower().lstrip("."),
        "error": error,
        "rows": 0,
        "columns_count": 0,
        "columns": [],
        "date_min": "",
        "date_max": "",
        "year_distribution": {},
        "detected_columns": {key: [] for key in COLUMN_PATTERNS},
        "missing_rates": {},
        "examples": [],
        "timing": {"post_match": [], "pre_match_possible": [], "ambiguous": []},
        "utility": {},
    }


def _finalize_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    profile["timing"] = classify_column_timing(profile.get("columns", []))
    profile["utility"] = utility_score(profile)
    return profile


def profile_csv(path: str) -> Dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return _empty_profile(path, "fichier introuvable")
    try:
        with target.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            columns = reader.fieldnames or []
            detected = detect_columns(columns)
            missing_counts = {column: 0 for column in columns}
            rows = 0
            examples: List[Dict[str, Any]] = []
            date_min = ""
            date_max = ""
            years: Dict[str, int] = {}
            date_columns = detected.get("date", [])
            for row in reader:
                rows += 1
                for column in columns:
                    if _is_missing(row.get(column)):
                        missing_counts[column] += 1
                if len(examples) < 3:
                    examples.append(_anonymized_example(row, detected))
                for date_column in date_columns[:3]:
                    parsed = _parse_date(row.get(date_column))
                    if parsed:
                        date_min = min(date_min, parsed) if date_min else parsed
                        date_max = max(date_max, parsed) if date_max else parsed
                        years[parsed[:4]] = years.get(parsed[:4], 0) + 1
                        break
            missing_rates = {
                column: round(missing_counts[column] / rows * 100.0, 2) if rows else 0.0
                for column in columns
            }
            return _finalize_profile({
                "path": str(target),
                "type": "csv",
                "error": "",
                "rows": rows,
                "columns_count": len(columns),
                "columns": columns,
                "date_min": date_min,
                "date_max": date_max,
                "year_distribution": years,
                "detected_columns": detected,
                "missing_rates": missing_rates,
                "examples": examples,
            })
    except Exception as exc:
        return _empty_profile(path, f"lecture impossible: {exc}")


def _rows_from_json(path: Path) -> Tuple[List[Dict[str, Any]], str]:
    try:
        if path.suffix.lower() == ".jsonl":
            rows = []
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    item = json.loads(line)
                    if isinstance(item, dict):
                        rows.append(item)
            return rows, ""
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)], ""
        if isinstance(data, dict):
            for value in data.values():
                if isinstance(value, list) and all(isinstance(item, dict) for item in value[:5]):
                    return value, ""
            return [data], ""
        return [], "format JSON non tabulaire"
    except Exception as exc:
        return [], f"lecture impossible: {exc}"


def profile_json(path: str) -> Dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return _empty_profile(path, "fichier introuvable")
    rows_data, error = _rows_from_json(target)
    if error:
        return _empty_profile(path, error)
    columns = sorted({key for row in rows_data for key in row.keys()})
    detected = detect_columns(columns)
    missing_counts = {column: 0 for column in columns}
    date_min = ""
    date_max = ""
    years: Dict[str, int] = {}
    examples: List[Dict[str, Any]] = []
    for row in rows_data:
        for column in columns:
            if _is_missing(row.get(column)):
                missing_counts[column] += 1
        if len(examples) < 3:
            examples.append(_anonymized_example(row, detected))
        for date_column in detected.get("date", [])[:3]:
            parsed = _parse_date(row.get(date_column))
            if parsed:
                date_min = min(date_min, parsed) if date_min else parsed
                date_max = max(date_max, parsed) if date_max else parsed
                years[parsed[:4]] = years.get(parsed[:4], 0) + 1
                break
    rows = len(rows_data)
    missing_rates = {
        column: round(missing_counts[column] / rows * 100.0, 2) if rows else 0.0
        for column in columns
    }
    return _finalize_profile({
        "path": str(target),
        "type": target.suffix.lower().lstrip("."),
        "error": "",
        "rows": rows,
        "columns_count": len(columns),
        "columns": columns,
        "date_min": date_min,
        "date_max": date_max,
        "year_distribution": years,
        "detected_columns": detected,
        "missing_rates": missing_rates,
        "examples": examples,
    })


def profile_file(path: str) -> Dict[str, Any]:
    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        return profile_csv(path)
    if suffix in (".json", ".jsonl"):
        return profile_json(path)
    return _empty_profile(path, "extension non supportee")


def profile_folder(path: str) -> Dict[str, Any]:
    target = Path(path)
    if not target.exists() or not target.is_dir():
        return {"path": path, "error": "dossier introuvable", "files": [], "utility": {}}
    files = [
        file for file in sorted(target.rglob("*"))
        if file.is_file() and file.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    profiles = [profile_file(str(file)) for file in files]
    return {
        "path": str(target),
        "error": "",
        "files": profiles,
        "utility": aggregate_folder_utility(profiles),
    }


def _has(profile: Dict[str, Any], category: str) -> bool:
    return bool(profile.get("detected_columns", {}).get(category))


def _score_from_count(count: int, maximum: int = 2) -> int:
    if count <= 0:
        return 0
    return min(5, 2 + min(3, count // maximum))


def utility_score(profile: Dict[str, Any]) -> Dict[str, Any]:
    detected = profile.get("detected_columns", {})
    timing = classify_column_timing(profile.get("columns", []))
    scores = {
        "match_results": min(5, (_score_from_count(len(detected.get("date", [])), 1) + _score_from_count(len(detected.get("score", [])), 2) + _score_from_count(len(detected.get("home_team", [])) + len(detected.get("away_team", [])), 2)) // 2),
        "odds": _score_from_count(len(detected.get("odds", [])), 2),
        "xg": _score_from_count(len(detected.get("xg", [])), 1),
        "shots": _score_from_count(len(detected.get("shots", [])) + len(detected.get("shots_on_target", [])), 2),
        "lineups": _score_from_count(len(detected.get("lineups", [])), 1),
        "player_stats": _score_from_count(len(detected.get("player_stats", [])), 3),
        "team_stats": _score_from_count(len(detected.get("team_stats", [])), 4),
        "recency": recency_score(profile.get("date_max", "")),
        "join_possible_with_xgabora": join_score(profile),
    }
    leak_risk = leak_risk_level(timing, scores)
    verdict = verdict_from_scores(scores, leak_risk)
    return {**scores, "leak_risk": leak_risk, "verdict": verdict}


def recency_score(date_max: str) -> int:
    if not date_max or len(date_max) < 4:
        return 0
    try:
        year = int(date_max[:4])
    except ValueError:
        return 0
    if year >= 2025:
        return 5
    if year == 2024:
        return 4
    if year >= 2022:
        return 3
    if year >= 2018:
        return 2
    return 1


def join_score(profile: Dict[str, Any]) -> int:
    score = 0
    if _has(profile, "date"):
        score += 2
    if _has(profile, "home_team") and _has(profile, "away_team"):
        score += 2
    if _has(profile, "competition"):
        score += 1
    return min(5, score)


def leak_risk_level(timing: Dict[str, List[str]], scores: Dict[str, int]) -> str:
    post_count = len(timing.get("post_match", [])) + len(timing.get("ambiguous", []))
    if scores.get("xg", 0) >= 3 or scores.get("shots", 0) >= 3 or post_count >= 6:
        return "eleve"
    if scores.get("match_results", 0) >= 3 or post_count >= 2:
        return "moyen"
    return "faible"


def verdict_from_scores(scores: Dict[str, int], leak_risk: str) -> str:
    if scores.get("match_results", 0) >= 4 and scores.get("odds", 0) >= 4 and scores.get("join_possible_with_xgabora", 0) >= 4 and leak_risk != "eleve":
        return "utiliser comme base principale"
    if scores.get("join_possible_with_xgabora", 0) >= 4 and (scores.get("xg", 0) >= 3 or scores.get("shots", 0) >= 3 or scores.get("lineups", 0) >= 3):
        return "utiliser comme enrichissement"
    if scores.get("xg", 0) >= 3 or scores.get("shots", 0) >= 3 or scores.get("player_stats", 0) >= 3:
        return "utiliser seulement comme laboratoire"
    return "eviter"


def aggregate_folder_utility(profiles: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not profiles:
        return {"verdict": "eviter", "leak_risk": "moyen"}
    keys = ("match_results", "odds", "xg", "shots", "lineups", "player_stats", "team_stats", "recency", "join_possible_with_xgabora")
    scores = {key: max(int((profile.get("utility") or {}).get(key, 0)) for profile in profiles) for key in keys}
    risks = [(profile.get("utility") or {}).get("leak_risk", "faible") for profile in profiles]
    leak_risk = "eleve" if "eleve" in risks else "moyen" if "moyen" in risks else "faible"
    scores["leak_risk"] = leak_risk
    scores["verdict"] = verdict_from_scores(scores, leak_risk)
    return scores


def print_profile(profile: Dict[str, Any], compact: bool = False) -> None:
    print(f"Profil dataset: {profile.get('path')}")
    if profile.get("error"):
        print(f"- Erreur: {profile['error']}")
        return
    print(f"- Type: {profile.get('type')}")
    print(f"- Lignes: {profile.get('rows', 0)}")
    print(f"- Colonnes: {profile.get('columns_count', 0)}")
    print(f"- Date min: {profile.get('date_min') or 'non detectee'}")
    print(f"- Date max: {profile.get('date_max') or 'non detectee'}")
    years = profile.get("year_distribution") or {}
    if years:
        print("- Distribution par annee: " + ", ".join(f"{year}={count}" for year, count in sorted(years.items())))
    print("- Colonnes utiles detectees:")
    for category, columns in (profile.get("detected_columns") or {}).items():
        if columns:
            print(f"  - {category}: {', '.join(columns[:10])}")
    print("- Anti-fuite:")
    timing = profile.get("timing") or {}
    print(f"  - post-match: {', '.join(timing.get('post_match', [])[:12]) or 'aucune'}")
    print(f"  - pre-match possibles: {', '.join(timing.get('pre_match_possible', [])[:12]) or 'aucune'}")
    if timing.get("ambiguous"):
        print(f"  - ambigues: {', '.join(timing.get('ambiguous', [])[:12])}")
    print("- Valeurs manquantes principales:")
    rates = profile.get("missing_rates") or {}
    for column, rate in sorted(rates.items(), key=lambda item: item[1], reverse=True)[:10]:
        print(f"  - {column}: {rate}%")
    if not compact:
        print("- Exemples anonymises:")
        for example in profile.get("examples") or []:
            print(f"  - {example}")
    print_utility(profile.get("utility") or {})


def print_utility(utility: Dict[str, Any]) -> None:
    if not utility:
        return
    print("- Score utilite Oracle:")
    for key in ("match_results", "odds", "xg", "shots", "lineups", "player_stats", "team_stats", "recency", "join_possible_with_xgabora"):
        print(f"  - {key}: {utility.get(key, 0)}/5")
    print(f"  - leak_risk: {utility.get('leak_risk')}")
    print(f"  - verdict: {utility.get('verdict')}")
    print("- Rappel anti-fuite: xG final, tirs finaux, corners finaux et resultats ne doivent pas predire le meme match.")


def print_folder_report(report: Dict[str, Any]) -> None:
    print(f"Profil dossier externe: {report.get('path')}")
    if report.get("error"):
        print(f"- Erreur: {report['error']}")
        return
    print(f"- Fichiers supportes detectes: {len(report.get('files') or [])}")
    print_utility(report.get("utility") or {})
    for profile in report.get("files") or []:
        print("")
        print_profile(profile, compact=True)


def print_list() -> None:
    print("External Dataset Lab Oracle Bot")
    print("- Commandes:")
    print("  - python external_dataset_probe.py --profile-csv chemin/vers/fichier.csv")
    print("  - python external_dataset_probe.py --profile-folder chemin/vers/dossier")
    print("  - python external_dataset_probe.py --recommend chemin/vers/fichier.csv")
    print("- Extensions supportees: csv, json, jsonl")
    print("- Priorite recherche: dataset EPL/FBref/Kaggle riche avec date, equipes, resultats, xG, tirs, tirs cadres, lineups et stats joueurs/equipes.")
    print("- Aucun telechargement, aucune API, aucun scraping: fournissez un fichier local.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Profile des datasets externes locaux sans API ni scraping.")
    parser.add_argument("--list", action="store_true", help="Liste les capacites du laboratoire externe")
    parser.add_argument("--profile-csv", default="", help="Profile un CSV externe")
    parser.add_argument("--profile-folder", default="", help="Profile un dossier de CSV/JSON/JSONL")
    parser.add_argument("--recommend", default="", help="Profile et affiche une recommandation d'usage")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    if args.list:
        print_list()
        return
    if args.profile_csv:
        print_profile(profile_csv(args.profile_csv))
        return
    if args.profile_folder:
        print_folder_report(profile_folder(args.profile_folder))
        return
    if args.recommend:
        profile = profile_file(args.recommend)
        print_profile(profile)
        print("- Recommandation finale:")
        print(f"  - {profile.get('utility', {}).get('verdict', 'eviter')}")
        if profile.get("utility", {}).get("odds", 0) < 3 and profile.get("utility", {}).get("xg", 0) >= 3:
            print("  - Dataset riche sans cotes: ne remplace pas xgabora, usage enrichissement/laboratoire seulement.")
        return
    print_list()


if __name__ == "__main__":
    main()
