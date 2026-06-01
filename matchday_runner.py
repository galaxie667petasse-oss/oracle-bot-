import argparse
import csv
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from evidence_gate import build_evidence_gate, write_html as write_evidence_html, write_json as write_evidence_json
from manual_odds_import import normalize_manual_csv
from matchday_pack import pack_status
from odds_closing_matcher import match_closing_snapshots
from odds_intake_audit import build_intake_audit, write_html as write_intake_html, write_json as write_intake_json
from odds_snapshot_store import append_snapshot_rows, init_store, load_snapshots
from odds_to_shadow import snapshots_to_shadow
from real_observation_guard import build_guard_report, write_html as write_guard_html, write_json as write_guard_json
from results_manual_import import VALID_RESULTS, import_manual_results
from shadow_clv_report import build_shadow_clv_report, write_html as write_shadow_html, write_json as write_shadow_json
from shadow_ledger import init_ledger, read_ledger
from shadow_quality_audit import audit_shadow_ledger, write_html as write_quality_html, write_json as write_quality_json


VALID_PHASES = {"pre_match", "near_close", "post_match", "full_day"}


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


def _normalise_phase(phase: str) -> str:
    value = str(phase or "full_day").strip().lower()
    if value not in VALID_PHASES:
        raise ValueError("Phase invalide. Valeurs: pre_match, near_close, post_match, full_day")
    return value


def validate_pack(pack: str, write_status: bool = False) -> Dict[str, Any]:
    target = _pack(pack)
    required = ["matchday_manual_odds.csv", "matchday_near_close.csv", "matchday_results.csv"]
    missing = [name for name in required if not (target / name).exists()]
    status = pack_status(pack, write=write_status)
    return {"pack": pack, "missing": missing, "valid": not missing, "status": status}


def _rows_from_manual(path: Path, near_close: bool) -> List[Dict[str, Any]]:
    rows = normalize_manual_csv(str(path))
    wanted = "True" if near_close else "False"
    return [row for row in rows if str(row.get("is_near_close") or "") == wanted and row.get("validation_status") == "valid"]


def _read_results_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _valid_results_count(path: Path) -> int:
    count = 0
    for row in _read_results_rows(path):
        result = str(row.get("result") or "").strip().lower()
        if result in VALID_RESULTS and result != "unknown":
            count += 1
    return count


def phase_next_actions(pack: str, phase: str, phase_status: str) -> List[str]:
    phase = _normalise_phase(phase)
    if phase == "pre_match":
        return [
            "Attendre la periode proche du coup d'envoi.",
            "Remplir matchday_near_close.csv avec une cote near-close reelle.",
            f"python matchday_runner.py --pack {pack} --full-dry-run --phase near_close",
            f"python matchday_runner.py --pack {pack} --import-near-close --apply",
        ]
    if phase == "near_close":
        if str(phase_status or "").startswith("blocked"):
            return [
                "Remplir matchday_near_close.csv avec une cote near-close reelle.",
                f"python matchday_runner.py --pack {pack} --full-dry-run --phase near_close",
                "Appliquer import-near-close seulement apres dry-run propre.",
            ]
        return [
            f"python matchday_runner.py --pack {pack} --import-near-close --apply",
            f"python matchday_runner.py --pack {pack} --match-closing --apply",
            "Attendre le resultat final.",
            "Remplir matchday_results.csv.",
            f"python matchday_runner.py --pack {pack} --full-dry-run --phase post_match",
        ]
    if phase == "post_match":
        if str(phase_status or "").startswith("blocked"):
            return [
                "Completer les near-close et resultats manquants.",
                f"python matchday_runner.py --pack {pack} --full-dry-run --phase post_match",
                "Importer les resultats seulement apres dry-run propre.",
            ]
        return [
            f"python matchday_runner.py --pack {pack} --import-results --apply",
            f"python matchday_runner.py --pack {pack} --report",
            "Relire evidence_gate.py.",
            "Continuer la collecte sans conclure avant sample significatif.",
        ]
    return [
        f"python matchday_status_report.py --pack {pack} --output reports/matchday_status.json --html reports/matchday_status.html",
        f"python matchday_runner.py --pack {pack} --full-dry-run --phase pre_match",
        "Suivre la phase qui correspond au moment de la journee.",
    ]


