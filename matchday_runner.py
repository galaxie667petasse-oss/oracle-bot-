import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from evidence_gate import build_evidence_gate, write_html as write_evidence_html, write_json as write_evidence_json
from manual_odds_import import normalize_manual_csv, split_rows
from matchday_pack import pack_status
from odds_closing_matcher import match_closing_snapshots
from odds_intake_audit import build_intake_audit, write_html as write_intake_html, write_json as write_intake_json
from odds_snapshot_store import append_snapshot_rows, init_store
from odds_to_shadow import snapshots_to_shadow
from real_observation_guard import build_guard_report, write_html as write_guard_html, write_json as write_guard_json
from results_manual_import import import_manual_results
from shadow_clv_report import build_shadow_clv_report, write_html as write_shadow_html, write_json as write_shadow_json
from shadow_ledger import init_ledger
from shadow_quality_audit import audit_shadow_ledger, write_html as write_quality_html, write_json as write_quality_json


def _pack(path: str) -> Path:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"Pack matchday introuvable: {path}")
    return target


def _safe_reports(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Les sorties matchday doivent rester hors data/.")
    target.mkdir(parents=True, exist_ok=True)
    return target


def validate_pack(pack: str) -> Dict[str, Any]:
    target = _pack(pack)
    required = ["matchday_manual_odds.csv", "matchday_near_close.csv", "matchday_results.csv"]
    missing = [name for name in required if not (target / name).exists()]
    status = pack_status(pack)
    return {"pack": pack, "missing": missing, "valid": not missing, "status": status}


def _rows_from_manual(path: Path, near_close: bool) -> List[Dict[str, Any]]:
    rows = normalize_manual_csv(str(path))
    wanted = "true" if near_close else "false"
    return [row for row in rows if str(row.get("is_near_close") or "").lower() == wanted and row.get("validation_status") == "valid"]


def import_taken(pack: str, store: str, apply: bool = False) -> Dict[str, Any]:
    rows = _rows_from_manual(_pack(pack) / "matchday_manual_odds.csv", near_close=False)
    if not apply:
        return {"dry_run": True, "valid_taken_rows": len(rows), "store": store}
    init_store(store)
    return {"dry_run": False, "valid_taken_rows": len(rows), "store_report": append_snapshot_rows(store, rows)}


def import_near_close(pack: str, store: str, apply: bool = False) -> Dict[str, Any]:
    rows = _rows_from_manual(_pack(pack) / "matchday_near_close.csv", near_close=True)
    if not apply:
        return {"dry_run": True, "valid_near_close_rows": len(rows), "store": store}
    init_store(store)
    return {"dry_run": False, "valid_near_close_rows": len(rows), "store_report": append_snapshot_rows(store, rows)}


def to_shadow(store: str, ledger: str, apply: bool = False) -> Dict[str, Any]:
    if apply:
        init_ledger(ledger)
    return snapshots_to_shadow(store, ledger, dry_run=not apply)


def match_closing(store: str, ledger: str, apply: bool = False) -> Dict[str, Any]:
    return match_closing_snapshots(ledger, store, dry_run=not apply, prefer_latest_before_kickoff=True)


def import_results(pack: str, ledger: str, apply: bool = False) -> Dict[str, Any]:
    return import_manual_results(ledger, str(_pack(pack) / "matchday_results.csv"), dry_run=not apply)


def write_matchday_report(pack: str, ledger: str, store: str, reports_dir: str) -> Dict[str, Any]:
    reports = _safe_reports(reports_dir)
    status = pack_status(pack)
    guard = build_guard_report(ledger, store)
    write_guard_json(guard, str(reports / "real_observation_guard.json"))
    write_guard_html(guard, str(reports / "real_observation_guard.html"))
    shadow = build_shadow_clv_report(ledger)
    write_shadow_json(shadow, str(reports / "shadow_clv_report.json"))
    write_shadow_html(shadow, str(reports / "shadow_clv_report.html"))
    quality = audit_shadow_ledger(ledger)
    write_quality_json(quality, str(reports / "shadow_quality_audit.json"))
    write_quality_html(quality, str(reports / "shadow_quality_audit.html"))
    intake = build_intake_audit(store, ledger)
    write_intake_json(intake, str(reports / "odds_intake_audit.json"))
    write_intake_html(intake, str(reports / "odds_intake_audit.html"))
    evidence = build_evidence_gate(
        shadow_report_path=str(reports / "shadow_clv_report.json"),
        quality_audit_path=str(reports / "shadow_quality_audit.json"),
        big5_summary_path=str(reports / "big5_xg_summary.json"),
        clv_readiness_path=str(reports / "clv_readiness.json"),
        real_guard_path=str(reports / "real_observation_guard.json"),
        matchday_status_path=str(Path(pack) / "matchday_status.json"),
    )
    write_evidence_json(evidence, str(reports / "evidence_gate.json"))
    write_evidence_html(evidence, str(reports / "evidence_gate.html"))
    summary = {"matchday_status": status, "guard": guard, "shadow": shadow, "quality": quality, "intake": intake, "evidence": evidence}
    (reports / "matchday_runner_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def full_dry_run(pack: str, ledger: str, store: str, reports_dir: str) -> Dict[str, Any]:
    return {
        "validate": validate_pack(pack),
        "import_taken": import_taken(pack, store, apply=False),
        "to_shadow": to_shadow(store, ledger, apply=False),
        "import_near_close": import_near_close(pack, store, apply=False),
        "match_closing": match_closing(store, ledger, apply=False),
        "guard": build_guard_report(ledger, store),
        "report_dir": reports_dir,
        "dry_run": True,
    }


def full_apply(pack: str, ledger: str, store: str, reports_dir: str) -> Dict[str, Any]:
    guard = build_guard_report(ledger, store)
    if guard.get("verdict") in {"mixed_test_and_real", "invalid"}:
        return {"applied": False, "error": "guard refuse l'application", "guard": guard}
    return {
        "applied": True,
        "import_taken": import_taken(pack, store, apply=True),
        "to_shadow": to_shadow(store, ledger, apply=True),
        "import_near_close": import_near_close(pack, store, apply=True),
        "match_closing": match_closing(store, ledger, apply=True),
        "import_results": import_results(pack, ledger, apply=True),
        "report": write_matchday_report(pack, ledger, store, reports_dir),
    }


def print_json(title: str, payload: Dict[str, Any]) -> None:
    print(title)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("- Observation seulement, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Execute un workflow matchday local.")
    parser.add_argument("--pack", required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--validate", action="store_true")
    group.add_argument("--import-taken", action="store_true")
    group.add_argument("--to-shadow", action="store_true")
    group.add_argument("--import-near-close", action="store_true")
    group.add_argument("--match-closing", action="store_true")
    group.add_argument("--import-results", action="store_true")
    group.add_argument("--report", action="store_true")
    group.add_argument("--full-dry-run", action="store_true")
    group.add_argument("--full-apply", action="store_true")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--store", default="reports/odds_snapshots.csv")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.validate:
            payload = validate_pack(args.pack)
        elif args.import_taken:
            payload = import_taken(args.pack, args.store, args.apply)
        elif args.to_shadow:
            payload = to_shadow(args.store, args.ledger, args.apply)
        elif args.import_near_close:
            payload = import_near_close(args.pack, args.store, args.apply)
        elif args.match_closing:
            payload = match_closing(args.store, args.ledger, args.apply)
        elif args.import_results:
            payload = import_results(args.pack, args.ledger, args.apply)
        elif args.report:
            payload = write_matchday_report(args.pack, args.ledger, args.store, args.reports_dir)
        elif args.full_apply:
            payload = full_apply(args.pack, args.ledger, args.store, args.reports_dir)
        else:
            payload = full_dry_run(args.pack, args.ledger, args.store, args.reports_dir)
        print_json("Matchday runner Oracle", payload)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
