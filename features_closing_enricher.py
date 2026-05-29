import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from closing_odds_probe import probe_csv
from external_xg_lab import parse_date
from team_name_normalizer import normalize_team_name


ADDED_COLUMNS = [
    "taken_odds",
    "closing_odds",
    "closing_source",
    "closing_implied_probability",
    "clv_percent",
]


def parse_float(value: Any) -> Optional[float]:
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        number = float(text)
    except Exception:
        return None
    if not math.isfinite(number) or number <= 1.0:
        return None
    return number


def ensure_output_path(path: str) -> Path:
    target = Path(path)
    parts = [part.lower() for part in target.parts]
    if "data" in parts:
        raise ValueError("La preview features closing ne doit pas etre ecrite dans data/. Utiliser reports/.")
    if "reports" not in parts:
        raise ValueError("La preview features closing doit etre ecrite dans reports/.")
    if target.name.lower() == "features_modern.csv":
        raise ValueError("Interdiction d'ecraser data/features_modern.csv.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _first_column(columns: Iterable[str], candidates: Iterable[str]) -> str:
    lookup = {str(name).lower(): str(name) for name in columns}
    for candidate in candidates:
        value = lookup.get(candidate.lower())
        if value:
            return value
    return ""


def _match_key(date: Any, home: Any, away: Any) -> Tuple[str, str, str]:
    return (
        parse_date(date),
        normalize_team_name(home, use_aliases=True),
        normalize_team_name(away, use_aliases=True),
    )


def _read_csv(path: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        return list(reader), reader.fieldnames or []


def _source_index(source_path: str) -> Tuple[Dict[Tuple[str, str, str], Dict[str, Any]], Dict[str, Any], List[str]]:
    rows, columns = _read_csv(source_path)
    date_col = _first_column(columns, ["Date", "date", "date_key", "MatchDate"])
    home_col = _first_column(columns, ["HomeTeam", "home", "home_team"])
    away_col = _first_column(columns, ["AwayTeam", "away", "away_team"])
    if not date_col or not home_col or not away_col:
        raise ValueError("Source closing sans colonnes date/home/away exploitables.")
    index: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for row in rows:
        key = _match_key(row.get(date_col), row.get(home_col), row.get(away_col))
        if key[0] and key[1] and key[2] and key not in index:
            index[key] = row
    return index, {"date_col": date_col, "home_col": home_col, "away_col": away_col, "rows": len(rows)}, columns


def _feature_key(row: Dict[str, Any]) -> Tuple[str, str, str]:
    return _match_key(row.get("date") or row.get("date_key"), row.get("home") or row.get("home_team"), row.get("away") or row.get("away_team"))


def _closing_mapping_for_feature(row: Dict[str, Any], mapping: Dict[str, str]) -> str:
    market = str(row.get("market_type") or "").lower()
    if market == "h2h":
        if str(row.get("is_home_pick") or "") in {"1", "true", "True"}:
            return mapping.get("h2h_home", "")
        if str(row.get("is_away_pick") or "") in {"1", "true", "True"}:
            return mapping.get("h2h_away", "")
        if str(row.get("is_draw") or "") in {"1", "true", "True"} or "draw" in str(row.get("pari") or "").lower() or "nul" in str(row.get("pari") or "").lower():
            return mapping.get("h2h_draw", "")
    if market == "draw":
        return mapping.get("h2h_draw", "")
    if market == "total":
        if str(row.get("is_over") or "") in {"1", "true", "True"} or "plus" in str(row.get("pari") or "").lower() or "over" in str(row.get("pari") or "").lower():
            return mapping.get("total_over", "")
        if str(row.get("is_under") or "") in {"1", "true", "True"} or "moins" in str(row.get("pari") or "").lower() or "under" in str(row.get("pari") or "").lower():
            return mapping.get("total_under", "")
    return ""


def enrich_features_with_closing(features_path: str, source_path: str, output: str) -> Dict[str, Any]:
    output_path = ensure_output_path(output)
    features, feature_columns = _read_csv(features_path)
    source_index, source_meta, _source_columns = _source_index(source_path)
    probe = probe_csv(source_path)
    detected = ((probe.get("detected_columns") or {}).get("all_closing") or [])
    mapping = probe.get("recommended_mapping") or {}
    final_columns = list(feature_columns)
    for column in detected:
        if column not in final_columns:
            final_columns.append(column)
    for column in ADDED_COLUMNS:
        if column not in final_columns:
            final_columns.append(column)

    matched = 0
    with_closing = 0
    rows_out: List[Dict[str, Any]] = []
    for row in features:
        out = dict(row)
        source = source_index.get(_feature_key(row))
        if source:
            matched += 1
            for column in detected:
                out[column] = source.get(column, "")
            closing_column = _closing_mapping_for_feature(row, mapping)
            closing_odds = parse_float(source.get(closing_column)) if closing_column else None
            taken_odds = parse_float(row.get("odds") or row.get("taken_odds"))
            out["taken_odds"] = "" if taken_odds is None else taken_odds
            out["closing_odds"] = "" if closing_odds is None else closing_odds
            out["closing_source"] = closing_column
            out["closing_implied_probability"] = round(1.0 / closing_odds, 8) if closing_odds else ""
            out["clv_percent"] = round(taken_odds / closing_odds - 1.0, 8) if taken_odds and closing_odds else ""
            if closing_odds:
                with_closing += 1
        rows_out.append(out)

    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=final_columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows_out:
            writer.writerow({column: row.get(column, "") for column in final_columns})

    summary = {
        "features_path": features_path,
        "source_path": source_path,
        "output": str(output_path),
        "features_rows": len(features),
        "source_rows": source_meta.get("rows"),
        "matched_rows": matched,
        "rows_with_closing": with_closing,
        "closing_coverage": round(with_closing / len(features) * 100.0, 2) if features else 0.0,
        "source_has_closing": bool(probe.get("closing_available")),
        "detected_closing_columns": detected,
        "recommended_mapping": mapping,
        "warnings": [] if probe.get("closing_available") else ["Source sans closing odds detectees: enrichissement CLV impossible."],
        "lab_only": True,
        "can_influence_picks": False,
    }
    (output_path.parent / "features_closing_enricher_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def print_summary(summary: Dict[str, Any]) -> None:
    print("Features Closing Enricher Oracle Bot")
    print(f"- Features source: {summary.get('features_path')}")
    print(f"- CSV closing source: {summary.get('source_path')}")
    print(f"- Sortie preview: {summary.get('output')}")
    print(f"- Lignes features: {summary.get('features_rows')}")
    print(f"- Lignes matchees source: {summary.get('matched_rows')}")
    print(f"- Lignes avec closing exploitable: {summary.get('rows_with_closing')}")
    print(f"- Coverage closing: {summary.get('closing_coverage')}%")
    for warning in summary.get("warnings") or []:
        print(f"- Avertissement: {warning}")
    print("- Laboratoire seulement: data/features_modern.csv n'est pas modifie.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Construit une preview features enrichie closing odds dans reports/, sans modifier data/.")
    parser.add_argument("--features", required=True, help="CSV features existant")
    parser.add_argument("--source", required=True, help="CSV source, ex: data/MATCHES.csv")
    parser.add_argument("--output", default="reports/features_with_closing_preview.csv", help="CSV preview dans reports/")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        summary = enrich_features_with_closing(args.features, args.source, args.output)
        print_summary(summary)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
