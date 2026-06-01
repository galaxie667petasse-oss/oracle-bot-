import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from manual_odds_import import MANUAL_COLUMNS, build_summary, normalize_manual_csv, split_rows, write_rejects, write_template, write_valid
from odds_closing_matcher import match_closing_snapshots
from odds_intake_audit import build_intake_audit
from odds_snapshot_store import DEFAULT_STORE, append_snapshot_rows, init_store, summarize_snapshots
from odds_source_config import load_odds_source_config, validate_config
from odds_source_quality_report import build_quality_report
from odds_to_shadow import snapshots_to_shadow
from shadow_clv_report import build_shadow_clv_report
from shadow_ledger import DEFAULT_LEDGER, init_ledger, summarize_ledger
from shadow_templates import create_candidates_template, create_closing_template, create_results_template
from matchday_pack import create_pack, pack_status
from matchday_runner import full_apply as matchday_full_apply, full_dry_run as matchday_full_dry_run
from real_observation_guard import build_guard_report
from test_archive_manager import archive_and_reset


def _read_optional_json(path: str) -> Dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _safe(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le wizard odds ne doit rien ecrire dans data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def build_status(store: str = DEFAULT_STORE, ledger: str = DEFAULT_LEDGER, reports_dir: str = "reports") -> Dict[str, Any]:
    config = validate_config(load_odds_source_config())
    store_summary = summarize_snapshots(store)
    ledger_summary = summarize_ledger(ledger)
    shadow_report_path = Path(reports_dir) / "shadow_clv_report.json"
    evidence_path = Path(reports_dir) / "evidence_gate.json"
    shadow_report = _read_optional_json(str(shadow_report_path)) if shadow_report_path.exists() else {}
    evidence = _read_optional_json(str(evidence_path)) if evidence_path.exists() else {}
    return {
        "config_ok": config.get("ok"),
        "config_warnings": config.get("warnings") or [],
        "store_exists": Path(store).exists(),
        "ledger_exists": Path(ledger).exists(),
        "snapshots_total": store_summary.get("rows_total"),
        "snapshots_taken": store_summary.get("taken_count"),
        "snapshots_near_close": store_summary.get("near_close_rows"),
        "shadow_observations": ledger_summary.get("signals_total"),
        "pending_closing": shadow_report.get("pending_closing"),
        "clv_coverage": shadow_report.get("clv_coverage"),
        "evidence_status": evidence.get("global_status"),
        "lab_only": True,
    }


def make_templates(reports_dir: str = "reports", ledger: str = DEFAULT_LEDGER, force: bool = False) -> Dict[str, str]:
    reports = Path(reports_dir)
    reports.mkdir(parents=True, exist_ok=True)
    candidates_path = reports / "shadow_candidates_template.csv"
    out = {
        "manual_odds": str(write_template(str(reports / "manual_odds_snapshot_template.csv"))),
        "shadow_candidates": str(candidates_path if candidates_path.exists() and not force else create_candidates_template(str(candidates_path), force=force)),
    }
    if Path(ledger).exists():
        closing_path = reports / "manual_closing_import_template.csv"
        results_path = reports / "manual_results_import_template.csv"
        out["manual_closing"] = str(closing_path if closing_path.exists() and not force else create_closing_template(str(closing_path), ledger=ledger, force=True))
        out["manual_results"] = str(results_path if results_path.exists() and not force else create_results_template(str(results_path), ledger=ledger, force=True))
    return out


def validate_manual(path: str) -> Dict[str, Any]:
    rows = normalize_manual_csv(path)
    return build_summary(path, rows)


def import_manual(path: str, store: str = DEFAULT_STORE, allow_errors: bool = False) -> Dict[str, Any]:
    rows = normalize_manual_csv(path)
    split = split_rows(rows)
    if split["rejected"] and not allow_errors:
        return {**build_summary(path, rows, store_path=store), "imported": False, "error": "lignes rejetees presentes"}
    report = append_snapshot_rows(store, split["valid"])
    return {**build_summary(path, rows, store_path=store), "imported": True, "store_report": report}


def dry_run_full(store: str = DEFAULT_STORE, ledger: str = DEFAULT_LEDGER, reports_dir: str = "reports") -> Dict[str, Any]:
    return {
        "config": validate_config(load_odds_source_config()),
        "store": summarize_snapshots(store),
        "quality": build_quality_report(store),
        "odds_to_shadow": snapshots_to_shadow(store, ledger, dry_run=True),
        "closing_matcher": match_closing_snapshots(ledger, store, dry_run=True),
        "intake_audit": build_intake_audit(store, ledger),
        "message": "Dry-run complet: aucune ecriture ledger, aucun reseau.",
    }


def write_demo_csv(path: str) -> Path:
    target = _safe(path)
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
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANUAL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return target


def demo(reports_dir: str = "reports", store: str = DEFAULT_STORE, ledger: str = DEFAULT_LEDGER, apply: bool = False, force: bool = False) -> Dict[str, Any]:
    reports = Path(reports_dir)
    reports.mkdir(parents=True, exist_ok=True)
    manual = write_demo_csv(str(reports / "odds_demo_manual.csv"))
    rows = normalize_manual_csv(str(manual))
    demo_store = reports / "odds_demo_snapshots.csv"
    from odds_normalizer import write_normalized_csv
    write_normalized_csv(rows, str(demo_store))
    result = {
        "manual_demo": str(manual),
        "snapshot_demo": str(demo_store),
        "apply": apply,
        "commands": [
            f"python manual_odds_import.py --input {manual} --store {store}",
            f"python odds_to_shadow.py --snapshots {store} --ledger {ledger} --dry-run",
            f"python odds_closing_matcher.py --ledger {ledger} --snapshots {store} --dry-run --prefer-latest-before-kickoff",
        ],
        "message": "Demo synthetique, aucune preuve reelle.",
    }
    if apply:
        init_store(store)
        init_ledger(ledger)
        result["import_manual"] = import_manual(str(manual), store=store, allow_errors=True)
        result["to_shadow"] = snapshots_to_shadow(store, ledger, dry_run=False, source_filter="demo")
        result["closing_match"] = match_closing_snapshots(ledger, store, dry_run=False, prefer_latest_before_kickoff=True)
    return result


def next_actions(store: str = DEFAULT_STORE, ledger: str = DEFAULT_LEDGER) -> List[str]:
    status = build_status(store, ledger)
    actions = []
    if not status["store_exists"]:
        actions.append("python odds_snapshot_store.py --init")
    actions.append("python odds_lab_wizard.py --make-templates")
    actions.append("remplir reports/manual_odds_snapshot.csv avec 2-3 cotes reelles")
    actions.append("python odds_lab_wizard.py --validate-manual reports/manual_odds_snapshot.csv")
    actions.append("python odds_lab_wizard.py --import-manual reports/manual_odds_snapshot.csv --apply")
    actions.append("python odds_to_shadow.py --snapshots reports/odds_snapshots.csv --ledger reports/shadow_ledger.csv --dry-run")
    return actions[:6]


def real_start(store: str = DEFAULT_STORE, ledger: str = DEFAULT_LEDGER) -> Dict[str, Any]:
    guard = build_guard_report(ledger, store)
    commands = [
        "python test_archive_manager.py --archive-and-reset --label before_real_june",
        "python matchday_pack.py --date YYYY-MM-DD --output-dir reports/matchday_YYYY_MM_DD",
        "python matchday_runner.py --pack reports/matchday_YYYY_MM_DD --full-dry-run",
    ]
    if guard.get("verdict") in {"mixed_test_and_real", "needs_review", "invalid"} or guard.get("test_like_rows", 0):
        recommendation = "archiver les tests avant collecte reelle"
    else:
        recommendation = "workspace pret ou vide pour collecte reelle"
    return {"guard": guard, "recommendation": recommendation, "commands": commands}


def archive_tests(reports_dir: str = "reports", label: str = "before_real_june") -> Dict[str, Any]:
    return archive_and_reset(reports_dir, label=label, include_templates=False)


def matchday_pack_command(match_date: str, reports_dir: str = "reports", from_csv: str = "") -> Dict[str, Any]:
    if not match_date:
        raise ValueError("--date requis avec --matchday-pack")
    safe = match_date.replace("-", "_")
    return create_pack(match_date, str(Path(reports_dir) / f"matchday_{safe}"), from_csv=from_csv)


def print_json(title: str, payload: Any) -> None:
    print(title)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("- Laboratoire local: aucune mise, aucun reseau.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Assistant local du workflow odds lab.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--status", action="store_true")
    group.add_argument("--make-templates", action="store_true")
    group.add_argument("--validate-manual", default="")
    group.add_argument("--import-manual", default="")
    group.add_argument("--dry-run-full", action="store_true")
    group.add_argument("--demo", action="store_true")
    group.add_argument("--next-actions", action="store_true")
    group.add_argument("--real-start", action="store_true")
    group.add_argument("--archive-tests", action="store_true")
    group.add_argument("--matchday-pack", action="store_true")
    group.add_argument("--matchday-status", default="")
    group.add_argument("--matchday-dry-run", default="")
    group.add_argument("--matchday-apply", default="")
    parser.add_argument("--store", default=DEFAULT_STORE)
    parser.add_argument("--ledger", default=DEFAULT_LEDGER)
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-errors", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--date", default="")
    parser.add_argument("--from-csv", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.status:
            print_json("Odds Lab Wizard - status", build_status(args.store, args.ledger, args.reports_dir))
        elif args.make_templates:
            print_json("Odds Lab Wizard - templates", make_templates(args.reports_dir, args.ledger, args.force))
        elif args.validate_manual:
            print_json("Odds Lab Wizard - validation manuelle", validate_manual(args.validate_manual))
        elif args.import_manual:
            if not args.apply:
                print_json("Odds Lab Wizard - import dry-run", validate_manual(args.import_manual))
            else:
                print_json("Odds Lab Wizard - import", import_manual(args.import_manual, args.store, args.allow_errors))
        elif args.dry_run_full:
            print_json("Odds Lab Wizard - dry-run complet", dry_run_full(args.store, args.ledger, args.reports_dir))
        elif args.demo:
            print_json("Odds Lab Wizard - demo", demo(args.reports_dir, args.store, args.ledger, apply=args.apply, force=args.force))
        elif args.next_actions:
            print_json("Odds Lab Wizard - prochaines actions", next_actions(args.store, args.ledger))
        elif args.real_start:
            print_json("Odds Lab Wizard - demarrage reel", real_start(args.store, args.ledger))
        elif args.archive_tests:
            print_json("Odds Lab Wizard - archive tests", archive_tests(args.reports_dir))
        elif args.matchday_pack:
            print_json("Odds Lab Wizard - matchday pack", matchday_pack_command(args.date, args.reports_dir, args.from_csv))
        elif args.matchday_status:
            print_json("Odds Lab Wizard - matchday status", pack_status(args.matchday_status))
        elif args.matchday_dry_run:
            print_json("Odds Lab Wizard - matchday dry-run", matchday_full_dry_run(args.matchday_dry_run, args.ledger, args.store, args.reports_dir))
        elif args.matchday_apply:
            print_json("Odds Lab Wizard - matchday apply", matchday_full_apply(args.matchday_apply, args.ledger, args.store, args.reports_dir))
        else:
            print_json("Odds Lab Wizard - status", build_status(args.store, args.ledger, args.reports_dir))
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
