import argparse
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from api_football_fixtures_adapter import fetch_fixtures, normalize_fixtures_payload, read_fixture as read_fixtures_fixture, write_csv as write_fixtures_csv, write_raw as write_fixtures_raw
from api_football_odds_adapter import fetch_api_football_odds, load_fixture_index, process_payload, read_fixture as read_odds_fixture, write_raw as write_odds_raw, write_rows, write_summary_html, write_summary_json
from api_football_valid_odds_selector import select_valid_odds, write_selection, write_summary as write_selection_summary
from odds_source_config import load_odds_source_config
from odds_to_shadow import snapshots_to_shadow


def _safe_dir(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le runner same-day doit ecrire hors data/.")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _read_json_if(path: str) -> Dict[str, Any]:
    if path and Path(path).exists():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return {"response": []}


def default_output_dir(date: str) -> str:
    safe = (date or datetime.now().strftime("%Y-%m-%d")).replace("-", "_")
    return f"reports/api_football_same_day_{safe}"


def run_same_day(
    date: str,
    output_dir: str = "",
    ledger: str = "reports/shadow_ledger.csv",
    fixtures_json: str = "",
    odds_json: str = "",
    allow_network: bool = False,
    apply: bool = False,
    bookmaker: str = "",
    market: str = "h2h",
    max_events: int = 3,
    prefer_side: str = "",
    include_draw: bool = False,
) -> Dict[str, Any]:
    if not date:
        raise ValueError("--date requis")
    out_dir = _safe_dir(output_dir or default_output_dir(date))
    config = load_odds_source_config()
    if fixtures_json:
        fixtures_payload = read_fixtures_fixture(fixtures_json)
    elif allow_network:
        fixtures_payload = fetch_fixtures(date, config)
    else:
        fixtures_payload = {"response": []}
    if odds_json:
        odds_payload = read_odds_fixture(odds_json)
    elif allow_network:
        odds_payload = fetch_api_football_odds(config, date=date, bookmaker=bookmaker, market=market)
    else:
        odds_payload = {"response": []}

    fixtures_raw_path = out_dir / "fixtures.json"
    fixtures_csv_path = out_dir / "fixtures.csv"
    odds_raw_path = out_dir / "odds_raw.json"
    odds_enriched_path = out_dir / "odds_enriched.csv"
    odds_invalid_path = out_dir / "odds_invalid.csv"
    odds_summary_path = out_dir / "odds_summary.json"
    odds_summary_html = out_dir / "odds_summary.html"
    selection_path = out_dir / "selection.csv"
    selection_summary_path = out_dir / "selection_summary.json"
    dry_run_shadow_path = out_dir / "dry_run_shadow.json"
    summary_path = out_dir / "summary.json"
    summary_html_path = out_dir / "summary.html"

    write_fixtures_raw(fixtures_payload, str(fixtures_raw_path))
    fixtures_rows = normalize_fixtures_payload(fixtures_payload)
    write_fixtures_csv(fixtures_rows, str(fixtures_csv_path))
    write_odds_raw(odds_payload, str(odds_raw_path))

    fixtures_index = load_fixture_index(fixtures_csv=str(fixtures_csv_path))
    odds_rows, invalid_rows, odds_summary = process_payload(
        odds_payload,
        fixtures_index=fixtures_index,
        market=market,
        bookmaker=bookmaker,
        valid_only=False,
    )
    write_rows(odds_rows, str(odds_enriched_path))
    write_rows(invalid_rows, str(odds_invalid_path))
    write_summary_json(odds_summary, str(odds_summary_path))
    write_summary_html(odds_summary, str(odds_summary_html))

    selection = select_valid_odds(
        str(odds_enriched_path),
        market=market,
        bookmaker=bookmaker,
        max_events=max_events,
        one_side_per_event=True,
        prefer_side=prefer_side,
        include_draw=include_draw,
        date_min=date,
    )
    write_selection(selection["selection"], str(selection_path))
    write_selection_summary(selection, str(selection_summary_path))
    shadow_report = snapshots_to_shadow(
        "",
        ledger,
        selection_csv=str(selection_path),
        strategy_name="api_football_same_day_shadow_v1",
        reason="observation_api_football_same_day",
        dry_run=not apply,
    )
    dry_run_shadow_path.write_text(json.dumps(shadow_report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "date": date,
        "output_dir": str(out_dir),
        "allow_network": allow_network,
        "applied": apply,
        "fixtures": len(fixtures_rows),
        "odds_raw_lines": odds_summary.get("raw_odds_lines"),
        "odds_valid": odds_summary.get("valid_rows"),
        "odds_invalid": odds_summary.get("pre_filter_invalid_rows"),
        "selection_rows": selection.get("selected_rows"),
        "would_add_or_added": shadow_report.get("rows_added"),
        "shadow_dry_run": shadow_report.get("dry_run"),
        "paths": {
            "fixtures_csv": str(fixtures_csv_path),
            "fixtures_json": str(fixtures_raw_path),
            "odds_enriched": str(odds_enriched_path),
            "odds_invalid": str(odds_invalid_path),
            "selection": str(selection_path),
            "dry_run_shadow": str(dry_run_shadow_path),
        },
        "message": "Same-day API-Football: observation shadow seulement, aucune mise.",
        "lab_only": True,
        "can_influence_picks": False,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_html_path.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>API-Football Same-Day Runner</h1><pre>"
        + html.escape(json.dumps(summary, ensure_ascii=False, indent=2))
        + "</pre><p>Laboratoire local, aucune mise.</p></body></html>",
        encoding="utf-8",
    )
    return summary


def print_report(report: Dict[str, Any]) -> None:
    print("API-Football same-day runner")
    print(f"- Date: {report.get('date')}")
    print(f"- Fixtures: {report.get('fixtures')}")
    print(f"- Odds valides: {report.get('odds_valid')}")
    print(f"- Selection: {report.get('selection_rows')}")
    print(f"- Would add / added: {report.get('would_add_or_added')}")
    print(f"- Applied: {report.get('applied')}")
    print("- Observation shadow seulement, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Workflow same-day API-Football en laboratoire local.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--bookmaker", default="")
    parser.add_argument("--market", default="h2h")
    parser.add_argument("--max-events", type=int, default=3)
    parser.add_argument("--prefer-side", default="")
    parser.add_argument("--include-draw", action="store_true")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--fixtures-json", default="")
    parser.add_argument("--odds-json", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        effective_allow_network = bool(args.allow_network and not args.dry_run)
        effective_apply = bool(args.apply and not args.dry_run)
        report = run_same_day(
            args.date,
            output_dir=args.output_dir,
            ledger=args.ledger,
            fixtures_json=args.fixtures_json,
            odds_json=args.odds_json,
            allow_network=effective_allow_network,
            apply=effective_apply,
            bookmaker=args.bookmaker,
            market=args.market,
            max_events=args.max_events,
            prefer_side=args.prefer_side,
            include_draw=args.include_draw,
        )
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
