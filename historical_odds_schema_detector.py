import argparse
import csv
import html
import json
import math
import re
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


ODDS_MIN = 1.01
ODDS_MAX = 100.0
ODDS_TYPICAL_MAX = 20.0

DATE_CANDIDATES = ("date", "match_date", "Date", "MatchDate", "kickoff_date")
LEAGUE_CANDIDATES = ("league", "competition", "division", "Div", "League")
HOME_CANDIDATES = ("home_team", "home", "HomeTeam", "Home", "HT")
AWAY_CANDIDATES = ("away_team", "away", "AwayTeam", "Away", "AT")
HOME_GOALS_CANDIDATES = ("home_goals", "FTHG", "HG", "home_score")
AWAY_GOALS_CANDIDATES = ("away_goals", "FTAG", "AG", "away_score")
RESULT_CANDIDATES = ("result", "FTR", "full_time_result")
BOOKMAKER_CANDIDATES = ("bookmaker", "book", "source", "odds_source")

OPENING_HOME = ("B365H", "PSH", "AvgH", "MaxH", "OpenH", "opening_home", "home_open")
OPENING_DRAW = ("B365D", "PSD", "AvgD", "MaxD", "OpenD", "opening_draw", "draw_open")
OPENING_AWAY = ("B365A", "PSA", "AvgA", "MaxA", "OpenA", "opening_away", "away_open")
CLOSING_HOME = ("B365CH", "PSCH", "AvgCH", "MaxCH", "C_LTH", "C_VCH", "closing_home", "home_close")
CLOSING_DRAW = ("B365CD", "PSCD", "AvgCD", "MaxCD", "C_LTD", "C_VCD", "closing_draw", "draw_close")
CLOSING_AWAY = ("B365CA", "PSCA", "AvgCA", "MaxCA", "C_LTA", "C_VCA", "closing_away", "away_close")


