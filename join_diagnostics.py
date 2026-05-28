import argparse
import csv
import html
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from external_xg_lab import detect_columns, first_column, parse_date
from team_name_normalizer import normalize_team_name, suggest_team_aliases, team_name_similarity


SUGGESTION_THRESHOLD = 0.75


def ensure_report_path(path: str) -> Path:
    target = Path(path)
    parts = [part.lower() for part in target.parts]
    if "data" in parts:
        raise ValueError("Le rapport de jointure ne doit pas etre ecrit dans data/.")
    if "reports" not in parts:
        raise ValueError("Le rapport de jointure doit etre ecrit dans reports/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def classify_join_quality(join_rate: Optional[float]) -> Dict[str, Any]:
    rate = float(join_rate or 0.0)
    if rate >= 90.0:
        quality = "excellent"
        allowed = True
        reason = "taux de jointure excellent"
    elif rate >= 75.0:
        quality = "exploitable_prudent"
        allowed = True
        reason = "taux de jointure exploitable avec controle"
    elif rate >= 50.0:
        quality = "fragile"
        allowed = True
        reason = "taux de jointure fragile: interpretation prudente"
    else:
        quality = "insuffisant"
        allowed = False
        reason = "taux de jointure insuffisant"
    return {
        "join_rate": round(rate, 2),
        "join_quality": quality,
        "modeling_allowed_by_join_quality": allowed,
        "reason": reason,
        "join_blocks_promotion": not allowed,
    }


def _season_from_date(date_key: str) -> str:
    if not date_key:
        return "inconnue"
    year = int(date_key[:4])
    start = year if date_key[5:7] >= "07" else year - 1
    return f"{start}-{start + 1}"


def _read_matches(path: str, league: str = "", use_aliases: bool = True) -> Dict[str, Any]:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"Fichier introuvable: {path}")
    with target.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        columns = reader.fieldnames or []
        rows = list(reader)
    detected = detect_columns(columns)
    date_col = first_column(detected, "date")
    home_col = first_column(detected, "home_team")
    away_col = first_column(detected, "away_team")
    league_col = first_column(detected, "competition")
    season_col = "season" if "season" in columns else ""
    if not date_col or not home_col or not away_col:
        raise ValueError(f"Colonnes date/home/away insuffisantes dans {path}.")
    matches: List[Dict[str, Any]] = []
    skipped = 0
    for index, row in enumerate(rows, start=1):
        date_key = parse_date(row.get(date_col))
        home = str(row.get(home_col) or "").strip()
        away = str(row.get(away_col) or "").strip()
        row_league = str(row.get(league_col) or league or "").strip()
        if not date_key or not home or not away:
            skipped += 1
            continue
        season = str(row.get(season_col) or "").strip() or _season_from_date(date_key)
        home_norm = normalize_team_name(home, league=row_league or league, use_aliases=use_aliases)
        away_norm = normalize_team_name(away, league=row_league or league, use_aliases=use_aliases)
        home_basic = normalize_team_name(home, league=row_league or league, use_aliases=False)
        away_basic = normalize_team_name(away, league=row_league or league, use_aliases=False)
        matches.append({
            "index": index,
            "date": date_key,
            "season": season,
            "league": row_league,
            "home": home,
            "away": away,
            "home_norm": home_norm,
            "away_norm": away_norm,
            "home_basic": home_basic,
            "away_basic": away_basic,
            "home_alias_applied": home_basic != home_norm,
            "away_alias_applied": away_basic != away_norm,
            "key": (date_key, home_norm, away_norm),
            "basic_key": (date_key, home_basic, away_basic),
        })
    return {
        "path": str(target),
        "rows": len(rows),
        "columns": columns,
        "detected": detected,
        "matches": matches,
        "skipped": skipped,
    }


def _index_by_key(matches: Iterable[Dict[str, Any]], key_name: str = "key") -> Dict[Tuple[str, str, str], List[Dict[str, Any]]]:
    indexed: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    for match in matches:
        indexed[match[key_name]].append(match)
    return indexed


def _team_names(matches: Iterable[Dict[str, Any]]) -> List[str]:
    names: List[str] = []
    for match in matches:
        names.append(match["home"])
        names.append(match["away"])
    return names


