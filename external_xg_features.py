import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from external_xg_lab import detect_columns, first_column, parse_date, parse_float
from team_name_normalizer import normalize_team_name


ROLLING_COLUMNS = [
    "home_xg_for_avg3",
    "home_xg_for_avg5",
    "home_xg_against_avg3",
    "home_xg_against_avg5",
    "away_xg_for_avg3",
    "away_xg_for_avg5",
    "away_xg_against_avg3",
    "away_xg_against_avg5",
    "xg_diff_avg3",
    "xg_diff_avg5",
    "home_xg_trend_3_vs_5",
    "away_xg_trend_3_vs_5",
    "home_xg_matches_available",
    "away_xg_matches_available",
    "xg_source_external_file",
    "xg_join_key",
    "xg_leak_risk",
]


def _round(value: Optional[float], digits: int = 6) -> Optional[float]:
    if value is None:
        return None
    if not math.isfinite(value):
        return None
    return round(value, digits)


def _avg(items: List[float], window: int) -> Optional[float]:
    if len(items) < window:
        return None
    return sum(items[-window:]) / window


def _diff(for_avg: Optional[float], against_avg: Optional[float]) -> Optional[float]:
    if for_avg is None or against_avg is None:
        return None
    return for_avg - against_avg


def _out(value: Any) -> Any:
    return "" if value is None else value