def phase_report(pack: str, phase: str = "full_day") -> Dict[str, Any]:
    phase = _normalise_phase(phase)
    target = _pack(pack)
    status = pack_status(pack, write=False)
    taken_rows = _rows_from_manual(target / "matchday_manual_odds.csv", near_close=False) if (target / "matchday_manual_odds.csv").exists() else []
    near_rows = _rows_from_manual(target / "matchday_near_close.csv", near_close=True) if (target / "matchday_near_close.csv").exists() else []
    result_rows = _valid_results_count(target / "matchday_results.csv")
    warnings: List[str] = []
    blockers: List[str] = []
    if not taken_rows:
        if phase in {"pre_match", "near_close", "post_match"}:
            blockers.append("aucune taken odds valide")
        else:
            warnings.append("aucune taken odds valide")
    if not near_rows:
        if phase == "pre_match":
            warnings.append("Phase pre_match: near-close a remplir plus tard.")
        elif phase in {"near_close", "post_match"}:
            blockers.append("near-close absente pour cette phase")
        else:
            warnings.append("near-close absente ou pas encore renseignee")
    if not result_rows:
        if phase == "post_match":
            blockers.append("resultats absents pour cette phase")
        elif phase in {"pre_match", "near_close"}:
            warnings.append(f"Phase {phase}: resultats a remplir plus tard.")
        else:
            warnings.append("resultats absents ou pas encore renseignes")
    if phase == "pre_match":
        phase_status = "ready_pre_match" if taken_rows and not blockers else "blocked_pre_match"
    elif phase == "near_close":
        phase_status = "ready_near_close" if taken_rows and near_rows and not blockers else "blocked_near_close"
    elif phase == "post_match":
        phase_status = "ready_post_match" if taken_rows and near_rows and result_rows and not blockers else "blocked_post_match"
    else:
        if taken_rows and near_rows and result_rows:
            phase_status = "full_day_complete"
        elif taken_rows:
            phase_status = "full_day_partial"
        else:
            phase_status = "full_day_empty"
    return {
        "phase": phase,
        "phase_status": phase_status,
        "phase_blockers": blockers,
        "phase_warnings": warnings,
        "valid_taken_rows": len(taken_rows),
        "valid_near_close_rows": len(near_rows),
        "valid_result_rows": result_rows,
        "pack_status": status,
        "next_actions": phase_next_actions(pack, phase, phase_status),
        "lab_only": True,
        "can_influence_picks": False,
    }


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


def _write_staged_results(pack: str, staged_ledger: str, output: str) -> int:
    source = _pack(pack) / "matchday_results.csv"
    rows = _read_results_rows(source)
    if not rows:
        return 0
    ledger_rows = read_ledger(staged_ledger)
    shadow_ids = [row.get("shadow_id") for row in ledger_rows if row.get("shadow_id")]
    patched = []
    filled = 0
    for idx, row in enumerate(rows):
        item = dict(row)
        if not str(item.get("shadow_id") or "").strip() and idx < len(shadow_ids):
            item["shadow_id"] = shadow_ids[idx]
        if str(item.get("result") or "").strip().lower() in VALID_RESULTS:
            filled += 1
        patched.append(item)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["shadow_id", "result", "notes"])
        writer.writeheader()
        for row in patched:
            writer.writerow({column: row.get(column, "") for column in ["shadow_id", "result", "notes"]})
    return filled


def _prepare_stage_file(real_path: str, temp_path: Path, include_existing_state: bool, init_func) -> None:
    if include_existing_state and Path(real_path).exists():
        shutil.copy2(real_path, temp_path)
    else:
        init_func(str(temp_path))