def _best_same_date_match(external: Dict[str, Any], candidates: Sequence[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], float, bool]:
    best: Optional[Dict[str, Any]] = None
    best_score = 0.0
    ambiguous = False
    for candidate in candidates:
        home_score = team_name_similarity(external["home"], candidate["home"])
        away_score = team_name_similarity(external["away"], candidate["away"])
        score = round((home_score + away_score) / 2.0, 4)
        if score > best_score:
            best = candidate
            best_score = score
            ambiguous = False
        elif score == best_score and score >= SUGGESTION_THRESHOLD:
            ambiguous = True
    if best_score >= SUGGESTION_THRESHOLD:
        return best, best_score, ambiguous
    return None, best_score, ambiguous


def _cause_for_unmatched(match: Dict[str, Any], x_by_date: Dict[str, List[Dict[str, Any]]], x_names_norm: set) -> List[str]:
    causes: List[str] = []
    same_date = x_by_date.get(match["date"], [])
    if same_date:
        causes.append("nom equipe different")
        if match["home_basic"] != match["home_norm"] or match["away_basic"] != match["away_norm"]:
            causes.append("alias ou accent")
        if match["home_norm"] not in x_names_norm or match["away_norm"] not in x_names_norm:
            causes.append("equipe promue/releguee ou competition differente")
    else:
        causes.append("date decalee")
        causes.append("calendrier manquant")
    return causes


def _examples(matches: Sequence[Dict[str, Any]], limit: int = 20) -> List[Dict[str, Any]]:
    return [
        {
            "date": item["date"],
            "season": item.get("season"),
            "home": item["home"],
            "away": item["away"],
            "home_norm": item["home_norm"],
            "away_norm": item["away_norm"],
        }
        for item in matches[:limit]
    ]