def ensure_reports_path(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le rapport schema historique ne doit pas etre ecrit dans data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _to_float(value: Any) -> Optional[float]:
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        number = float(text)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def read_sample(csv_path: str, max_rows: int = 5000) -> tuple[List[str], List[Dict[str, Any]], int]:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV historique introuvable: {csv_path}")
    rows: List[Dict[str, Any]] = []
    total = 0
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        for row in reader:
            total += 1
            if len(rows) < max_rows:
                rows.append(dict(row))
    return fieldnames, rows, total


def column_profile(rows: List[Dict[str, Any]], column: str, max_examples: int = 8) -> Dict[str, Any]:
    non_empty = 0
    numeric = 0
    text = 0
    values: List[float] = []
    examples: List[str] = []
    for row in rows:
        raw = str(row.get(column) or "").strip()
        if not raw:
            continue
        non_empty += 1
        if len(examples) < max_examples:
            examples.append(raw)
        number = _to_float(raw)
        if number is None:
            text += 1
            continue
        numeric += 1
        values.append(number)
    plausible = [v for v in values if ODDS_MIN <= v <= ODDS_MAX]
    typical = [v for v in values if ODDS_MIN <= v <= ODDS_TYPICAL_MAX]
    small = [v for v in values if 0 <= v <= 1]
    total_rows = len(rows)
    if non_empty == 0:
        verdict = "mostly_empty"
        reason = "colonne vide dans l'echantillon"
    elif non_empty / max(total_rows, 1) < 0.10:
        verdict = "mostly_empty"
        reason = "couverture trop faible"
    elif numeric / max(non_empty, 1) < 0.50:
        verdict = "text_or_code"
        reason = "valeurs surtout textuelles"
    elif numeric and len(plausible) / numeric >= 0.80 and len(typical) / numeric >= 0.65 and len(small) / numeric <= 0.10:
        verdict = "decimal_odds_plausible"
        reason = "valeurs compatibles avec des cotes decimales"
    elif numeric:
        verdict = "numeric_but_not_odds"
        reason = "valeurs numeriques mais non compatibles avec des cotes"
    else:
        verdict = "unknown"
        reason = "profil insuffisant"
    return {
        "column": column,
        "rows_sampled": total_rows,
        "non_empty": non_empty,
        "non_empty_rate": round(non_empty / max(total_rows, 1) * 100.0, 2),
        "numeric_count": numeric,
        "text_count": text,
        "examples": examples,
        "min": round(min(values), 6) if values else None,
        "max": round(max(values), 6) if values else None,
        "mean": round(statistics.fmean(values), 6) if values else None,
        "median": round(statistics.median(values), 6) if values else None,
        "plausible_decimal_odds": len(plausible),
        "typical_decimal_odds": len(typical),
        "zero_one_values": len(small),
        "verdict": verdict,
        "verdict_reason": reason,
    }


def _find_present(fieldnames: Sequence[str], candidates: Iterable[str]) -> List[str]:
    lookup = {_norm(name): name for name in fieldnames}
    found: List[str] = []
    for candidate in candidates:
        value = lookup.get(_norm(candidate))
        if value and value not in found:
            found.append(value)
    return found


def _first_plausible(rows: List[Dict[str, Any]], fieldnames: Sequence[str], candidates: Iterable[str]) -> Optional[str]:
    for column in _find_present(fieldnames, candidates):
        if column_profile(rows, column)["verdict"] == "decimal_odds_plausible":
            return column
    return None


def _suspect_columns(fieldnames: Sequence[str]) -> List[str]:
    out = []
    for name in fieldnames:
        lower = str(name).lower()
        norm = _norm(name)
        if any(token in lower for token in ("odd", "odds", "close", "closing", "open", "price")):
            out.append(name)
        elif norm.startswith(("b365", "ps", "avg", "max", "c")) and len(norm) <= 8:
            out.append(name)
    return sorted(set(out), key=lambda item: str(item).lower())


def detect_schema(csv_path: str, max_rows: int = 5000, profile_columns: str = "") -> Dict[str, Any]:
    fieldnames, rows, total_rows = read_sample(csv_path, max_rows=max_rows)
    suspects = _suspect_columns(fieldnames)
    requested = [part.strip() for part in profile_columns.split(",") if part.strip()]
    profiles = {column: column_profile(rows, column) for column in sorted(set(suspects + requested)) if column in fieldnames}
    detected = {
        "date": (_find_present(fieldnames, DATE_CANDIDATES) or [None])[0],
        "league": (_find_present(fieldnames, LEAGUE_CANDIDATES) or [None])[0],
        "home_team": (_find_present(fieldnames, HOME_CANDIDATES) or [None])[0],
        "away_team": (_find_present(fieldnames, AWAY_CANDIDATES) or [None])[0],
        "home_goals": (_find_present(fieldnames, HOME_GOALS_CANDIDATES) or [None])[0],
        "away_goals": (_find_present(fieldnames, AWAY_GOALS_CANDIDATES) or [None])[0],
        "result": (_find_present(fieldnames, RESULT_CANDIDATES) or [None])[0],
        "bookmaker": (_find_present(fieldnames, BOOKMAKER_CANDIDATES) or [None])[0],
        "opening_home": _first_plausible(rows, fieldnames, OPENING_HOME),
        "opening_draw": _first_plausible(rows, fieldnames, OPENING_DRAW),
        "opening_away": _first_plausible(rows, fieldnames, OPENING_AWAY),
        "closing_home": _first_plausible(rows, fieldnames, CLOSING_HOME),
        "closing_draw": _first_plausible(rows, fieldnames, CLOSING_DRAW),
        "closing_away": _first_plausible(rows, fieldnames, CLOSING_AWAY),
    }
    invalid_closing = []
    for side, candidates in {"home": CLOSING_HOME, "draw": CLOSING_DRAW, "away": CLOSING_AWAY}.items():
        for column in _find_present(fieldnames, candidates):
            profile = profiles.get(column) or column_profile(rows, column)
            if profile["verdict"] != "decimal_odds_plausible":
                invalid_closing.append({"side": side, "column": column, "verdict": profile["verdict"], "reason": profile["verdict_reason"]})
    has_h2h = all(detected.get(key) for key in ("date", "home_team", "away_team", "opening_home", "opening_away", "closing_home", "closing_away"))
    closing_complete = all(detected.get(key) for key in ("closing_home", "closing_draw", "closing_away"))
    if has_h2h and closing_complete:
        verdict = "h2h_complete"
    elif has_h2h:
        verdict = "h2h_partial"
    elif any(detected.get(key) for key in ("closing_home", "closing_draw", "closing_away")):
        verdict = "closing_partial_needs_mapping"
    else:
        verdict = "no_usable_closing"
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "csv_path": csv_path,
        "rows_total": total_rows,
        "rows_sampled": len(rows),
        "columns": fieldnames,
        "suspect_columns": suspects,
        "detected_columns": detected,
        "column_profiles": profiles,
        "invalid_closing_candidates": invalid_closing,
        "verdict": verdict,
        "warnings": [
            "Les colonnes detectees par nom ne sont pas utilisees si leurs valeurs ne ressemblent pas a des cotes decimales.",
            "Ce detecteur ne calcule pas de CLV.",
        ],
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = ensure_reports_path(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = ensure_reports_path(output)
    profiles = report.get("column_profiles") or {}
    rows = "".join(
        f"<tr><td>{html.escape(str(name))}</td><td>{html.escape(str(profile.get('verdict')))}</td><td>{html.escape(str(profile.get('min')))}</td><td>{html.escape(str(profile.get('max')))}</td><td>{html.escape(str(profile.get('examples')))}</td></tr>"
        for name, profile in profiles.items()
    )
    target.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>Schema odds historique</h1>"
        f"<p>Verdict: {html.escape(str(report.get('verdict')))}</p>"
        "<table border='1'><tr><th>Colonne</th><th>Verdict</th><th>Min</th><th>Max</th><th>Exemples</th></tr>"
        + rows
        + "</table></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Detecteur schema odds historique")
    print(f"- Lignes totales: {report.get('rows_total')}")
    print(f"- Verdict: {report.get('verdict')}")
    for key, value in (report.get("detected_columns") or {}).items():
        print(f"- {key}: {value or 'absent'}")
    print("- Aucune CLV calculee par ce module.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Detecte les colonnes opening/closing odds dans un CSV historique.")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--max-rows", type=int, default=5000)
    parser.add_argument("--profile-columns", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = detect_schema(args.csv, max_rows=args.max_rows, profile_columns=args.profile_columns)
        if args.output:
            write_json(report, args.output)
        if args.html:
            write_html(report, args.html)
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
