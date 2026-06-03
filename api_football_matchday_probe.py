import argparse
import html
import json
from pathlib import Path
from typing import Any, Dict, List

from api_football_fixtures_adapter import fetch_fixtures, normalize_fixtures_payload, read_fixture as read_fixtures_fixture
from api_football_odds_adapter import fetch_api_football_odds, normalize_api_football_payload, read_fixture as read_odds_fixture, response_warnings
from odds_source_config import load_odds_source_config


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le probe matchday doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def build_probe_report(fixtures_payload: Dict[str, Any], odds_payload: Dict[str, Any] | None = None, date: str = "") -> Dict[str, Any]:
    fixtures = normalize_fixtures_payload(fixtures_payload or {"response": []})
    odds_rows = normalize_api_football_payload(odds_payload or {"response": []})
    by_league: Dict[str, int] = {}
    by_country: Dict[str, int] = {}
    for row in fixtures:
        by_league[row.get("league") or "unknown"] = by_league.get(row.get("league") or "unknown", 0) + 1
        by_country[row.get("country") or "unknown"] = by_country.get(row.get("country") or "unknown", 0) + 1
    odds_leagues = {row.get("league") for row in odds_rows if row.get("league")}
    fixture_leagues = set(by_league)
    no_odds = sorted(league for league in fixture_leagues if league not in odds_leagues)
    warnings = response_warnings(odds_payload or {"response": []})
    if fixtures and not odds_rows:
        warnings.append("fixtures trouvees mais aucune cote API-Football normalisable")
    return {
        "generated_for_date": date,
        "total_fixtures": len(fixtures),
        "fixtures_by_country": by_country,
        "fixtures_by_league": by_league,
        "odds_rows": len(odds_rows),
        "odds_available_count": len({row.get("source_event_id") for row in odds_rows if row.get("source_event_id")}),
        "competitions_with_fixtures_but_no_odds": no_odds,
        "likely_manual_required": bool(fixtures and not odds_rows),
        "warnings": warnings,
        "fixtures_sample": fixtures[:20],
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    leagues = "".join(
        f"<li>{html.escape(str(name))}: {count}</li>"
        for name, count in sorted((report.get("fixtures_by_league") or {}).items())
    )
    warnings = "".join(f"<li>{html.escape(str(item))}</li>" for item in report.get("warnings") or [])
    target.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>API-Football matchday probe</h1>"
        f"<p>Date: {html.escape(str(report.get('generated_for_date') or ''))}</p>"
        f"<p>Fixtures: {report.get('total_fixtures')} | Cotes events: {report.get('odds_available_count')}</p>"
        f"<h2>Ligues</h2><ul>{leagues}</ul><h2>Warnings</h2><ul>{warnings}</ul>"
        "<p>Diagnostic source uniquement, aucune mise.</p></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("API-Football matchday probe")
    print(f"- Date: {report.get('generated_for_date') or 'n/a'}")
    print(f"- Fixtures: {report.get('total_fixtures')}")
    print(f"- Events avec odds: {report.get('odds_available_count')}")
    print(f"- Manuel probablement requis: {'oui' if report.get('likely_manual_required') else 'non'}")
    for warning in report.get("warnings") or []:
        print(f"- Warning: {warning}")
    print("- Aucun reseau sans --allow-network.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Probe matchday API-Football fixtures + odds.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--date", required=True)
    parser.add_argument("--from-fixtures", default="")
    parser.add_argument("--from-odds", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.dry_run and not args.from_fixtures:
            print("API-Football matchday probe dry-run")
            print(f"- Date: {args.date}")
            print("- Aucun reseau lance.")
            return 0
        config = load_odds_source_config()
        if args.from_fixtures:
            fixtures_payload = read_fixtures_fixture(args.from_fixtures)
        else:
            if not args.allow_network:
                raise ValueError("Reseau refuse par defaut. Utiliser --dry-run, --from-fixtures ou --allow-network.")
            fixtures_payload = fetch_fixtures(args.date, config)
        if args.from_odds:
            odds_payload = read_odds_fixture(args.from_odds)
        elif args.allow_network and not args.from_fixtures:
            odds_payload = fetch_api_football_odds(config, date=args.date)
        else:
            odds_payload = {"response": []}
        report = build_probe_report(fixtures_payload, odds_payload, date=args.date)
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
