import argparse
import csv
import math
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from team_name_normalizer import normalize_team_name, suggest_team_matches, team_name_similarity


MISSING = {"", "na", "n/a", "nan", "none", "null", "-"}
FUZZY_THRESHOLD = 0.84
PREVIEW_LIMIT = 500

ROLE_ORDER = [
    "date",
    "home_team",
    "away_team",
    "score_home",
    "score_away",
    "home_xg",
    "away_xg",
    "xg",
    "home_xga",
    "away_xga",
    "xga",
    "home_shots",
    "away_shots",
    "shots",
    "home_shots_on_target",
    "away_shots_on_target",
    "shots_on_target",
    "lineups",
    "player_stats",
    "competition",
]

PREVIEW_COLUMNS = [
    "date",
    "home",
    "away",
    "market_type",
    "odds",
    "result",
    "no_vig_probability",
    "home_xg",
    "away_xg",
    "xg_diff",
    "home_xga",
    "away_xga",
    "shots_diff",
    "source_external_file",
    "leak_risk",
]


def normalize_column(name: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name or "").strip().lower())


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


def parse_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    candidates = [text, text[:10]]
    for candidate in candidates:
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y", "%Y%m%d"):
            try:
                return datetime.strptime(candidate, fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _add(detected: Dict[str, List[str]], role: str, column: str) -> None:
    if column not in detected[role]:
        detected[role].append(column)


def detect_columns(columns: Iterable[str]) -> Dict[str, List[str]]:
    detected = {role: [] for role in ROLE_ORDER}
    for column in columns:
        raw = str(column)
        norm = normalize_column(raw)

        if norm in {"date", "matchdate", "matchday", "utcdate", "kickoff", "kickoffdate", "time"} or (norm.endswith("date") and "update" not in norm):
            _add(detected, "date", raw)

        if norm in {"home", "hometeam", "hometeamname", "homeclub", "squadhome", "teamhome", "homename"}:
            _add(detected, "home_team", raw)
        if norm in {"away", "awayteam", "awayteamname", "awayclub", "squadaway", "teamaway", "awayname"}:
            _add(detected, "away_team", raw)

        if norm in {"fthg", "fthome", "homegoals", "homescore", "scorehome", "homegoalsft", "homeftgoals"}:
            _add(detected, "score_home", raw)
        if norm in {"ftag", "ftaway", "awaygoals", "awayscore", "scoreaway", "awaygoalsft", "awayftgoals"}:
            _add(detected, "score_away", raw)

        is_home = "home" in norm or norm.startswith("h")
        is_away = "away" in norm or norm.startswith("a")
        has_xg = "xg" in norm or "expectedgoals" in norm
        has_xga = "xga" in norm or "expectedgoalsagainst" in norm
        has_shots = "shots" in norm or norm in {"sh", "totalshots"}
        has_target = "target" in norm or "sot" in norm or "shotsontarget" in norm

        if has_xga and is_home:
            _add(detected, "home_xga", raw)
        elif has_xga and is_away:
            _add(detected, "away_xga", raw)
        elif has_xga:
            _add(detected, "xga", raw)
        elif has_xg and is_home:
            _add(detected, "home_xg", raw)
        elif has_xg and is_away:
            _add(detected, "away_xg", raw)
        elif has_xg:
            _add(detected, "xg", raw)

        if has_shots and has_target and is_home:
            _add(detected, "home_shots_on_target", raw)
        elif has_shots and has_target and is_away:
            _add(detected, "away_shots_on_target", raw)
        elif has_shots and has_target:
            _add(detected, "shots_on_target", raw)
        elif has_shots and is_home:
            _add(detected, "home_shots", raw)
        elif has_shots and is_away:
            _add(detected, "away_shots", raw)
        elif has_shots:
            _add(detected, "shots", raw)

        if any(token in norm for token in ("lineup", "startingxi", "starter", "formation", "eleven")):
            _add(detected, "lineups", raw)
        if any(token in norm for token in ("player", "minutes", "assists", "xag", "passes", "tackles")):
            _add(detected, "player_stats", raw)
        if norm in {"competition", "league", "division", "comp", "season", "tournament"}:
            _add(detected, "competition", raw)
    return detected


def first_column(detected: Dict[str, List[str]], *roles: str) -> str:
    for role in roles:
        values = detected.get(role) or []
        if values:
            return values[0]
    return ""


def first_value(row: Dict[str, Any], detected: Dict[str, List[str]], *roles: str) -> Any:
    for role in roles:
        for column in detected.get(role) or []:
            value = row.get(column)
            if str(value or "").strip().lower() not in MISSING:
                return value
    return ""


def first_number(row: Dict[str, Any], detected: Dict[str, List[str]], *roles: str) -> Optional[float]:
    for role in roles:
        for column in detected.get(role) or []:
            number = parse_float(row.get(column))
            if number is not None:
                return number
    return None


def discover_csv_files(path: str) -> List[Path]:
    target = Path(path)
    if target.is_file() and target.suffix.lower() == ".csv":
        return [target]
    if target.is_dir():
        return [file for file in sorted(target.rglob("*.csv")) if file.is_file()]
    return []


def read_csv_rows(path: Path) -> Tuple[List[Dict[str, Any]], List[str], str]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
            return rows, reader.fieldnames or [], ""
    except Exception as exc:
        return [], [], str(exc)


def xg_columns(detected: Dict[str, List[str]]) -> List[str]:
    columns: List[str] = []
    for role in ("home_xg", "away_xg", "xg", "home_xga", "away_xga", "xga"):
        columns.extend(detected.get(role) or [])
    return columns


def xg_richness(detected: Dict[str, List[str]]) -> str:
    if detected.get("home_xg") and detected.get("away_xg"):
        return "eleve"
    if xg_columns(detected):
        return "moyen"
    return "absent"


def is_probably_match_level(detected: Dict[str, List[str]]) -> bool:
    has_teams = bool(detected.get("home_team") and detected.get("away_team"))
    has_score = bool(detected.get("score_home") and detected.get("score_away"))
    has_match_signal = bool(has_score or xg_columns(detected) or detected.get("shots"))
    return bool(detected.get("date") and has_teams) or has_match_signal


def xg_is_only_post_match(detected: Dict[str, List[str]]) -> bool:
    cols = xg_columns(detected)
    if not cols:
        return False
    pre_tokens = ("before", "prematch", "pre", "rolling", "avg", "average", "last", "prior")
    return not any(any(token in normalize_column(column) for token in pre_tokens) for column in cols)


def leak_risk(detected: Dict[str, List[str]]) -> str:
    if xg_is_only_post_match(detected) or detected.get("score_home") or detected.get("score_away"):
        return "eleve"
    if detected.get("lineups") or detected.get("shots") or detected.get("shots_on_target"):
        return "moyen"
    return "faible"


def classify_timing(detected: Dict[str, List[str]]) -> Dict[str, List[str]]:
    post_match: List[str] = []
    pre_match: List[str] = []
    ambiguous: List[str] = []
    for role in ("score_home", "score_away", "home_xg", "away_xg", "xg", "home_xga", "away_xga", "xga", "home_shots", "away_shots", "shots", "home_shots_on_target", "away_shots_on_target", "shots_on_target"):
        post_match.extend(detected.get(role) or [])
    for role in ("date", "home_team", "away_team", "competition"):
        pre_match.extend(detected.get(role) or [])
    ambiguous.extend(detected.get("lineups") or [])
    ambiguous.extend(detected.get("player_stats") or [])
    return {"post_match": post_match, "pre_match_possible": pre_match, "ambiguous": ambiguous}


def profile_csv(path: Path) -> Dict[str, Any]:
    rows, columns, error = read_csv_rows(path)
    if error:
        return {"path": str(path), "error": error, "rows": 0, "columns": [], "detected": {role: [] for role in ROLE_ORDER}}
    detected = detect_columns(columns)
    date_column = first_column(detected, "date")
    date_min = ""
    date_max = ""
    years: Dict[str, int] = {}
    for row in rows:
        parsed = parse_date(row.get(date_column)) if date_column else ""
        if not parsed:
            continue
        date_min = min(date_min, parsed) if date_min else parsed
        date_max = max(date_max, parsed) if date_max else parsed
        years[parsed[:4]] = years.get(parsed[:4], 0) + 1
    return {
        "path": str(path),
        "error": "",
        "rows": len(rows),
        "columns": columns,
        "columns_count": len(columns),
        "detected": detected,
        "date_min": date_min,
        "date_max": date_max,
        "years": years,
        "match_level": is_probably_match_level(detected),
        "xg_richness": xg_richness(detected),
        "leak_risk": leak_risk(detected),
        "timing": classify_timing(detected),
    }


def profile_path(path: str) -> Dict[str, Any]:
    files = discover_csv_files(path)
    profiles = [profile_csv(file) for file in files]
    return {
        "path": path,
        "files_read": len(files),
        "profiles": profiles,
        "match_level_files": [profile for profile in profiles if profile.get("match_level")],
    }


def _row_to_match(row: Dict[str, Any], detected: Dict[str, List[str]], source: str) -> Optional[Dict[str, Any]]:
    date_column = first_column(detected, "date")
    home_column = first_column(detected, "home_team")
    away_column = first_column(detected, "away_team")
    if not date_column or not home_column or not away_column:
        return None
    date_key = parse_date(row.get(date_column))
    home_raw = str(row.get(home_column) or "").strip()
    away_raw = str(row.get(away_column) or "").strip()
    home_norm = normalize_team_name(home_raw)
    away_norm = normalize_team_name(away_raw)
    if not date_key or not home_norm or not away_norm:
        return None
    return {
        "date": date_key,
        "home": home_raw,
        "away": away_raw,
        "home_norm": home_norm,
        "away_norm": away_norm,
        "key": (date_key, home_norm, away_norm),
        "row": row,
        "source": source,
        "detected": detected,
    }


def load_match_rows(path: str) -> Dict[str, Any]:
    files = discover_csv_files(path)
    matches: List[Dict[str, Any]] = []
    rows_total = 0
    profiles = []
    for file in files:
        rows, columns, error = read_csv_rows(file)
        detected = detect_columns(columns)
        profiles.append(profile_csv(file) if not error else {"path": str(file), "error": error, "rows": 0, "detected": detected})
        rows_total += len(rows)
        for row in rows:
            match = _row_to_match(row, detected, str(file))
            if match:
                matches.append(match)
    return {"files": files, "rows_total": rows_total, "matches": matches, "profiles": profiles}


def _best_fuzzy_match(external_match: Dict[str, Any], candidates: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], float]:
    best = None
    best_score = 0.0
    for candidate in candidates:
        home_score = team_name_similarity(external_match["home"], candidate["home"])
        away_score = team_name_similarity(external_match["away"], candidate["away"])
        score = round((home_score + away_score) / 2.0, 4)
        if home_score >= 0.78 and away_score >= 0.78 and score > best_score:
            best = candidate
            best_score = score
    if best_score >= FUZZY_THRESHOLD:
        return best, best_score
    return None, best_score


