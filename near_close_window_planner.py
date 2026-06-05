import argparse
import csv
import html
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from near_close_scheduler import load_sport_map
from shadow_ledger import read_ledger


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le plan near-close doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _parse_dt(value: str, fallback_date: str = "") -> Optional[datetime]:
    text = str(value or "").strip()
    if not text and fallback_date:
        text = f"{fallback_date}T12:00:00"
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    for candidate in (text, text.replace(" ", "T")):
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except Exception:
            pass
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d")
    except Exception:
        return None


def _source_event_id(row: Dict[str, Any]) -> str:
    notes = str(row.get("notes") or "")
    for part in notes.split(";"):
        if "source_event_id=" in part:
            return part.split("source_event_id=", 1)[1].strip()
    return str(row.get("source_event_id") or row.get("fixture_id") or "").strip()


def _note_value(row: Dict[str, Any], key: str) -> str:
    notes = str(row.get("notes") or "")
    prefix = f"{key}="
    for part in notes.split(";"):
        part = part.strip()
        if part.startswith(prefix):
            return part.split("=", 1)[1].strip()
    return ""


def _command_for(row: Dict[str, Any], sport_map: Dict[str, str]) -> str:
    fixture_id = _source_event_id(row)
    if fixture_id:
        return f"python api_football_odds_adapter.py --allow-network --fixture-id {fixture_id} --output reports/api_football_near_close_{fixture_id}.csv"
    league = str(row.get("league") or "")
    sport_key = sport_map.get(league, "")
    if sport_key:
        return f"python near_close_batch_runner.py --ledger reports/shadow_ledger.csv --allow-network --dry-run"
    return "python manual_betclic_intake_helper.py --template reports/betclic_manual_intake.csv"


def build_window_plan(
    ledger: str = "reports/shadow_ledger.csv",
    hours_before: float = 2.0,
    now: str = "",
    sport_map_path: str = "",
    due_now_only: bool = False,
) -> Dict[str, Any]:
    current = _parse_dt(now) if now else datetime.now()
    sport_map = load_sport_map(sport_map_path)
    rows = read_ledger(ledger)
    observations: List[Dict[str, Any]] = []
    status_counts: Dict[str, int] = {}
    for row in rows:
        kickoff_text = str(row.get("kickoff_time") or _note_value(row, "kickoff_time") or "")
        kickoff = _parse_dt(kickoff_text, str(row.get("match_date") or ""))
        closing_missing = not str(row.get("closing_odds") or "").strip()
        result_missing = str(row.get("result") or "unknown").lower() == "unknown"
        minutes_to_kickoff = None
        if kickoff:
            minutes_to_kickoff = round((kickoff - current).total_seconds() / 60.0, 2)
        if not closing_missing:
            status = "result_due" if result_missing and minutes_to_kickoff is not None and minutes_to_kickoff < -120 else "captured"
        elif minutes_to_kickoff is None:
            status = "too_early"
        elif minutes_to_kickoff < 0:
            status = "overdue"
        elif minutes_to_kickoff <= hours_before * 60:
            status = "due_now"
        else:
            status = "too_early"
        status_counts[status] = status_counts.get(status, 0) + 1
        item = {
            "shadow_id": row.get("shadow_id"),
            "league": row.get("league"),
            "match_date": row.get("match_date"),
            "kickoff_time": kickoff_text,
            "home_team": row.get("home_team"),
            "away_team": row.get("away_team"),
            "bookmaker": row.get("bookmaker"),
            "market_type": row.get("market_type"),
            "side": row.get("side"),
            "taken_odds": row.get("taken_odds"),
            "closing_missing": closing_missing,
            "minutes_to_kickoff": minutes_to_kickoff,
            "near_close_status": status,
            "recommended_command": _command_for(row, sport_map),
            "lab_only": True,
            "can_influence_picks": False,
        }
        if not due_now_only or status == "due_now":
            observations.append(item)
    return {
        "ledger": ledger,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "now": current.isoformat(timespec="seconds"),
        "hours_before": hours_before,
        "rows_total": len(rows),
        "status_counts": status_counts,
        "due_now_count": status_counts.get("due_now", 0),
        "overdue_count": status_counts.get("overdue", 0),
        "observations": observations,
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    rows = "".join(
        f"<tr><td>{html.escape(str(item.get('shadow_id')))}</td><td>{html.escape(str(item.get('match_date')))}</td><td>{html.escape(str(item.get('home_team')))} - {html.escape(str(item.get('away_team')))}</td><td>{html.escape(str(item.get('near_close_status')))}</td><td><code>{html.escape(str(item.get('recommended_command')))}</code></td></tr>"
        for item in report.get("observations") or []
    )
    target.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>Near-Close Window Planner</h1>"
        f"<p>Due now: {report.get('due_now_count')}</p>"
        f"<p>Overdue: {report.get('overdue_count')}</p>"
        "<table border='1'><tr><th>Shadow</th><th>Date</th><th>Match</th><th>Statut</th><th>Commande</th></tr>"
        + rows
        + "</table><p>Laboratoire local, aucune mise.</p></body></html>",
        encoding="utf-8",
    )
    return target


def write_csv(rows: List[Dict[str, Any]], output: str) -> Path:
    target = _safe_output(output)
    fields = sorted({key for row in rows for key in row.keys()}) or ["empty"]
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Near-close window planner")
    print(f"- Ledger: {report.get('ledger')}")
    print(f"- Observations: {report.get('rows_total')}")
    print(f"- Due now: {report.get('due_now_count')}")
    print(f"- Overdue: {report.get('overdue_count')}")
    for status, count in (report.get("status_counts") or {}).items():
        print(f"- {status}: {count}")
    print("- Plan local: aucune requete reseau lancee.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Planifie les fenetres near-close du ledger shadow.")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--hours-before", type=float, default=2.0)
    parser.add_argument("--now", default="")
    parser.add_argument("--sport-map", default="")
    parser.add_argument("--due-now", action="store_true")
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    parser.add_argument("--csv", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = build_window_plan(args.ledger, args.hours_before, args.now, args.sport_map, args.due_now)
        if args.output:
            write_json(report, args.output)
        if args.html:
            write_html(report, args.html)
        if args.csv:
            write_csv(report.get("observations") or [], args.csv)
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
