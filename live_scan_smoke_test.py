import argparse
import html
import json
from pathlib import Path
from typing import Any, Dict

from api_football_next_days_runner import run_next_days


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le smoke test live scan doit ecrire hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def default_json_path(date: str) -> str:
    return f"reports/live_scan_smoke_test_{date}.json"


def default_html_path(date: str) -> str:
    return f"reports/live_scan_smoke_test_{date}.html"


def build_live_scan_smoke_test(
    date: str,
    days: int = 1,
    allow_network: bool = False,
    debug: bool = False,
    output_json: str = "",
    output_html: str = "",
    output_dir: str = "reports/live_scan_smoke_next_days",
    ledger: str = "reports/shadow_ledger.csv",
) -> Dict[str, Any]:
    if not date:
        raise ValueError("--date requis")
    summary = run_next_days(
        date,
        days=days,
        output_dir=output_dir,
        ledger=ledger,
        allow_network=allow_network,
        dry_run=True,
        apply=False,
        debug_network=debug,
    )
    if allow_network and not summary.get("allow_network"):
        raise RuntimeError("Erreur: --allow-network demande mais non actif dans live_scan_smoke_test.")
    fixtures_total = int(summary.get("fixtures_total") or 0)
    odds_valid_total = int(summary.get("odds_valid_total") or 0)
    h2h_total = int(summary.get("h2h_valid_not_finished_total") or 0)
    explanations = []
    if not allow_network:
        explanations.append("reseau non autorise: smoke test offline uniquement")
    if allow_network and fixtures_total == 0:
        explanations.append("API-Football a retourne 0 fixture ou la cle/quota/source ne donne aucun match pour la periode")
    if fixtures_total > 0 and odds_valid_total == 0:
        explanations.append("fixtures detectees mais aucune cote valide apres enrichissement")
    if odds_valid_total > 0 and h2h_total == 0:
        explanations.append("odds detectees mais aucun H2H non termine exploitable")
    report = {
        "date": date,
        "days": days,
        "allow_network": bool(allow_network),
        "dry_run": True,
        "ledger_write": False,
        "telegram_send": False,
        "fixtures_total": fixtures_total,
        "odds_valid_total": odds_valid_total,
        "h2h_valid_not_finished_total": h2h_total,
        "selected_total": int(summary.get("selected_total") or 0),
        "status": "fixtures_detectees" if fixtures_total > 0 else "aucune_fixture_detectee",
        "explanations": explanations,
        "next_days_summary": summary,
        "lab_only": True,
        "can_influence_picks": False,
    }
    write_json(report, output_json or default_json_path(date))
    write_html(report, output_html or default_html_path(date))
    return report


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>Live Scan Smoke Test</h1><pre>"
        + html.escape(json.dumps(report, ensure_ascii=False, indent=2))
        + "</pre><p>Laboratoire local, aucun ledger ecrit, aucun Telegram.</p></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Live scan smoke test Oracle")
    print(f"- Date: {report.get('date')}")
    print(f"- Days: {report.get('days')}")
    print(f"- Reseau autorise: {report.get('allow_network')}")
    print(f"- Fixtures: {report.get('fixtures_total')}")
    print(f"- Odds valides: {report.get('odds_valid_total')}")
    print(f"- H2H non termines: {report.get('h2h_valid_not_finished_total')}")
    print(f"- Selection dry-run: {report.get('selected_total')}")
    for explanation in report.get("explanations") or []:
        print(f"- Diagnostic: {explanation}")
    print("- Aucun ledger ecrit, aucun Telegram, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Smoke test live scan API-Football sans ecriture ledger.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--output-json", default="")
    parser.add_argument("--html", default="")
    parser.add_argument("--output-dir", default="reports/live_scan_smoke_next_days")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = build_live_scan_smoke_test(
            args.date,
            days=args.days,
            allow_network=args.allow_network,
            debug=args.debug,
            output_json=args.output_json,
            output_html=args.html,
            output_dir=args.output_dir,
            ledger=args.ledger,
        )
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