def build_join_plan(xgabora_path: str, external_path: str) -> Dict[str, Any]:
    x_data = load_match_rows(xgabora_path)
    e_data = load_match_rows(external_path)
    x_by_key: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    x_by_date: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for match in x_data["matches"]:
        x_by_key[match["key"]].append(match)
        x_by_date[match["date"]].append(match)

    exact: List[Dict[str, Any]] = []
    fuzzy: List[Dict[str, Any]] = []
    unmatched: List[Dict[str, Any]] = []
    for external_match in e_data["matches"]:
        key = external_match["key"]
        if key in x_by_key:
            exact.append({"external": external_match, "xgabora_matches": x_by_key[key], "similarity": 1.0, "kind": "exact"})
            continue
        candidate, score = _best_fuzzy_match(external_match, x_by_date.get(external_match["date"], []))
        if candidate:
            fuzzy.append({"external": external_match, "xgabora_matches": x_by_key[candidate["key"]], "similarity": score, "kind": "similarite"})
        else:
            unmatched.append(external_match)

    matched_count = len(exact) + len(fuzzy)
    joinable_external = len(e_data["matches"])
    match_rate = round(matched_count / joinable_external * 100.0, 2) if joinable_external else 0.0
    x_names = [match["home"] for match in x_data["matches"]] + [match["away"] for match in x_data["matches"]]
    e_names = [match["home"] for match in unmatched] + [match["away"] for match in unmatched]
    return {
        "xgabora_path": xgabora_path,
        "external_path": external_path,
        "xgabora_rows": x_data["rows_total"],
        "external_rows": e_data["rows_total"],
        "xgabora_joinable_matches": len(x_data["matches"]),
        "external_joinable_matches": joinable_external,
        "exact_matches": exact,
        "fuzzy_matches": fuzzy,
        "unmatched_external": unmatched,
        "matched_total": matched_count,
        "match_rate": match_rate,
        "xgabora_profiles": x_data["profiles"],
        "external_profiles": e_data["profiles"],
        "team_suggestions": suggest_team_matches(e_names, x_names)[:20],
    }


