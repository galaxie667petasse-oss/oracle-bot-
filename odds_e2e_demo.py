import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict

from evidence_gate import build_evidence_gate, write_html as write_evidence_html, write_json as write_evidence_json
from manual_odds_import import MANUAL_COLUMNS, normalize_manual_csv
from odds_closing_matcher import match_closing_snapshots
from odds_intake_audit import build_intake_audit, write_html as write_intake_html, write_json as write_intake_json
from odds_normalizer import write_normalized_csv
from odds_snapshot_store import append_snapshot_rows, summarize_snapshots
from odds_source_quality_report import build_quality_report, write_html as write_quality_html, write_json as write_quality_json
from odds_to_shadow import snapshots_to_shadow
from results_manual_import import import_manual_results
from shadow_clv_report import build_shadow_clv_report, write_html as write_shadow_html, write_json as write_shadow_json
from shadow_ledger import init_ledger, read_ledger
from shadow_quality_audit import audit_shadow_ledger, write_html as write_audit_html, write_json as write_audit_json


def _safe_dir(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("La demo odds ne doit pas ecrire dans data/.")
    target.mkdir(parents=True, exist_ok=True)
    return target


def write_manual_demo(path: Path) -> Path:
    rows = [
        {
            "captured_at": "2026-06-01T10:00:00",
            "source": "demo",
            "league": "EPL",
            "match_date": "2026-06-01",
            "kickoff_time": "2026-06-01T19:00:00",
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "bookmaker": "DemoBook",
            "market_type": "h2h",
            "side": "home",
            "odds": "2.10",
            "is_live": "false",
            "is_near_close": "false",
            "notes": "demo taken",
        },
        {
            "captured_at": "2026-06-01T18:55:00",
            "source": "demo",
            "league": "EPL",
            "match_date": "2026-06-01",
            "kickoff_time": "2026-06-01T19:00:00",
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "bookmaker": "DemoBook",
            "market_type": "h2h",
            "side": "home",
            "odds": "2.00",
            "is_live": "false",
            "is_near_close": "true",
            "notes": "demo near-close",
        },
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANUAL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_results_demo(path: Path, ledger_path: Path) -> Path:
    rows = read_ledger(str(ledger_path))
    shadow_id = rows[0]["shadow_id"] if rows else ""
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["shadow_id", "result", "notes"])
        writer.writeheader()
        writer.writerow({"shadow_id": shadow_id, "result": "win", "notes": "demo synthetique"})
    return path


def run_demo(output_dir: str = "reports/odds_e2e_demo", apply_to_main_reports: bool = False) -> Dict[str, Any]:
    out = _safe_dir(output_dir)
    manual = write_manual_demo(out / "manual_odds_snapshot_demo.csv")
    normalized_rows = normalize_manual_csv(str(manual))
    snapshots = out / "odds_snapshots_demo.csv"
    write_normalized_csv(normalized_rows, str(snapshots))
    store = snapshots if not apply_to_main_reports else Path("reports/odds_snapshots.csv")
    ledger = out / "shadow_ledger_demo.csv" if not apply_to_main_reports else Path("reports/shadow_ledger.csv")
    init_ledger(str(ledger))
    if apply_to_main_reports:
        append_snapshot_rows(str(store), normalized_rows)
    to_shadow = snapshots_to_shadow(str(store), str(ledger), dry_run=False, source_filter="demo")
    closing = match_closing_snapshots(str(ledger), str(store), dry_run=False, prefer_latest_before_kickoff=True)
    results_csv = write_results_demo(out / "manual_results_demo.csv", ledger)
    results = import_manual_results(str(ledger), str(results_csv), dry_run=False)
    quality = build_quality_report(str(store))
    write_quality_json(quality, str(out / "odds_source_quality_demo.json"))
    write_quality_html(quality, str(out / "odds_source_quality_demo.html"))
    intake = build_intake_audit(str(store), str(ledger))
    write_intake_json(intake, str(out / "odds_intake_audit_demo.json"))
    write_intake_html(intake, str(out / "odds_intake_audit_demo.html"))
    audit = audit_shadow_ledger(str(ledger))
    write_audit_json(audit, str(out / "shadow_quality_audit_demo.json"))
    write_audit_html(audit, str(out / "shadow_quality_audit_demo.html"))
    shadow = build_shadow_clv_report(str(ledger))
    write_shadow_json(shadow, str(out / "shadow_clv_report_demo.json"))
    write_shadow_html(shadow, str(out / "shadow_clv_report_demo.html"))
    evidence = build_evidence_gate(
        shadow_report_path=str(out / "shadow_clv_report_demo.json"),
        quality_audit_path=str(out / "shadow_quality_audit_demo.json"),
    )
    write_evidence_json(evidence, str(out / "evidence_gate_demo.json"))
    write_evidence_html(evidence, str(out / "evidence_gate_demo.html"))
    summary = {
        "output_dir": str(out),
        "manual_csv": str(manual),
        "snapshots": str(store),
        "ledger": str(ledger),
        "to_shadow": to_shadow,
        "closing": closing,
        "results": results,
        "quality": quality,
        "intake": intake,
        "shadow_report": shadow,
        "evidence": evidence,
        "message": "Demo synthetique, aucune preuve reelle.",
        "lab_only": True,
    }
    (out / "demo_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Demo end-to-end odds intake, sans reseau.")
    parser.add_argument("--output-dir", default="reports/odds_e2e_demo")
    parser.add_argument("--apply-to-main-reports", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        summary = run_demo(args.output_dir, apply_to_main_reports=args.apply_to_main_reports)
        print("Demo odds E2E Oracle")
        print(f"- Dossier: {summary['output_dir']}")
        print(f"- Observations shadow: {summary['shadow_report'].get('signals_total')}")
        print(f"- CLV coverage: {summary['shadow_report'].get('clv_coverage')}%")
        print(f"- Evidence: {summary['evidence'].get('global_status')}")
        print("- Demo synthetique, aucune preuve reelle, aucune mise.")
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