def _ensure_reports_output(output: str) -> Path:
    target = Path(output)
    parts = [part.lower() for part in target.parts]
    if "data" in parts:
        raise ValueError("Le fichier rolling xG ne doit pas etre ecrit dans data/.")
    if "reports" not in parts:
        raise ValueError("Le fichier rolling xG doit etre ecrit dans reports/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def read_external_matches(path: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    target = Path(path)
    with target.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        columns = reader.fieldnames or []
        detected = detect_columns(columns)
        date_col = first_column(detected, "date")
        home_col = first_column(detected, "home_team")
        away_col = first_column(detected, "away_team")
        home_xg_col = first_column(detected, "home_xg")
        away_xg_col = first_column(detected, "away_xg")
        score_col = first_column(detected, "score_home", "score_away")
        if not all((date_col, home_col, away_col, home_xg_col, away_xg_col)):
            raise ValueError("Colonnes externes insuffisantes: date/home/away/home_xg/away_xg requis.")
        matches: List[Dict[str, Any]] = []
        for index, row in enumerate(reader, start=1):
            date_key = parse_date(row.get(date_col))
            home = str(row.get(home_col) or "").strip()
            away = str(row.get(away_col) or "").strip()
            home_xg = parse_float(row.get(home_xg_col))
            away_xg = parse_float(row.get(away_xg_col))
            if not date_key or not home or not away or home_xg is None or away_xg is None:
                continue
            matches.append({
                "external_index": index,
                "date": date_key,
                "home": home,
                "away": away,
                "home_norm": normalize_team_name(home),
                "away_norm": normalize_team_name(away),
                "home_xg": home_xg,
                "away_xg": away_xg,
                "score": row.get(score_col, "") if score_col else row.get("score", ""),
                "source_external_file": target.name,
            })
    meta = {
        "path": str(target),
        "detected_columns": detected,
        "date_min": min((m["date"] for m in matches), default=""),
        "date_max": max((m["date"] for m in matches), default=""),
    }
    return matches, meta


def _team_roll(history: List[Dict[str, Any]], prefix: str) -> Dict[str, Any]:
    xg_for = [item["xg_for"] for item in history]
    xg_against = [item["xg_against"] for item in history]
    for3 = _avg(xg_for, 3)
    for5 = _avg(xg_for, 5)
    against3 = _avg(xg_against, 3)
    against5 = _avg(xg_against, 5)
    return {
        f"{prefix}_xg_for_avg3": _round(for3),
        f"{prefix}_xg_for_avg5": _round(for5),
        f"{prefix}_xg_against_avg3": _round(against3),
        f"{prefix}_xg_against_avg5": _round(against5),
        f"{prefix}_xg_trend_3_vs_5": _round(for3 - for5) if for3 is not None and for5 is not None else None,
        f"{prefix}_xg_matches_available": len(history),
        f"_{prefix}_xg_source_dates": [item["date"] for item in history[-5:]],
    }


def compute_rolling_features(matches: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_date: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for match in matches:
        by_date[match["date"]].append(dict(match))

    history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    out: List[Dict[str, Any]] = []
    for date_key in sorted(by_date):
        daily = sorted(by_date[date_key], key=lambda item: item.get("external_index", 0))
        prepared: List[Dict[str, Any]] = []
        for match in daily:
            home_history = history[match["home_norm"]]
            away_history = history[match["away_norm"]]
            home_roll = _team_roll(home_history, "home")
            away_roll = _team_roll(away_history, "away")
            home_strength3 = _diff(home_roll["home_xg_for_avg3"], home_roll["home_xg_against_avg3"])
            away_strength3 = _diff(away_roll["away_xg_for_avg3"], away_roll["away_xg_against_avg3"])
            home_strength5 = _diff(home_roll["home_xg_for_avg5"], home_roll["home_xg_against_avg5"])
            away_strength5 = _diff(away_roll["away_xg_for_avg5"], away_roll["away_xg_against_avg5"])
            row = {
                **match,
                **home_roll,
                **away_roll,
                "xg_diff_avg3": _round(home_strength3 - away_strength3) if home_strength3 is not None and away_strength3 is not None else None,
                "xg_diff_avg5": _round(home_strength5 - away_strength5) if home_strength5 is not None and away_strength5 is not None else None,
                "_source_dates": sorted(set(home_roll["_home_xg_source_dates"] + away_roll["_away_xg_source_dates"])),
            }
            prepared.append(row)
            out.append(row)
        for match in daily:
            history[match["home_norm"]].append({"date": date_key, "xg_for": match["home_xg"], "xg_against": match["away_xg"]})
            history[match["away_norm"]].append({"date": date_key, "xg_for": match["away_xg"], "xg_against": match["home_xg"]})
    return out


def _match_key(date_key: str, home: Any, away: Any) -> Tuple[str, str, str]:
    return date_key, normalize_team_name(home), normalize_team_name(away)


def read_xgabora_rows(path: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        return list(reader), reader.fieldnames or []


def validate_no_xg_leakage(rows: Iterable[Dict[str, Any]]) -> None:
    for index, row in enumerate(rows, start=1):
        if "home_xg" in row or "away_xg" in row:
            raise ValueError(f"Fuite xG directe ligne {index}: home_xg/away_xg ne doivent pas etre des features predictives.")
        date_key = str(row.get("date") or "")
        source_dates = row.get("_source_dates") or []
        if isinstance(source_dates, str):
            try:
                source_dates = json.loads(source_dates)
            except Exception:
                source_dates = [source_dates] if source_dates else []
        for source_date in source_dates:
            if source_date and date_key and str(source_date) >= date_key:
                raise ValueError(f"Fuite rolling xG ligne {index}: source {source_date} >= match {date_key}.")
        current_home_xg = row.get("_current_home_xg")
        current_away_xg = row.get("_current_away_xg")
        for column in ROLLING_COLUMNS:
            if not column.endswith(("avg3", "avg5")):
                continue
            value = row.get(column)
            if value in ("", None):
                continue
            try:
                number = float(value)
            except Exception:
                continue
            if current_home_xg is not None and abs(number - float(current_home_xg)) < 1e-12 and not source_dates:
                raise ValueError(f"Fuite suspecte ligne {index}: rolling egal au home_xg courant sans historique.")
            if current_away_xg is not None and abs(number - float(current_away_xg)) < 1e-12 and not source_dates:
                raise ValueError(f"Fuite suspecte ligne {index}: rolling egal au away_xg courant sans historique.")


def join_rolling_with_xgabora(rolling_matches: List[Dict[str, Any]], xgabora_rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rolling_by_key = {
        (match["date"], match["home_norm"], match["away_norm"]): match
        for match in rolling_matches
    }
    matched_external_keys = set()
    enriched: List[Dict[str, Any]] = []
    for row in xgabora_rows:
        date_key = str(row.get("date") or row.get("date_key") or "")
        key = _match_key(date_key, row.get("home"), row.get("away"))
        rolling = rolling_by_key.get(key)
        if not rolling:
            continue
        matched_external_keys.add(key)
        item = dict(row)
        for column in ROLLING_COLUMNS:
            if column in {"xg_source_external_file", "xg_join_key", "xg_leak_risk"}:
                continue
            item[column] = _out(rolling.get(column))
        item["xg_source_external_file"] = rolling.get("source_external_file", "")
        item["xg_join_key"] = "|".join(key)
        item["xg_leak_risk"] = "controlled_rolling"
        item["_source_dates"] = rolling.get("_source_dates", [])
        item["_current_home_xg"] = rolling.get("home_xg")
        item["_current_away_xg"] = rolling.get("away_xg")
        enriched.append(item)
    validate_no_xg_leakage([{key: value for key, value in row.items() if key not in ("_current_home_xg", "_current_away_xg")} for row in enriched])
    meta = {
        "matched_external_matches": len(matched_external_keys),
        "external_join_rate": round(len(matched_external_keys) / len(rolling_matches) * 100.0, 2) if rolling_matches else 0.0,
        "enriched_rows": len(enriched),
        "avg3_rows": sum(1 for row in enriched if row.get("home_xg_for_avg3") not in ("", None) and row.get("away_xg_for_avg3") not in ("", None)),
        "avg5_rows": sum(1 for row in enriched if row.get("home_xg_for_avg5") not in ("", None) and row.get("away_xg_for_avg5") not in ("", None)),
    }
    for row in enriched:
        row.pop("_source_dates", None)
        row.pop("_current_home_xg", None)
        row.pop("_current_away_xg", None)
    return enriched, meta


def write_enriched_csv(rows: List[Dict[str, Any]], fieldnames: List[str], output: str) -> Path:
    target = _ensure_reports_output(output)
    final_fields = list(fieldnames)
    for column in ROLLING_COLUMNS:
        if column not in final_fields:
            final_fields.append(column)
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=final_fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return target


def build_external_xg_features(external_path: str, xgabora_path: str, output: str) -> Dict[str, Any]:
    external_matches, external_meta = read_external_matches(external_path)
    rolling = compute_rolling_features(external_matches)
    xgabora_rows, fieldnames = read_xgabora_rows(xgabora_path)
    enriched, join_meta = join_rolling_with_xgabora(rolling, xgabora_rows)
    output_path = write_enriched_csv(enriched, fieldnames, output)
    summary = {
        "external_path": external_path,
        "xgabora_path": xgabora_path,
        "output": str(output_path),
        "external_matches_read": len(external_matches),
        "xgabora_rows_read": len(xgabora_rows),
        "matched_external_matches": join_meta["matched_external_matches"],
        "join_rate": join_meta["external_join_rate"],
        "enriched_rows": join_meta["enriched_rows"],
        "avg3_rows": join_meta["avg3_rows"],
        "avg5_rows": join_meta["avg5_rows"],
        "date_min": external_meta["date_min"],
        "date_max": external_meta["date_max"],
        "anti_leakage": "rolling xG calcule uniquement avec matchs strictement anterieurs; xG direct non exporte",
    }
    (output_path.parent / "external_xg_features_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def print_summary(summary: Dict[str, Any]) -> None:
    print("External xG Rolling Features Lab")
    print(f"- Fichier externe: {summary['external_path']}")
    print(f"- Fichier xgabora/features: {summary['xgabora_path']}")
    print(f"- Sortie: {summary['output']}")
    print(f"- Matchs externes lus: {summary['external_matches_read']}")
    print(f"- Lignes xgabora lues: {summary['xgabora_rows_read']}")
    print(f"- Matchs externes joints: {summary['matched_external_matches']}")
    print(f"- Taux de jointure: {summary['join_rate']}%")
    print(f"- Lignes candidates enrichies: {summary['enriched_rows']}")
    print(f"- Lignes avec rolling avg3 disponible: {summary['avg3_rows']}")
    print(f"- Lignes avec rolling avg5 disponible: {summary['avg5_rows']}")
    print(f"- Periode couverte: {summary['date_min']} -> {summary['date_max']}")
    print("- Avertissement anti-fuite: xG final du match courant non exporte et jamais utilise comme feature predictive.")
    print("- Statut: laboratoire local uniquement, aucun pick automatique.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Construit des rolling features xG pre-match depuis un dataset externe local.")
    parser.add_argument("--external", required=True, help="CSV externe match-level avec xG")
    parser.add_argument("--xgabora", required=True, help="CSV features_modern.csv")
    parser.add_argument("--output", required=True, help="CSV de sortie dans reports/")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        print_summary(build_external_xg_features(args.external, args.xgabora, args.output))
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