def match_has_xg(match: Dict[str, Any]) -> bool:
    row = match["row"]
    detected = match["detected"]
    return any(first_number(row, detected, role) is not None for role in ("home_xg", "away_xg", "xg", "home_xga", "away_xga", "xga"))


def match_has_odds(match: Dict[str, Any]) -> bool:
    row = match["row"]
    for key, value in row.items():
        norm = normalize_column(key)
        if norm == "odds" or norm.endswith("odds") or "odd" in norm:
            if parse_float(value) is not None:
                return True
    return False


def evaluate_join(xgabora_path: str, external_path: str) -> Dict[str, Any]:
    plan = build_join_plan(xgabora_path, external_path)
    profiles = plan["external_profiles"]
    detected_any = {role: [] for role in ROLE_ORDER}
    date_min = ""
    date_max = ""
    for profile in profiles:
        for role, columns in (profile.get("detected") or {}).items():
            detected_any[role].extend(columns)
        if profile.get("date_min"):
            date_min = min(date_min, profile["date_min"]) if date_min else profile["date_min"]
        if profile.get("date_max"):
            date_max = max(date_max, profile["date_max"]) if date_max else profile["date_max"]

    matched = plan["exact_matches"] + plan["fuzzy_matches"]
    matches_with_xg = [item for item in matched if match_has_xg(item["external"])]
    matches_with_xg_and_odds = [
        item for item in matches_with_xg
        if any(match_has_odds(x_match) for x_match in item["xgabora_matches"])
    ]
    test_matches = [item for item in matches_with_xg if item["external"]["date"] >= "2024-01-01"]
    covers_2024 = bool(date_max and date_max >= "2024-01-01")
    has_date = bool(detected_any["date"] and date_min and date_max)
    has_teams = bool(detected_any["home_team"] and detected_any["away_team"])
    has_external_odds = any(any("odd" in normalize_column(col) or normalize_column(col).endswith("odds") for col in profile.get("columns", [])) for profile in profiles)
    only_post_match_xg = any(xg_is_only_post_match(profile.get("detected") or {}) for profile in profiles)

    notes: List[str] = []
    if not has_external_odds:
        notes.append("Pas de cotes externes detectees: enrichissement seulement, pas remplacement de xgabora.")
    if only_post_match_xg:
        notes.append("xG detecte comme post-match: utilisable en laboratoire, puis a transformer en rolling pre-match.")
    if len(test_matches) < 300:
        notes.append("Moins de 300 matchs xG joints sur 2024+: echantillon test faible.")

    if not has_date:
        verdict = "dataset a eviter"
    elif not has_teams:
        verdict = "dataset a eviter"
    elif plan["match_rate"] < 50:
        verdict = "integration fragile"
    elif only_post_match_xg:
        verdict = "dataset utile seulement laboratoire"
    elif len(test_matches) < 300:
        verdict = "integration fragile"
    else:
        verdict = "integration possible"

    return {
        "plan": plan,
        "date_min": date_min,
        "date_max": date_max,
        "covers_2024_plus": covers_2024,
        "matches_with_xg": len(matches_with_xg),
        "matches_with_xg_and_xgabora_odds": len(matches_with_xg_and_odds),
        "test_matches_with_xg": len(test_matches),
        "has_date": has_date,
        "has_teams": has_teams,
        "has_external_odds": has_external_odds,
        "only_post_match_xg": only_post_match_xg,
        "notes": notes,
        "verdict": verdict,
    }


