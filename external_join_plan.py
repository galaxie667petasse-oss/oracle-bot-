import argparse
import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from external_dataset_probe import detect_columns, normalize_team_name


def _parse_date(value: Any) -> str:
    from external_dataset_probe import _parse_date as parse_date

    return parse_date(value) or ""


def _best_column(columns: Iterable[str], candidates: Iterable[str], fallback_detected: List[str]) -> str:
    by_norm = {column.strip().lower().replace("_", ""): column for column in columns}
    for candidate in candidates:
        normalized = candidate.lower().replace("_", "")
        if normalized in by_norm:
            return by_norm[normalized]
    return fallback_detected[0] if fallback_detected else ""


def detect_join_columns(path: str) -> Dict[str, str]:
    target = Path(path)
    if target.suffix.lower() != ".csv" or not target.exists():
        return {"date": "", "home": "", "away": "", "competition": ""}
    with target.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        columns = reader.fieldnames or []
    detected = detect_columns(columns)
    return {
        "date": _best_column(columns, ("date", "date_key", "matchdate", "MatchDate"), detected.get("date", [])),
        "home": _best_column(columns, ("home", "home_team", "HomeTeam", "hometeam"), detected.get("home_team", [])),
        "away": _best_column(columns, ("away", "away_team", "AwayTeam", "awayteam"), detected.get("away_team", [])),
        "competition": _best_column(columns, ("competition", "league", "division", "Division"), detected.get("competition", [])),
    }


def _key(row: Dict[str, Any], columns: Dict[str, str]) -> Optional[Tuple[str, str, str]]:
    date_column = columns.get("date", "")
    home_column = columns.get("home", "")
    away_column = columns.get("away", "")
    if not date_column or not home_column or not away_column:
        return None
    date_key = _parse_date(row.get(date_column))
    home = normalize_team_name(row.get(home_column))
    away = normalize_team_name(row.get(away_column))
    if not date_key or not home or not away:
        return None
    return date_key, home, away


def read_match_keys(path: str, columns: Dict[str, str]) -> Dict[str, Any]:
    rows = 0
    keys = set()
    examples: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    target = Path(path)
    if target.suffix.lower() != ".csv" or not target.exists():
        return {"rows": 0, "keys": keys, "examples": examples}
    with target.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows += 1
            key = _key(row, columns)
            if key is None:
                continue
            keys.add(key)
            if len(examples) < 5 and key not in examples:
                examples[key] = {
                    "date": key[0],
                    "home": row.get(columns["home"], ""),
                    "away": row.get(columns["away"], ""),
                    "competition": row.get(columns.get("competition", ""), ""),
                }
    return {"rows": rows, "keys": keys, "examples": examples}


def build_join_plan(xgabora_path: str, external_path: str) -> Dict[str, Any]:
    x_columns = detect_join_columns(xgabora_path)
    external_columns = detect_join_columns(external_path)
    x_data = read_match_keys(xgabora_path, x_columns)
    external_data = read_match_keys(external_path, external_columns)
    x_keys = x_data["keys"]
    external_keys = external_data["keys"]
    matched = sorted(x_keys & external_keys)
    external_unmatched = sorted(external_keys - x_keys)
    x_unmatched = sorted(x_keys - external_keys)
    match_rate = round(len(matched) / len(external_keys) * 100.0, 2) if external_keys else 0.0
    return {
        "xgabora_path": xgabora_path,
        "external_path": external_path,
        "xgabora_columns": x_columns,
        "external_columns": external_columns,
        "xgabora_rows": x_data["rows"],
        "external_rows": external_data["rows"],
        "xgabora_unique_matches": len(x_keys),
        "external_unique_matches": len(external_keys),
        "matched": len(matched),
        "match_rate": match_rate,
        "matched_examples": matched[:5],
        "external_unmatched_examples": external_unmatched[:5],
        "xgabora_unmatched_examples": x_unmatched[:5],
        "recommendations": recommendations(x_columns, external_columns, match_rate),
    }


def recommendations(x_columns: Dict[str, str], external_columns: Dict[str, str], match_rate: float) -> List[str]:
    lines: List[str] = []
    if not all(external_columns.get(key) for key in ("date", "home", "away")):
        lines.append("Jointure fragile: colonnes date/home/away externes incompletes.")
    if match_rate >= 70:
        lines.append("Taux de match eleve: source candidate pour enrichissement apres controle anti-fuite.")
    elif match_rate >= 30:
        lines.append("Taux de match moyen: prevoir table de correspondance des noms d'equipes.")
    else:
        lines.append("Taux de match faible: verifier formats de dates, noms d'equipes et couverture.")
    if not external_columns.get("competition"):
        lines.append("Competition absente ou non detectee: jointure par date/equipes seulement.")
    lines.append("Ne pas creer de dataset final avant backtest train/validation/test.")
    lines.append("Marquer xG final, tirs finaux et stats post-match comme non disponibles avant match.")
    return lines


def print_plan(plan: Dict[str, Any]) -> None:
    print("Plan de jointure externe Oracle Bot")
    print(f"- Xgabora/features: {plan.get('xgabora_path')}")
    print(f"- Externe: {plan.get('external_path')}")
    print(f"- Lignes xgabora: {plan.get('xgabora_rows', 0)}")
    print(f"- Lignes externes: {plan.get('external_rows', 0)}")
    print(f"- Matchs uniques xgabora: {plan.get('xgabora_unique_matches', 0)}")
    print(f"- Matchs uniques externes: {plan.get('external_unique_matches', 0)}")
    print(f"- Matchs potentiellement matches: {plan.get('matched', 0)}")
    print(f"- Taux de match externe: {plan.get('match_rate', 0)}%")
    print("- Colonnes jointure xgabora: " + str(plan.get("xgabora_columns", {})))
    print("- Colonnes jointure externe: " + str(plan.get("external_columns", {})))
    print("- Exemples matches:")
    for example in plan.get("matched_examples") or []:
        print(f"  - {example}")
    print("- Exemples externes non matches:")
    for example in plan.get("external_unmatched_examples") or []:
        print(f"  - {example}")
    print("- Exemples xgabora non matches:")
    for example in plan.get("xgabora_unmatched_examples") or []:
        print(f"  - {example}")
    print("- Recommandations:")
    for line in plan.get("recommendations") or []:
        print(f"  - {line}")
    print("- Rappel: aucun fichier final n'a ete cree et la memoire n'a pas ete modifiee.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Prepare une jointure theorique sans modifier les datasets.")
    parser.add_argument("--xgabora", required=True, help="CSV xgabora/features existant")
    parser.add_argument("--external", required=True, help="CSV externe a comparer")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    print_plan(build_join_plan(args.xgabora, args.external))


if __name__ == "__main__":
    main()
