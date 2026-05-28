import argparse
import csv
import html
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from external_xg_lab import detect_columns, first_column, parse_date, parse_float
from understat_probe import compact_soccerdata_season_to_label, parse_seasons


POST_MATCH_ROLES = [
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
]
PREMATCH_ROLES = ["date", "home_team", "away_team", "competition"]


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_report_path(path: str) -> Path:
    target = Path(path)
    parts = [part.lower() for part in target.parts]
    if "data" in parts:
        raise ValueError("Le rapport quality xG ne doit pas etre ecrit dans data/.")
    if "reports" not in parts:
        raise ValueError("Le rapport quality xG doit etre ecrit dans reports/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def expected_season_labels(value: str) -> List[str]:
    return [item["label"] for item in parse_seasons(value)] if value else []


def expected_matches_per_season(league: str) -> Optional[int]:
    normalized = str(league or "").strip().lower()
    if normalized in {"epl", "premier league", "england", "eng-premier league"}:
        return 380
    if normalized in {"la-liga", "la liga", "laliga", "esp-la liga", "spain"}:
        return 380
    if normalized in {"bundesliga", "ger-bundesliga", "germany", "d1"}:
        return 306
    if normalized in {"serie a", "ita-serie a", "italy", "i1"}:
        return 380
    return None


def expected_matches_for_season(league: str, season: str) -> Optional[int]:
    normalized = str(league or "").strip().lower()
    if normalized in {"ligue 1", "fra-ligue 1", "france", "f1"}:
        try:
            start_year = int(str(season)[:4])
        except Exception:
            return None
        return 306 if start_year >= 2023 else 380
    return expected_matches_per_season(league)


def _percentage(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100.0, 2) if denominator else 0.0


def _missing_count(rows: Sequence[Dict[str, Any]], column: str) -> int:
    return sum(1 for row in rows if not str(row.get(column) or "").strip())


def _columns_for_roles(detected: Dict[str, List[str]], roles: Sequence[str]) -> List[str]:
    out: List[str] = []
    for role in roles:
        for column in detected.get(role) or []:
            if column not in out:
                out.append(column)
    return out


def _season_from_row(row: Dict[str, Any], season_col: str, date_col: str) -> str:
    if season_col:
        season = compact_soccerdata_season_to_label(row.get(season_col))
        if season:
            return season
    parsed = parse_date(row.get(date_col)) if date_col else ""
    if parsed:
        year = int(parsed[:4])
        start = year if parsed[5:7] >= "07" else year - 1
        return f"{start}-{start + 1}"
    return ""


def build_quality_report(external_path: str, league: str = "", expected_seasons: str = "") -> Dict[str, Any]:
    target = Path(external_path)
    if not target.exists():
        return {
            "generated_at": now_iso(),
            "external_path": str(target),
            "status": "erreur",
            "error": f"Fichier externe introuvable: {external_path}",
            "verdict": "a_eviter",
            "lab_only": True,
            "can_influence_picks": False,
        }
    with target.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        columns = reader.fieldnames or []
        rows = list(reader)

    detected = detect_columns(columns)
    date_col = first_column(detected, "date")
    home_col = first_column(detected, "home_team")
    away_col = first_column(detected, "away_team")
    season_col = "season" if "season" in columns else first_column(detected, "competition")
    home_xg_col = first_column(detected, "home_xg")
    away_xg_col = first_column(detected, "away_xg")
    home_score_col = first_column(detected, "score_home")
    away_score_col = first_column(detected, "score_away")
    source_col = "source" if "source" in columns else ""

    parsed_dates = [parse_date(row.get(date_col)) for row in rows] if date_col else []
    parsed_dates = [value for value in parsed_dates if value]
    seasons = sorted({_season_from_row(row, season_col if season_col == "season" else "", date_col) for row in rows})
    seasons = [season for season in seasons if season]
    expected = expected_season_labels(expected_seasons)
    expected_per_season = expected_matches_per_season(league)
    expected_by_season = {
        season: expected_matches_for_season(league, season)
        for season in expected
        if expected_matches_for_season(league, season) is not None
    }
    matches_by_season: Dict[str, int] = {}
    for row in rows:
        season = _season_from_row(row, season_col if season_col == "season" else "", date_col) or "inconnue"
        matches_by_season[season] = matches_by_season.get(season, 0) + 1
    completeness_by_season: Dict[str, Optional[float]] = {}
    if expected_by_season:
        for season in sorted(set(seasons) | set(expected)):
            season_expected = expected_by_season.get(season, expected_matches_for_season(league, season))
            completeness_by_season[season] = round(matches_by_season.get(season, 0) / season_expected * 100.0, 2) if season_expected else None
    elif expected_per_season:
        for season in sorted(set(seasons) | set(expected)):
            completeness_by_season[season] = round(matches_by_season.get(season, 0) / expected_per_season * 100.0, 2)
    else:
        for season in seasons:
            completeness_by_season[season] = None

    duplicate_keys = set()
    duplicate_count = 0
    for row in rows:
        key = (
            parse_date(row.get(date_col)) if date_col else "",
            str(row.get(home_col) or "").strip().lower() if home_col else "",
            str(row.get(away_col) or "").strip().lower() if away_col else "",
        )
        if key in duplicate_keys:
            duplicate_count += 1
        else:
            duplicate_keys.add(key)

    teams = {
        str(row.get(home_col) or "").strip()
        for row in rows
        if home_col and str(row.get(home_col) or "").strip()
    } | {
        str(row.get(away_col) or "").strip()
        for row in rows
        if away_col and str(row.get(away_col) or "").strip()
    }
    home_xg_missing = sum(1 for row in rows if home_xg_col and parse_float(row.get(home_xg_col)) is None)
    away_xg_missing = sum(1 for row in rows if away_xg_col and parse_float(row.get(away_xg_col)) is None)
    xg_complete = sum(
        1 for row in rows
        if home_xg_col and away_xg_col and parse_float(row.get(home_xg_col)) is not None and parse_float(row.get(away_xg_col)) is not None
    )
    score_missing = 0
    if home_score_col and away_score_col:
        score_missing = sum(1 for row in rows if parse_float(row.get(home_score_col)) is None or parse_float(row.get(away_score_col)) is None)
    else:
        score_missing = len(rows)

    expected_total = sum(value for value in expected_by_season.values() if value is not None) if expected_by_season and expected else None
    if expected_total is None:
        expected_total = expected_per_season * len(expected) if expected_per_season and expected else None
    actual_total = len(rows)
    completeness_total = round(actual_total / expected_total * 100.0, 2) if expected_total else None
    missing_seasons = sorted(set(expected) - set(seasons))
    extra_seasons = sorted(set(seasons) - set(expected)) if expected else []
    date_home_away_ok = bool(date_col and home_col and away_col and parsed_dates)
    xg_coverage = _percentage(xg_complete, len(rows))
    post_match_columns = _columns_for_roles(detected, POST_MATCH_ROLES)
    prematch_columns = _columns_for_roles(detected, PREMATCH_ROLES)
    leak_risk = "eleve" if post_match_columns else "faible"
    min_completeness = min((value for value in completeness_by_season.values() if value is not None), default=completeness_total or 0.0)

    if (
        xg_coverage >= 95.0
        and not missing_seasons
        and (completeness_total is None or completeness_total >= 95.0)
        and min_completeness >= 95.0
        and date_home_away_ok
        and len(rows) >= 1000
    ):
        verdict = "exploitable_rolling_xg"
    elif xg_coverage < 80.0 or not date_home_away_ok or len(rows) < 300:
        verdict = "a_eviter"
    else:
        verdict = "fragile"

    warnings: List[str] = []
    if missing_seasons:
        warnings.append("Saisons attendues manquantes: " + ", ".join(missing_seasons))
    if duplicate_count:
        warnings.append(f"Doublons date/home/away detectes: {duplicate_count}")
    if expected_total is not None and actual_total != expected_total:
        warnings.append(f"Volume inattendu: {actual_total} lignes vs {expected_total} attendues.")

    return {
        "generated_at": now_iso(),
        "external_path": str(target),
        "status": "ok",
        "rows": len(rows),
        "date_min": min(parsed_dates) if parsed_dates else "",
        "date_max": max(parsed_dates) if parsed_dates else "",
        "seasons_detected": seasons,
        "seasons_expected": expected,
        "missing_seasons": missing_seasons,
        "extra_seasons": extra_seasons,
        "matches_by_season": dict(sorted(matches_by_season.items())),
        "expected_matches_per_season": expected_per_season,
        "expected_matches_by_season": expected_by_season,
        "completeness_by_season": completeness_by_season,
        "total_expected_matches": expected_total,
        "total_actual_matches": actual_total,
        "total_completeness": completeness_total,
        "duplicate_count": duplicate_count,
        "teams_detected": len(teams),
        "xg_coverage": xg_coverage,
        "home_xg_missing": home_xg_missing if home_xg_col else len(rows),
        "away_xg_missing": away_xg_missing if away_xg_col else len(rows),
        "scores_missing": score_missing,
        "source": sorted({str(row.get(source_col) or "").strip() for row in rows if source_col and str(row.get(source_col) or "").strip()}),
        "columns": columns,
        "post_match_columns": post_match_columns,
        "safe_prematch_columns": prematch_columns,
        "leak_risk": leak_risk,
        "has_date_home_away": date_home_away_ok,
        "verdict": verdict,
        "warnings": warnings,
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_json(report: Dict[str, Any], path: str) -> Path:
    target = ensure_report_path(path)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], path: str) -> Path:
    target = ensure_report_path(path)
    rows = []
    for season, count in (report.get("matches_by_season") or {}).items():
        completeness = (report.get("completeness_by_season") or {}).get(season)
        rows.append(f"<tr><td>{html.escape(str(season))}</td><td>{count}</td><td>{html.escape(str(completeness))}</td></tr>")
    target.write_text("\n".join([
        "<!doctype html>",
        "<html lang='fr'><head><meta charset='utf-8'>",
        "<title>Quality gate xG Understat</title>",
        "<style>body{font-family:Arial,sans-serif;margin:32px;color:#1f2933}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px;text-align:left}th{background:#f3f4f6}.warn{background:#fff7ed;border:1px solid #fed7aa;padding:12px;border-radius:6px}</style>",
        "</head><body>",
        "<h1>Understat xG Dataset Quality Gate</h1>",
        f"<p>Verdict: {html.escape(str(report.get('verdict')))}. Lab only: {report.get('lab_only')}. Picks: {report.get('can_influence_picks')}.</p>",
        "<ul>",
        f"<li>Lignes: {report.get('rows')}</li>",
        f"<li>Periode: {report.get('date_min')} -> {report.get('date_max')}</li>",
        f"<li>xG coverage: {report.get('xg_coverage')}%</li>",
        f"<li>Doublons: {report.get('duplicate_count')}</li>",
        f"<li>Equipes: {report.get('teams_detected')}</li>",
        "</ul>",
        "<h2>Saisons</h2>",
        "<table><thead><tr><th>Saison</th><th>Matchs</th><th>Completeness</th></tr></thead><tbody>",
        *rows,
        "</tbody></table>",
        "<section class='warn'><h2>Warnings</h2><ul>",
        *[f"<li>{html.escape(str(item))}</li>" for item in report.get("warnings") or []],
        "</ul></section>",
        "<p>Rapport descriptif seulement: aucun pick automatique, aucune DB, aucun fichier data/.</p>",
        "</body></html>",
    ]), encoding="utf-8")
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Quality gate dataset xG")
    print(f"- Fichier analyse: {report.get('external_path')}")
    if report.get("error"):
        print(f"- Erreur: {report.get('error')}")
    print(f"- Lignes: {report.get('rows', 0)}")
    print(f"- Dates: {report.get('date_min') or 'non detectee'} -> {report.get('date_max') or 'non detectee'}")
    print(f"- Saisons detectees: {', '.join(report.get('seasons_detected') or []) or 'non detectees'}")
    print(f"- Saisons attendues: {', '.join(report.get('seasons_expected') or []) or 'non renseignees'}")
    print(f"- Saisons manquantes: {', '.join(report.get('missing_seasons') or []) or 'aucune'}")
    print(f"- Matchs attendus/reels: {report.get('total_expected_matches')} / {report.get('total_actual_matches')}")
    print(f"- xG coverage: {report.get('xg_coverage')}%")
    print(f"- Doublons date/home/away: {report.get('duplicate_count')}")
    print(f"- Leak risk: {report.get('leak_risk')}")
    print(f"- Verdict: {report.get('verdict')}")
    for warning in report.get("warnings") or []:
        print(f"- Avertissement: {warning}")
    print("- Statut: laboratoire seulement, aucun pick automatique.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Quality gate local pour dataset xG externe.")
    parser.add_argument("--external", required=True, help="CSV externe xG a auditer")
    parser.add_argument("--league", default="", help="Ligue attendue, ex: EPL")
    parser.add_argument("--expected-seasons", default="", help="Saisons attendues separees par virgules")
    parser.add_argument("--output", default="", help="Rapport JSON dans reports/")
    parser.add_argument("--html", default="", help="Rapport HTML dans reports/")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    report = build_quality_report(args.external, league=args.league, expected_seasons=args.expected_seasons)
    if args.output:
        path = write_json(report, args.output)
        print(f"- Rapport JSON quality ecrit: {path}")
    if args.html:
        path = write_html(report, args.html)
        print(f"- Rapport HTML quality ecrit: {path}")
    print_report(report)
    return 0 if report.get("status") != "erreur" else 1


if __name__ == "__main__":
    raise SystemExit(main())