def _ensure_reports_output(output: str) -> Path:
    target = Path(output)
    parts = [part.lower() for part in target.parts]
    if "data" in parts:
        raise ValueError("Le preview xG ne doit pas etre ecrit dans data/.")
    if "reports" not in parts:
        raise ValueError("Le preview xG doit etre ecrit dans reports/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def build_preview(xgabora_path: str, external_path: str, output: str, limit: int = PREVIEW_LIMIT) -> Dict[str, Any]:
    target = _ensure_reports_output(output)
    plan = build_join_plan(xgabora_path, external_path)
    joined = plan["exact_matches"] + plan["fuzzy_matches"]
    written = 0
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=PREVIEW_COLUMNS)
        writer.writeheader()
        for item in joined:
            external = item["external"]
            e_row = external["row"]
            detected = external["detected"]
            home_xg = first_number(e_row, detected, "home_xg")
            away_xg = first_number(e_row, detected, "away_xg")
            xg_diff = round(home_xg - away_xg, 6) if home_xg is not None and away_xg is not None else ""
            home_xga = first_number(e_row, detected, "home_xga")
            away_xga = first_number(e_row, detected, "away_xga")
            home_shots = first_number(e_row, detected, "home_shots")
            away_shots = first_number(e_row, detected, "away_shots")
            shots_diff = round(home_shots - away_shots, 6) if home_shots is not None and away_shots is not None else ""
            risk = leak_risk(detected)
            for x_match in item["xgabora_matches"]:
                x_row = x_match["row"]
                writer.writerow({
                    "date": x_match["date"],
                    "home": x_match["home"],
                    "away": x_match["away"],
                    "market_type": x_row.get("market_type", ""),
                    "odds": x_row.get("odds", ""),
                    "result": x_row.get("result", ""),
                    "no_vig_probability": x_row.get("no_vig_probability", ""),
                    "home_xg": "" if home_xg is None else home_xg,
                    "away_xg": "" if away_xg is None else away_xg,
                    "xg_diff": xg_diff,
                    "home_xga": "" if home_xga is None else home_xga,
                    "away_xga": "" if away_xga is None else away_xga,
                    "shots_diff": shots_diff,
                    "source_external_file": Path(external["source"]).name,
                    "leak_risk": risk,
                })
                written += 1
                if written >= limit:
                    break
            if written >= limit:
                break
    return {"output": str(target), "rows_written": written, "limit": limit, "match_rate": plan["match_rate"]}


