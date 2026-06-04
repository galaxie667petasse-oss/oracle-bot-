import argparse
import csv
import html
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from near_close_scheduler import build_schedule
from odds_closing_matcher import match_closing_snapshots


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Les sorties near-close batch doivent rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _write_rows(rows: List[Dict[str, Any]], output: str) -> Path:
    target = _safe_output(output)
    fieldnames = sorted({key for row in rows for key in row.keys()}) or ["empty"]
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return target


def _collect_command(item: Dict[str, Any], output_dir: str) -> List[str]:
    sport = item.get("sport_key") or ""
    if not sport:
        return []
    safe = str(sport).replace("/", "_").replace(" ", "_")
    output = str(Path(output_dir) / f"the_odds_api_{safe}_near_close.csv")
    return [
        "the_odds_api_adapter.py",
        "--allow-network",
        "--sport",
        sport,
        "--regions",
        "us,uk,eu",
        "--markets",
        "h2h",
        "--near-close",
        "--output",
        output,
    ]


def run_batch(
    ledger: str,
    sport_map: str = "",
    snapshots: str = "reports/odds_snapshots.csv",
    apply_existing: str = "",
    output_dir: str = "reports",
    allow_network: bool = False,
    apply: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    schedule = build_schedule(ledger, sport_map)
    commands: List[str] = []
    network_runs: List[Dict[str, Any]] = []
    match_reports: List[Dict[str, Any]] = []
    for item in schedule.get("schedule") or []:
        command = _collect_command(item, output_dir)
        if command:
            commands.append(" ".join([sys.executable, *command]))
            if allow_network and not dry_run:
                completed = subprocess.run([sys.executable, *command], text=True, capture_output=True, encoding="utf-8", errors="replace", timeout=1200)
                network_runs.append({"command": " ".join([sys.executable, *command]), "returncode": completed.returncode, "stdout": completed.stdout[-1000:], "stderr": completed.stderr[-1000:]})
    if apply_existing:
        for path in sorted(Path(apply_existing).glob("*.csv")):
            match_reports.append(match_closing_snapshots(ledger, str(path), prefer_latest_before_kickoff=True, prefer_same_bookmaker=True, only_shadow_pending=True, dry_run=not apply))
    return {
        "ledger": ledger,
        "snapshots": snapshots,
        "pending_total": schedule.get("pending_total"),
        "leagues_count": schedule.get("leagues_count"),
        "commands": commands,
        "network_allowed": allow_network,
        "dry_run": dry_run or not allow_network,
        "network_runs": network_runs,
        "apply_existing": apply_existing or None,
        "apply": apply,
        "match_reports": match_reports,
        "message": "Batch near-close local: aucun reseau sans --allow-network.",
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    commands = "".join(f"<li><code>{html.escape(str(command))}</code></li>" for command in report.get("commands") or [])
    target.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>Near-close batch runner</h1>"
        f"<p>Pending total: {report.get('pending_total')}</p>"
        f"<p>Reseau autorise: {report.get('network_allowed')}</p><ul>{commands}</ul>"
        "<p>Observation seulement, aucune mise.</p></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Near-close batch runner Oracle")
    print(f"- Pending total: {report.get('pending_total')}")
    print(f"- Commandes preparees: {len(report.get('commands') or [])}")
    print(f"- Reseau autorise: {report.get('network_allowed')}")
    print(f"- Match reports: {len(report.get('match_reports') or [])}")
    print("- Aucun reseau sans --allow-network.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Prepare ou lance une collecte near-close batch.")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--sport-map", default="")
    parser.add_argument("--snapshots", default="reports/odds_snapshots.csv")
    parser.add_argument("--apply-existing", default="")
    parser.add_argument("--output-dir", default="reports")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    parser.add_argument("--commands-csv", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = run_batch(
            args.ledger,
            sport_map=args.sport_map,
            snapshots=args.snapshots,
            apply_existing=args.apply_existing,
            output_dir=args.output_dir,
            allow_network=args.allow_network,
            apply=args.apply,
            dry_run=args.dry_run,
        )
        if args.output:
            write_json(report, args.output)
        if args.html:
            write_html(report, args.html)
        if args.commands_csv:
            _write_rows([{"command": command} for command in report.get("commands") or []], args.commands_csv)
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
