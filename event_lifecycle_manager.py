import argparse
import html
import json
from datetime import datetime, time
from pathlib import Path
from typing import Any, Dict, List, Optional

from shadow_ledger import read_ledger


COMPLETE_RESULTS = {"win", "loss", "push", "void"}
REQUIRED_FIELDS = ["shadow_id", "match_date", "league", "home_team", "away_team", "market_type", "side", "taken_odds"]


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le rapport lifecycle doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _parse_dt(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        try:
            return datetime.fromisoformat(text[:19]).replace(tzinfo=None)
        except Exception:
            return None


def _parse_match_date(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.combine(datetime.fromisoformat(text[:10]).date(), time.min)
    except Exception:
        return None


def _extract_kickoff(row: Dict[str, Any]) -> str:
    direct = str(row.get("kickoff_time") or "").strip()
    if direct:
        return direct
    notes = str(row.get("notes") or "")
    for token in notes.replace(";", " ").replace("|", " ").split():
        if token.lower().startswith("kickoff_time="):
            return token.split("=", 1)[1]
    return ""


def _minutes_to_kickoff(row: Dict[str, Any], now: Optional[datetime]) -> Optional[float]:
    kickoff = _parse_dt(_extract_kickoff(row))
    if not kickoff or not now:
        return None
    return round((kickoff - now).total_seconds() / 60.0, 2)


def classify_row(row: Dict[str, Any], now: Optional[datetime] = None, minutes_before: int = 120) -> Dict[str, Any]:
    now = now or datetime.now()
    missing = [field for field in REQUIRED_FIELDS if not str(row.get(field) or "").strip()]
    result = str(row.get("result") or "unknown").strip().lower() or "unknown"
    closing = str(row.get("closing_odds") or "").strip()
    match_dt = _parse_match_date(row.get("match_date"))
    minutes = _minutes_to_kickoff(row, now)
    kickoff_time = _extract_kickoff(row)
    if missing:
        status = "invalid"
        next_action = "corriger les champs obligatoires du ledger"
    elif result in COMPLETE_RESULTS:
        status = "complete"
        next_action = "relire le rapport CLV shadow"
    elif closing:
        if match_dt and match_dt.date() < now.date():
            status = "result_overdue"
            next_action = "renseigner le resultat manuel"
        elif match_dt and match_dt.date() > now.date():
            status = "closing_captured"
            next_action = "attendre le match puis renseigner le resultat"
        else:
            status = "waiting_result"
            next_action = "attendre puis renseigner le resultat"
    else:
        if minutes is not None:
            if minutes < 0:
                status = "near_close_overdue"
                next_action = "verifier si une near-close reelle existe encore dans une source fiable"
            elif minutes <= minutes_before:
                status = "near_close_due_soon"
                next_action = "capturer la near-close reelle"
            else:
                status = "pre_match_waiting_close"
                next_action = "attendre la fenetre near-close"
        elif match_dt and match_dt.date() < now.date():
            status = "near_close_overdue"
            next_action = "verifier si une near-close reelle existe encore dans une source fiable"
        elif match_dt and match_dt.date() == now.date():
            status = "near_close_due_soon"
            next_action = "capturer la near-close reelle si le match approche"
        else:
            status = "pre_match_waiting_close"
            next_action = "attendre la fenetre near-close"
    return {
        "shadow_id": row.get("shadow_id"),
        "match_date": row.get("match_date"),
        "kickoff_time": kickoff_time,
        "league": row.get("league"),
        "home_team": row.get("home_team"),
        "away_team": row.get("away_team"),
        "market_type": row.get("market_type"),
        "side": row.get("side"),
        "bookmaker": row.get("bookmaker"),
        "taken_odds": row.get("taken_odds"),
        "closing_odds": row.get("closing_odds"),
        "result": result,
        "lifecycle_status": status,
        "minutes_to_kickoff": minutes,
        "missing_fields": missing,
        "next_action": next_action,
    }


def build_lifecycle_report(ledger: str, minutes_before: int = 120, now: Optional[datetime] = None) -> Dict[str, Any]:
    rows = [classify_row(row, now=now, minutes_before=minutes_before) for row in read_ledger(ledger)]
    counts: Dict[str, int] = {}
    for row in rows:
        status = row["lifecycle_status"]
        counts[status] = counts.get(status, 0) + 1
    due_now = [row for row in rows if row["lifecycle_status"] in {"near_close_due_soon", "near_close_overdue"}]
    due_results = [row for row in rows if row["lifecycle_status"] in {"closing_captured", "waiting_result", "result_overdue"}]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ledger": ledger,
        "minutes_before": minutes_before,
        "total_observations": len(rows),
        "status_counts": counts,
        "pending_closing": sum(counts.get(key, 0) for key in ("pre_match_waiting_close", "near_close_due_soon", "near_close_overdue")),
        "pending_results": sum(counts.get(key, 0) for key in ("closing_captured", "waiting_result", "result_overdue")),
        "completed": counts.get("complete", 0),
        "due_now": due_now,
        "due_results": due_results,
        "observations": rows,
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
        "<tr>"
        + f"<td>{html.escape(str(item.get('shadow_id') or ''))}</td>"
        + f"<td>{html.escape(str(item.get('match_date') or ''))}</td><td>{html.escape(str(item.get('league') or ''))}</td>"
        + f"<td>{html.escape(str(item.get('home_team') or ''))} - {html.escape(str(item.get('away_team') or ''))}</td>"
        + f"<td>{html.escape(str(item.get('market_type') or ''))}/{html.escape(str(item.get('side') or ''))}</td>"
        + f"<td>{html.escape(str(item.get('lifecycle_status') or ''))}</td><td>{html.escape(str(item.get('next_action') or ''))}</td>"
        + "</tr>"
        for item in report.get("observations") or []
    )
    target.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>Event Lifecycle Oracle</h1>"
        f"<p>Observations: {report.get('total_observations')} | Pending closing: {report.get('pending_closing')} | Pending results: {report.get('pending_results')}</p>"
        "<table border='1'><tr><th>ID</th><th>Date</th><th>Ligue</th><th>Match</th><th>Marche</th><th>Statut</th><th>Action</th></tr>"
        + rows
        + "</table><p>Observation seulement, aucune mise.</p></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any], mode: str = "status") -> None:
    print("Event Lifecycle Oracle")
    print(f"- Observations: {report.get('total_observations')}")
    print(f"- Pending closing: {report.get('pending_closing')}")
    print(f"- Pending results: {report.get('pending_results')}")
    print(f"- Complete: {report.get('completed')}")
    rows = report.get("observations") or []
    if mode == "due_now":
        rows = report.get("due_now") or []
    elif mode == "due_results":
        rows = report.get("due_results") or []
    for row in rows[:30]:
        print(f"- {row.get('shadow_id')} | {row.get('match_date')} | {row.get('home_team')} - {row.get('away_team')} | {row.get('lifecycle_status')} | {row.get('next_action')}")
    print("- Laboratoire local: preuve insuffisante tant que CLV/resultats manquent.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Classe le cycle de vie des observations shadow.")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--due-now", action="store_true")
    parser.add_argument("--due-results", action="store_true")
    parser.add_argument("--minutes-before", type=int, default=120)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = build_lifecycle_report(args.ledger, minutes_before=args.minutes_before)
        if args.output:
            write_json(report, args.output)
        if args.html:
            write_html(report, args.html)
        mode = "due_now" if args.due_now else ("due_results" if args.due_results else "status")
        print_report(report, mode=mode)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