def print_profile_report(report: Dict[str, Any]) -> None:
    print("External xG Integration Lab")
    print(f"- Chemin analyse: {report.get('path')}")
    print(f"- Fichiers lus: {report.get('files_read', 0)}")
    print(f"- Fichiers probablement match-level: {len(report.get('match_level_files') or [])}")
    if not report.get("profiles"):
        print("- Aucun CSV lisible detecte.")
        return
    for profile in report["profiles"]:
        print("")
        print(f"Fichier: {profile.get('path')}")
        if profile.get("error"):
            print(f"- Erreur: {profile['error']}")
            continue
        print(f"- Lignes: {profile.get('rows', 0)}")
        print(f"- Colonnes: {profile.get('columns_count', 0)}")
        print(f"- Date min/max: {profile.get('date_min') or 'non detectee'} -> {profile.get('date_max') or 'non detectee'}")
        years = profile.get("years") or {}
        print("- Annees disponibles: " + (", ".join(f"{year}={count}" for year, count in sorted(years.items())) if years else "non detectees"))
        print(f"- Niveau richesse xG: {profile.get('xg_richness')}")
        print(f"- Risque de fuite: {profile.get('leak_risk')}")
        print(f"- Possibilite jointure xgabora: {'oui' if profile.get('match_level') else 'fragile'}")
        print("- Colonnes detectees:")
        for role in ROLE_ORDER:
            columns = profile.get("detected", {}).get(role) or []
            if columns:
                print(f"  - {role}: {', '.join(columns[:8])}")
        timing = profile.get("timing") or {}
        print("- Anti-fuite:")
        print(f"  - post-match: {', '.join(timing.get('post_match', [])[:12]) or 'aucune'}")
        print(f"  - pre-match possible: {', '.join(timing.get('pre_match_possible', [])[:12]) or 'aucune'}")
        print(f"  - ambigu: {', '.join(timing.get('ambiguous', [])[:12]) or 'aucun'}")
    print("")
    print("- Rappel: aucune source externe ne modifie la memoire ni les picks.")


def _print_match_example(item: Dict[str, Any]) -> str:
    external = item["external"]
    first_x = item["xgabora_matches"][0]
    return f"{external['date']} | externe {external['home']} - {external['away']} -> xgabora {first_x['home']} - {first_x['away']} ({item['kind']}, similarite {item['similarity']})"