def _alias_usage(matches: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counter: Counter = Counter()
    for match in matches:
        if match["home_alias_applied"]:
            counter[(match["home"], match["home_norm"])] += 1
        if match["away_alias_applied"]:
            counter[(match["away"], match["away_norm"])] += 1
    return [
        {"raw": raw, "normalized": normalized, "count": count}
        for (raw, normalized), count in counter.most_common(30)
    ]


def build_join_diagnostics(xgabora_path: str, external_path: str, league: str = "") -> Dict[str, Any]:
    x_basic = _read_matches(xgabora_path, league=league, use_aliases=False)
    e_basic = _read_matches(external_path, league=league, use_aliases=False)
    x_alias = _read_matches(xgabora_path, league=league, use_aliases=True)
    e_alias = _read_matches(external_path, league=league, use_aliases=True)

    x_basic_keys = _index_by_key(x_basic["matches"], "basic_key")
    x_alias_keys = _index_by_key(x_alias["matches"], "key")
    x_by_date: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for match in x_alias["matches"]:
        x_by_date[match["date"]].append(match)

    exact_before = [match for match in e_basic["matches"] if match["basic_key"] in x_basic_keys]
    exact_after = [match for match in e_alias["matches"] if match["key"] in x_alias_keys]
    exact_after_keys = {match["key"] for match in exact_after}
    fuzzy: List[Dict[str, Any]] = []
    ambiguous_fuzzy: List[Dict[str, Any]] = []
    unmatched: List[Dict[str, Any]] = []
    for match in e_alias["matches"]:
        if match["key"] in exact_after_keys:
            continue
        candidate, score, ambiguous = _best_same_date_match(match, x_by_date.get(match["date"], []))
        if candidate and not ambiguous:
            fuzzy.append({
                "external": _examples([match], 1)[0],
                "xgabora": _examples([candidate], 1)[0],
                "similarity": score,
            })
        elif candidate and ambiguous:
            ambiguous_fuzzy.append({
                "external": _examples([match], 1)[0],
                "similarity": score,
                "reason": "plusieurs candidats proches, non joint automatiquement",
            })
            unmatched.append(match)
        else:
            unmatched.append(match)

    external_count = len(e_alias["matches"])
    exact_rate_before = round(len(exact_before) / external_count * 100.0, 2) if external_count else 0.0
    exact_rate_after = round(len(exact_after) / external_count * 100.0, 2) if external_count else 0.0
    fuzzy_rate = round((len(exact_after) + len(fuzzy)) / external_count * 100.0, 2) if external_count else 0.0
    x_names = _team_names(x_alias["matches"])
    e_unmatched_names = _team_names(unmatched)
    x_names_norm = {normalize_team_name(name, league=league) for name in x_names}
    suggestions = suggest_team_aliases(e_unmatched_names, x_names, threshold=SUGGESTION_THRESHOLD, league=league)[:40]
    causes = Counter()
    for match in unmatched:
        causes.update(_cause_for_unmatched(match, x_by_date, x_names_norm))

    by_season = Counter(match.get("season") or "inconnue" for match in e_alias["matches"])
    unmatched_by_season = Counter(match.get("season") or "inconnue" for match in unmatched)
    by_team = Counter()
    unmatched_by_team = Counter()
    for match in e_alias["matches"]:
        by_team[match["home"]] += 1
        by_team[match["away"]] += 1
    for match in unmatched:
        unmatched_by_team[match["home"]] += 1
        unmatched_by_team[match["away"]] += 1

    quality = classify_join_quality(exact_rate_after)
    return {
        "xgabora_path": xgabora_path,
        "external_path": external_path,
        "league": league,
        "external_matches": external_count,
        "xgabora_match_level_unique": len({match["key"] for match in x_alias["matches"]}),
        "join_rate_before_alias": exact_rate_before,
        "join_rate_after_alias": exact_rate_after,
        "join_rate_exact_date_home_away": exact_rate_after,
        "join_rate_fuzzy": fuzzy_rate,
        "exact_matches_before_alias": len(exact_before),
        "exact_matches_after_alias": len(exact_after),
        "alias_matches_gained": max(0, len(exact_after) - len(exact_before)),
        "fuzzy_matches_possible": len(fuzzy),
        "ambiguous_fuzzy_matches": len(ambiguous_fuzzy),
        "unmatched_count": len(unmatched),
        "unmatched_external_examples": _examples(unmatched, 30),
        "unrecognized_external_teams": [
            {"team": team, "count": count}
            for team, count in unmatched_by_team.most_common(30)
        ],
        "close_xgabora_suggestions": suggestions,
        "top_alias_suggestions": suggestions[:20],
        "alias_used": _alias_usage(e_alias["matches"]),
        "distribution_by_season": dict(sorted(by_season.items())),
        "unmatched_by_season": dict(sorted(unmatched_by_season.items())),
        "distribution_by_team": [
            {"team": team, "count": count}
            for team, count in by_team.most_common(30)
        ],
        "unmatched_by_team": [
            {"team": team, "count": count}
            for team, count in unmatched_by_team.most_common(30)
        ],
        "probable_causes": [
            {"cause": cause, "count": count}
            for cause, count in causes.most_common()
        ],
        "fuzzy_examples": fuzzy[:20],
        "ambiguous_examples": ambiguous_fuzzy[:20],
        "join_quality": quality["join_quality"],
        "modeling_allowed_by_join_quality": quality["modeling_allowed_by_join_quality"],
        "join_quality_reason": quality["reason"],
        "join_blocks_promotion": quality["join_blocks_promotion"],
        "alias_applied": bool(len(exact_after) != len(exact_before) or _alias_usage(e_alias["matches"])),
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_json(report: Dict[str, Any], path: str) -> Path:
    target = ensure_report_path(path)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], path: str) -> Path:
    target = ensure_report_path(path)
    suggestions = "".join(
        f"<li>{html.escape(str(item.get('external_name')))} -> {html.escape(str(item.get('suggested_xgabora_name')))} ({item.get('similarity')})</li>"
        for item in report.get("top_alias_suggestions", [])[:20]
    ) or "<li>Aucune suggestion au-dessus du seuil.</li>"
    unmatched = "".join(
        f"<li>{html.escape(item['date'])}: {html.escape(item['home'])} - {html.escape(item['away'])}</li>"
        for item in report.get("unmatched_external_examples", [])[:20]
    ) or "<li>Aucun exemple.</li>"
    target.write_text("\n".join([
        "<!doctype html>",
        "<html lang='fr'><head><meta charset='utf-8'>",
        "<title>Diagnostic jointure xG</title>",
        "<style>body{font-family:Arial,sans-serif;margin:32px;color:#1f2933}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:8px;text-align:left}th{background:#f3f4f6}.warn{background:#fff7ed;border:1px solid #fed7aa;padding:12px;border-radius:6px}</style>",
        "</head><body>",
        "<h1>Diagnostic de jointure Understat xG</h1>",
        "<table><tbody>",
        f"<tr><th>Matchs externes</th><td>{report.get('external_matches')}</td></tr>",
        f"<tr><th>Matchs xgabora uniques</th><td>{report.get('xgabora_match_level_unique')}</td></tr>",
        f"<tr><th>Join rate avant alias</th><td>{report.get('join_rate_before_alias')}%</td></tr>",
        f"<tr><th>Join rate apres alias</th><td>{report.get('join_rate_after_alias')}%</td></tr>",
        f"<tr><th>Join rate fuzzy potentiel</th><td>{report.get('join_rate_fuzzy')}%</td></tr>",
        f"<tr><th>Qualite jointure</th><td>{html.escape(str(report.get('join_quality')))}</td></tr>",
        f"<tr><th>Modeling allowed</th><td>{report.get('modeling_allowed_by_join_quality')}</td></tr>",
        "</tbody></table>",
        "<section class='warn'><h2>Causes probables</h2><pre>",
        html.escape(json.dumps(report.get("probable_causes", []), ensure_ascii=False, indent=2)),
        "</pre></section>",
        "<h2>Suggestions alias a valider</h2><ul>",
        suggestions,
        "</ul>",
        "<h2>Exemples non joints</h2><ul>",
        unmatched,
        "</ul>",
        "<p>Rapport local descriptif: aucun alias applique automatiquement aux CSV source, aucun pick automatique.</p>",
        "</body></html>",
    ]), encoding="utf-8")
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Diagnostic de jointure multi-ligues")
    print(f"- Xgabora/features: {report.get('xgabora_path')}")
    print(f"- Externe: {report.get('external_path')}")
    print(f"- Matchs externes: {report.get('external_matches')}")
    print(f"- Matchs xgabora uniques: {report.get('xgabora_match_level_unique')}")
    print(f"- Join rate avant alias: {report.get('join_rate_before_alias')}%")
    print(f"- Join rate apres alias: {report.get('join_rate_after_alias')}%")
    print(f"- Join rate fuzzy potentiel: {report.get('join_rate_fuzzy')}%")
    print(f"- Matchs gagnes par alias: {report.get('alias_matches_gained')}")
    print(f"- Matchs externes non joints: {report.get('unmatched_count')}")
    print(f"- Join quality: {report.get('join_quality')}")
    print(f"- Modeling allowed par jointure: {report.get('modeling_allowed_by_join_quality')}")
    for cause in report.get("probable_causes", [])[:8]:
        print(f"- Cause probable: {cause['cause']} ({cause['count']})")
    print("- Suggestions alias a valider:")
    for suggestion in report.get("top_alias_suggestions", [])[:8]:
        print(f"  - {suggestion['external_name']} -> {suggestion['suggested_xgabora_name']} ({suggestion['similarity']})")
    print("- Rappel: aucun alias n'est applique automatiquement aux fichiers source.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Diagnostic local de jointure Understat/xgabora, sans modification CSV.")
    parser.add_argument("--xgabora", required=True, help="CSV features/xgabora local")
    parser.add_argument("--external", required=True, help="CSV externe Understat ou xG")
    parser.add_argument("--league", default="", help="Ligue optionnelle pour les alias")
    parser.add_argument("--output", default="", help="Rapport JSON dans reports/")
    parser.add_argument("--html", default="", help="Rapport HTML dans reports/")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = build_join_diagnostics(args.xgabora, args.external, league=args.league)
        if args.output:
            path = write_json(report, args.output)
            print(f"- Rapport JSON jointure ecrit: {path}")
        if args.html:
            path = write_html(report, args.html)
            print(f"- Rapport HTML jointure ecrit: {path}")
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
