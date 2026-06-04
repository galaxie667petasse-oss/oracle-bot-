import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from near_close_scheduler import load_sport_map
from shadow_ledger import read_ledger


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le helper near-close today doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _extract_source_event_id(row: Dict[str, Any]) -> str:
    notes = str(row.get("notes") or "")
    for part in notes.split(";"):
        if "source_event_id=" in part:
            return part.split("source_event_id=", 1)[1].strip()
    return str(row.get("source_event_id") or "").strip()


def build_today_helper(ledger: str, sport_map: str = "", date: str = "", api_football: bool = False) -> Dict[str, Any]:
    date = date or _today()
    rows = [
        row for row in read_ledger(ledger)
        if str(row.get("match_date") or "") == date and not str(row.get("closing_odds") or "").strip()
    ]
    mapping = load_sport_map(sport_map)
    leagues = sorted({row.get("league") or "unknown" for row in rows})
    commands: List[str] = []
    for league in leagues:
        sport_key = mapping.get(league, "")
        if sport_key:
            commands.append(f"python near_close_batch_runner.py --ledger {ledger} --sport-map {sport_map or 'config/sport_key_map.example.json'} --dry-run")
    api_events = sorted({event for event in (_extract_source_event_id(row) for row in rows) if event})
    if api_football or api_events:
        for event_id in api_events[:10]:
            commands.append(f"python api_football_odds_adapter.py --fixture-id {event_id} --allow-network --valid-only --output reports/api_football_near_close_{event_id}.csv --summary-json reports/api_football_near_close_{event_id}_summary.json")
    commands.append("python manual_betclic_intake_helper.py --template reports/betclic_manual_intake.csv")
    return {
        "ledger": ledger,
        "date": date,
        "pending_today": len(rows),
        "leagues": leagues,
        "sport_keys": {league: mapping.get(league, "") for league in leagues},
        "api_football_fixture_ids": api_events,
        "commands": commands,
        "manual_fallback": True,
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Near-close today helper")
    print(f"- Date: {report.get('date')}")
    print(f"- Observations du jour pending closing: {report.get('pending_today')}")
    print(f"- Ligues: {', '.join(report.get('leagues') or []) or 'aucune'}")
    for command in report.get("commands") or []:
        print(f"- Commande suggeree: {command}")
    print("- Aucune commande reseau n'est lancee par ce helper.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Genere les commandes near-close pour les observations du jour.")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--sport-map", default="")
    parser.add_argument("--date", default="")
    parser.add_argument("--api-football", action="store_true")
    parser.add_argument("--output", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = build_today_helper(args.ledger, sport_map=args.sport_map, date=args.date, api_football=args.api_football)
        if args.output:
            write_json(report, args.output)
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