def print_join_plan(plan: Dict[str, Any]) -> None:
    print("Plan de jointure xG externe")
    print(f"- Xgabora/features: {plan.get('xgabora_path')}")
    print(f"- Externe: {plan.get('external_path')}")
    print(f"- Lignes xgabora: {plan.get('xgabora_rows', 0)}")
    print(f"- Lignes externes: {plan.get('external_rows', 0)}")
    print(f"- Matchs joinables xgabora: {plan.get('xgabora_joinable_matches', 0)}")
    print(f"- Matchs joinables externes: {plan.get('external_joinable_matches', 0)}")
    print(f"- Matchs matches exactement: {len(plan.get('exact_matches') or [])}")
    print(f"- Matchs matches par similarite: {len(plan.get('fuzzy_matches') or [])}")
    print(f"- Matchs non matches: {len(plan.get('unmatched_external') or [])}")
    print(f"- Taux de match: {plan.get('match_rate', 0)}%")
    print("- Exemples matches:")
    for item in (plan.get("exact_matches") or [])[:3] + (plan.get("fuzzy_matches") or [])[:3]:
        print(f"  - {_print_match_example(item)}")
    print("- Exemples non matches:")
    for item in (plan.get("unmatched_external") or [])[:5]:
        print(f"  - {item['date']} | {item['home']} - {item['away']}")
    if plan.get("team_suggestions"):
        print("- Suggestions de mapping equipe a valider manuellement:")
        for suggestion in plan["team_suggestions"][:8]:
            print(f"  - {suggestion['external_name']} -> {suggestion['suggested_xgabora_name']} ({suggestion['similarity']})")
    print("- Rappel: aucune jointure finale n'a ete ecrite.")


def print_evaluation(evaluation: Dict[str, Any]) -> None:
    plan = evaluation["plan"]
    print("Evaluation jointure xG externe")
    print(f"- Taux de jointure: {plan.get('match_rate', 0)}%")
    print(f"- Matchs avec xG joints: {evaluation.get('matches_with_xg', 0)}")
    print(f"- Matchs avec xG + odds xgabora: {evaluation.get('matches_with_xg_and_xgabora_odds', 0)}")
    print(f"- Periode couverte: {evaluation.get('date_min') or 'non detectee'} -> {evaluation.get('date_max') or 'non detectee'}")
    print(f"- Recouvre 2024+: {'oui' if evaluation.get('covers_2024_plus') else 'non'}")
    print(f"- Matchs test 2024+ avec xG joints: {evaluation.get('test_matches_with_xg', 0)}")
    print(f"- Verdict: {evaluation.get('verdict')}")
    for note in evaluation.get("notes") or []:
        print(f"- Note: {note}")
    print("- Aucune source externe ne doit influencer les picks sans rolling pre-match et backtest.")


def print_preview_result(result: Dict[str, Any]) -> None:
    print("Preview xG externe")
    print(f"- Fichier cree: {result.get('output')}")
    print(f"- Lignes ecrites: {result.get('rows_written', 0)}")
    print(f"- Limite preview: {result.get('limit', 0)}")
    print(f"- Taux de match observe: {result.get('match_rate', 0)}%")
    print("- Ce fichier sert uniquement a verifier la jointure, pas a entrainer le bot.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Laboratoire local d'integration xG externe, sans API ni scraping.")
    parser.add_argument("--profile", default="", help="CSV ou dossier externe a profiler")
    parser.add_argument("--join-plan", action="store_true", help="Affiche une jointure theorique date/home/away")
    parser.add_argument("--evaluate-join", action="store_true", help="Evalue la qualite d'une jointure xG")
    parser.add_argument("--build-preview", action="store_true", help="Construit un petit CSV preview dans reports/")
    parser.add_argument("--xgabora", default="", help="CSV xgabora/features_modern.csv")
    parser.add_argument("--external", default="", help="CSV externe xG a comparer")
    parser.add_argument("--output", default="reports/external_xg_preview.csv", help="Sortie preview, obligatoirement dans reports/")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.profile:
            print_profile_report(profile_path(args.profile))
            return 0
        if args.join_plan:
            if not args.xgabora or not args.external:
                raise ValueError("--join-plan requiert --xgabora et --external.")
            print_join_plan(build_join_plan(args.xgabora, args.external))
            return 0
        if args.evaluate_join:
            if not args.xgabora or not args.external:
                raise ValueError("--evaluate-join requiert --xgabora et --external.")
            print_evaluation(evaluate_join(args.xgabora, args.external))
            return 0
        if args.build_preview:
            if not args.xgabora or not args.external:
                raise ValueError("--build-preview requiert --xgabora et --external.")
            print_preview_result(build_preview(args.xgabora, args.external, args.output))
            return 0
        print("External xG Integration Lab")
        print("- Exemple profil: python external_xg_lab.py --profile external_data/epl_fbref_2024_2025")
        print("- Exemple evaluation: python external_xg_lab.py --evaluate-join --xgabora data/features_modern.csv --external external_data/epl_fbref_2024_2025/matches.csv")
        print("- Aucun telechargement, aucune API, aucun scraping.")
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
