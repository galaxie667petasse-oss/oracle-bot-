import argparse
import html
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from odds_closing_matcher import match_closing_snapshots
from odds_snapshot_store import append_csv, init_store, load_snapshots, summarize_snapshots
from shadow_clv_report import build_shadow_clv_report, write_html as write_shadow_html, write_json as write_shadow_json
from shadow_ledger import read_ledger, write_ledger


SPORT_BY_LEAGUE = {
    "J League": "soccer_japan_j_league",
    "Japan J League": "soccer_japan_j_league",
    "EPL": "soccer_epl",
    "MLS": "soccer_usa_mls",
}


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Les sorties near-close doivent rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def pending_rows(ledger: str) -> List[Dict[str, Any]]:
    return [row for row in read_ledger(ledger) if not str(row.get("closing_odds") or "").strip()]


def build_status(ledger: str) -> Dict[str, Any]:
    rows = pending_rows(ledger)
    dates = sorted({row.get("match_date") for row in rows if row.get("match_date")})
    leagues = sorted({row.get("league") for row in rows if row.get("league")})
    events = sorted({(row.get("match_date"), row.get("league"), row.get("home_team"), row.get("away_team")) for row in rows})
    return {
        "ledger": ledger,
        "pending_closing_count": len(rows),
        "next_match_date": dates[0] if dates else None,
        "leagues": leagues,
        "events": [" | ".join(str(part or "") for part in event) for event in events[:50]],
        "recommended_timing": "capturer near-close 5-10 minutes avant kickoff",
        "lab_only": True,
        "can_influence_picks": False,
    }


def suggest_commands(ledger: str, sport: str = "") -> Dict[str, Any]:
    status = build_status(ledger)
    sports = sorted({SPORT_BY_LEAGUE.get(league, sport) for league in status["leagues"] if SPORT_BY_LEAGUE.get(league, sport)})
    if sport:
        sports = [sport]
    commands = []
    for item in sports or ["soccer_japan_j_league"]:
        commands.extend([
            f"python the_odds_api_adapter.py --allow-network --sport {item} --regions us,uk,eu --markets h2h --near-close --output reports/the_odds_api_{item}_near_close.csv",
            f"python odds_snapshot_store.py --append reports/the_odds_api_{item}_near_close.csv",
            "python odds_closing_matcher.py --ledger reports/shadow_ledger.csv --snapshots reports/odds_snapshots.csv --only-shadow-pending --prefer-latest-before-kickoff --prefer-same-bookmaker --dry-run",
        ])
    return {"status": status, "commands": commands, "lab_only": True}


def write_plan(report: Dict[str, Any], output: str = "", html_output: str = "") -> None:
    if output:
        target = _safe_output(output)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if html_output:
        target = _safe_output(html_output)
        target.write_text("<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>Near-close plan</h1><pre>" + html.escape(json.dumps(report, ensure_ascii=False, indent=2)) + "</pre></body></html>", encoding="utf-8")


def run_near_close_file(
    ledger: str,
    snapshots: str,
    near_close_file: str,
    apply: bool = False,
    reports_dir: str = "reports",
) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="oracle_near_close_") as tmp:
        stage = Path(tmp)
        stage_ledger = stage / "shadow_ledger.csv"
        stage_store = stage / "odds_snapshots.csv"
        if Path(ledger).exists():
            shutil.copy2(ledger, stage_ledger)
        else:
            write_ledger([], str(stage_ledger))
        if Path(snapshots).exists():
            shutil.copy2(snapshots, stage_store)
        else:
            init_store(str(stage_store))
        append_report = append_csv(str(stage_store), near_close_file)
        match_report = match_closing_snapshots(
            str(stage_ledger),
            str(stage_store),
            prefer_latest_before_kickoff=True,
            prefer_same_bookmaker=True,
            only_shadow_pending=True,
            dry_run=False,
        )
        shadow = build_shadow_clv_report(str(stage_ledger))
        if apply:
            Path(snapshots).parent.mkdir(parents=True, exist_ok=True)
            Path(ledger).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(stage_store, snapshots)
            shutil.copy2(stage_ledger, ledger)
            reports = Path(reports_dir)
            reports.mkdir(parents=True, exist_ok=True)
            write_shadow_json(shadow, str(reports / "shadow_clv_report.json"))
            write_shadow_html(shadow, str(reports / "shadow_clv_report.html"))
        return {
            "dry_run": not apply,
            "append_report": append_report,
            "match_report": match_report,
            "shadow_report": shadow,
            "staged_store": summarize_snapshots(str(stage_store)),
            "lab_only": True,
            "can_influence_picks": False,
        }


def print_report(report: Dict[str, Any]) -> None:
    print("Workflow near-close Oracle")
    if "pending_closing_count" in report:
        print(f"- Pending closing: {report.get('pending_closing_count')}")
        print(f"- Prochain match: {report.get('next_match_date')}")
    elif "commands" in report:
        for command in report.get("commands") or []:
            print(f"- Commande: {command}")
    else:
        print(f"- Dry-run: {report.get('dry_run')}")
        print(f"- Matchs trouves: {(report.get('match_report') or {}).get('matches_found')}")
    print("- Aucune cote closing n'est inventee.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Guide la collecte near-close des observations shadow.")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--snapshots", default="reports/odds_snapshots.csv")
    parser.add_argument("--sport", default="")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--suggest-commands", action="store_true")
    parser.add_argument("--near-close-file", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    parser.add_argument("--reports-dir", default="reports")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.suggest_commands:
            report = suggest_commands(args.ledger, args.sport)
        elif args.near_close_file:
            report = run_near_close_file(args.ledger, args.snapshots, args.near_close_file, apply=args.apply, reports_dir=args.reports_dir)
        else:
            report = build_status(args.ledger)
        if args.output or args.html:
            write_plan(report, args.output, args.html)
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
