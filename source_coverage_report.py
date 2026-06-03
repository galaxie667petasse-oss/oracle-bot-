import argparse
import html
import json
from pathlib import Path
from typing import Any, Dict, List

from api_football_fixtures_adapter import normalize_fixtures_payload


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le rapport source coverage doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _read_json(path: str) -> Dict[str, Any]:
    if not path or not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if isinstance(data, list):
        return {"sports": data}
    return data if isinstance(data, dict) else {}


def _manual_pack_summary(path: str) -> Dict[str, Any]:
    target = Path(path)
    if not path or not target.exists():
        return {"available": False}
    files = sorted(item.name for item in target.iterdir() if item.is_file())
    return {"available": True, "path": path, "files": files}


def _fixture_leagues(data: Dict[str, Any]) -> Dict[str, int]:
    if data.get("fixtures_by_league"):
        return data.get("fixtures_by_league") or {}
    if data.get("response"):
        rows = normalize_fixtures_payload(data)
        out: Dict[str, int] = {}
        for row in rows:
            league = row.get("league") or "unknown"
            out[league] = out.get(league, 0) + 1
        return out
    return {}


def build_source_coverage_report(
    active_sports_path: str = "",
    the_odds_scan_path: str = "",
    fixtures_path: str = "",
    api_odds_path: str = "",
    manual_pack: str = "",
) -> Dict[str, Any]:
    active = _read_json(active_sports_path)
    scan = _read_json(the_odds_scan_path)
    fixtures = _read_json(fixtures_path)
    api_odds = _read_json(api_odds_path)
    manual = _manual_pack_summary(manual_pack)
    active_keys = set(active.get("sport_keys") or [row.get("key") for row in active.get("sports", []) if row.get("key")])
    scanned_items = scan.get("sports") or []
    scanned_keys = {item.get("sport_key") for item in scanned_items if item.get("sport_key")}
    active_not_scanned = sorted(active_keys - scanned_keys)
    near_term = [
        {
            "sport_key": item.get("sport_key"),
            "events": item.get("distinct_events") or item.get("events") or 0,
            "earliest_match_date": item.get("earliest_match_date"),
            "priority": item.get("recommended_priority") or item.get("priority"),
            "usable_for_shadow": item.get("usable_for_shadow"),
        }
        for item in scanned_items
        if item.get("earliest_match_date")
    ]
    fixture_leagues = _fixture_leagues(fixtures)
    missing: List[str] = []
    if active_keys and active_not_scanned:
        missing.append("sports actifs The Odds API non scannes")
    if fixture_leagues and not api_odds.get("odds_available_count"):
        missing.append("fixtures API-Football sans odds associees")
    if not manual.get("available"):
        missing.append("aucun pack manuel fourni")
    recommendations = []
    if near_term:
        recommendations.append("API automatique: prioriser les sport_keys proches avec events")
    if fixture_leagues and not api_odds.get("odds_available_count"):
        recommendations.append("manuel Betclic: saisir les matchs visibles mais absents des odds API")
    if not near_term and not fixture_leagues:
        recommendations.append("ignorer ou attendre une fenetre plus proche")
    if any(item.get("usable_for_shadow") for item in near_term):
        recommendations.append("attendre near-close avant toute mesure CLV")
    return {
        "active_sports_available": bool(active),
        "the_odds_scan_available": bool(scan),
        "api_football_fixtures_available": bool(fixtures),
        "api_football_odds_available": bool(api_odds),
        "manual_pack": manual,
        "competitions_active": sorted(active_keys),
        "competitions_scanned": sorted(scanned_keys),
        "competitions_active_not_scanned": active_not_scanned,
        "near_term_sources": near_term,
        "fixtures_by_league": fixture_leagues,
        "api_football_odds_count": api_odds.get("odds_available_count") or api_odds.get("odds_rows") or 0,
        "identified_gaps": missing,
        "source_recommendations": recommendations,
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    gaps = "".join(f"<li>{html.escape(str(item))}</li>" for item in report.get("identified_gaps") or [])
    recs = "".join(f"<li>{html.escape(str(item))}</li>" for item in report.get("source_recommendations") or [])
    rows = "".join(
        f"<tr><td>{html.escape(str(item.get('sport_key')))}</td><td>{item.get('events')}</td><td>{html.escape(str(item.get('earliest_match_date')))}</td><td>{html.escape(str(item.get('priority')))}</td></tr>"
        for item in report.get("near_term_sources") or []
    )
    target.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>Source Coverage Oracle</h1>"
        "<h2>Sources proches</h2><table border='1'><tr><th>Sport</th><th>Events</th><th>Premiere date</th><th>Priorite</th></tr>"
        + rows
        + f"</table><h2>Manques</h2><ul>{gaps}</ul><h2>Recommandations</h2><ul>{recs}</ul>"
        "<p>Coverage source uniquement, aucune mise.</p></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Source Coverage Oracle")
    print(f"- Sports actifs: {len(report.get('competitions_active') or [])}")
    print(f"- Sports scannes: {len(report.get('competitions_scanned') or [])}")
    print(f"- Sources proches: {len(report.get('near_term_sources') or [])}")
    for gap in report.get("identified_gaps") or []:
        print(f"- Manque: {gap}")
    for rec in report.get("source_recommendations") or []:
        print(f"- Recommandation: {rec}")
    print("- Diagnostic local, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Compare la couverture des sources odds/matchday.")
    parser.add_argument("--active-sports", default="")
    parser.add_argument("--the-odds-scan", default="")
    parser.add_argument("--fixtures", default="")
    parser.add_argument("--api-odds", default="")
    parser.add_argument("--manual-pack", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = build_source_coverage_report(
            active_sports_path=args.active_sports,
            the_odds_scan_path=args.the_odds_scan,
            fixtures_path=args.fixtures,
            api_odds_path=args.api_odds,
            manual_pack=args.manual_pack,
        )
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