def write_matchday_report(pack: str, ledger: str, store: str, reports_dir: str, phase: str = "full_day") -> Dict[str, Any]:
    reports = _safe_reports(reports_dir)
    status = pack_status(pack, write=True)
    phase_info = phase_report(pack, phase)
    guard = build_guard_report(ledger, store, phase=phase)
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
    summary = {
        "matchday_status": status,
        "phase": phase_info,
        "guard": guard,
        "shadow": shadow,
        "quality": quality,
        "intake": intake,
        "evidence": evidence,
    }
    (reports / "matchday_runner_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def full_dry_run(
    pack: str,
    ledger: str,
    store: str,
    reports_dir: str,
    phase: str = "full_day",
    include_existing_state: bool = False,
) -> Dict[str, Any]:
    phase = _normalise_phase(phase)
    with tempfile.TemporaryDirectory(prefix="oracle_matchday_stage_") as tmp:
        stage = Path(tmp)
        staged_store = stage / "odds_snapshots.csv"
        staged_ledger = stage / "shadow_ledger.csv"
        _prepare_stage_file(store, staged_store, include_existing_state, init_store)
        _prepare_stage_file(ledger, staged_ledger, include_existing_state, init_ledger)
        taken = import_taken(pack, str(staged_store), apply=True)
        shadow = to_shadow(str(staged_store), str(staged_ledger), apply=True)
        near = import_near_close(pack, str(staged_store), apply=True)
        closing = match_closing(str(staged_store), str(staged_ledger), apply=True)
        staged_results_csv = stage / "matchday_results.csv"
        staged_result_rows = _write_staged_results(pack, str(staged_ledger), str(staged_results_csv))
        if staged_result_rows:
            results = import_manual_results(str(staged_ledger), str(staged_results_csv), dry_run=False)
        else:
            results = {"dry_run": False, "rows_updated": 0, "errors": [], "result_counts": {}, "lab_only": True}
        staged_store_rows = len(load_snapshots(str(staged_store)))
        staged_ledger_rows = len(read_ledger(str(staged_ledger)))
        phase_info = phase_report(pack, phase)
        stage_warnings = list(phase_info.get("phase_warnings") or [])
        if shadow.get("rows_added", 0) == 0 and taken.get("valid_taken_rows", 0):
            stage_warnings.append("taken valide detectee mais aucune observation shadow simulee")
        return {
            "validate": validate_pack(pack, write_status=False),
            "phase": phase_info,
            "import_taken": taken,
            "to_shadow": shadow,
            "import_near_close": near,
            "match_closing": closing,
            "import_results": results,
            "staged_store_rows": staged_store_rows,
            "staged_ledger_rows": staged_ledger_rows,
            "staged_taken_imported": taken.get("store_report", {}).get("appended_rows", 0),
            "staged_shadow_created": shadow.get("rows_added", 0),
            "staged_near_close_imported": near.get("store_report", {}).get("appended_rows", 0),
            "staged_closing_matched": closing.get("matches_found", 0),
            "staged_results_imported": results.get("rows_updated", 0),
            "stage_warnings": stage_warnings,
            "next_action": (phase_info.get("next_actions") or ["Continuer la collecte shadow."])[0],
            "next_actions": phase_info.get("next_actions") or [],
            "report_dir": reports_dir,
            "dry_run": True,
            "include_existing_state": include_existing_state,
            "lab_only": True,
            "can_influence_picks": False,
        }


def full_apply(pack: str, ledger: str, store: str, reports_dir: str, phase: str = "full_day") -> Dict[str, Any]:
    phase = _normalise_phase(phase)
    guard = build_guard_report(ledger, store, phase=phase)
    if guard.get("verdict") in {"mixed_test_and_real", "invalid"}:
        return {"applied": False, "error": "guard refuse l'application", "guard": guard}
    return {
        "applied": True,
        "phase": phase_report(pack, phase),
        "import_taken": import_taken(pack, store, apply=True),
        "to_shadow": to_shadow(store, ledger, apply=True),
        "import_near_close": import_near_close(pack, store, apply=True),
        "match_closing": match_closing(store, ledger, apply=True),
        "import_results": import_results(pack, ledger, apply=True),
        "report": write_matchday_report(pack, ledger, store, reports_dir, phase=phase),
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
    group.add_argument("--phase-status", action="store_true")
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
    parser.add_argument("--phase", default="full_day", choices=sorted(VALID_PHASES))
    parser.add_argument("--include-existing-state", action="store_true")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.validate:
            payload = validate_pack(args.pack, write_status=True)
        elif args.phase_status:
            payload = phase_report(args.pack, args.phase)
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
            payload = write_matchday_report(args.pack, args.ledger, args.store, args.reports_dir, phase=args.phase)
        elif args.full_apply:
            payload = full_apply(args.pack, args.ledger, args.store, args.reports_dir, phase=args.phase)
        else:
            payload = full_dry_run(
                args.pack,
                args.ledger,
                args.store,
                args.reports_dir,
                phase=args.phase,
                include_existing_state=args.include_existing_state,
            )
        print_json("Matchday runner Oracle", payload)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
