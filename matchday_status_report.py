import argparse
import csv
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from manual_odds_import import MANUAL_COLUMNS, normalize_manual_csv, split_rows
from matchday_pack import RESULT_COLUMNS, pack_status
from matchday_runner import phase_next_actions


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le rapport matchday status doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _manual_file_report(path: Path, near_close: bool) -> Dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "rows": 0,
            "valid_rows": 0,
            "rejected_rows": 0,
            "missing_fields": ["fichier absent"],
            "rejection_reasons": {},
        }
    rows = normalize_manual_csv(str(path))
    split = split_rows(rows)
    wanted = "True" if near_close else "False"
    valid_rows = [row for row in split["valid"] if str(row.get("is_near_close") or "") == wanted]
    rejection_reasons: Dict[str, int] = {}
    missing_fields: List[str] = []
    raw_rows = _read_csv(path)
    for raw in raw_rows:
        for column in MANUAL_COLUMNS:
            if column not in raw:
                missing_fields.append(column)
    for row in split["rejected"]:
        reason = row.get("validation_reason") or "inconnu"
        rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
    return {
        "exists": True,
        "rows": len(rows),
        "valid_rows": len(valid_rows),
        "rejected_rows": len(split["rejected"]),
        "missing_fields": sorted(set(missing_fields)),
        "rejection_reasons": rejection_reasons,
    }


def _results_file_report(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"exists": False, "rows": 0, "valid_rows": 0, "missing_fields": ["fichier absent"], "rejected_rows": 0}
    rows = _read_csv(path)
    missing_fields = []
    valid = 0
    rejected = 0
    for row in rows:
        for column in RESULT_COLUMNS:
            if column not in row:
                missing_fields.append(column)
        result = str(row.get("result") or "").strip().lower()
        if result in {"win", "loss", "push", "void"}:
            valid += 1
        elif any(str(row.get(column) or "").strip() for column in RESULT_COLUMNS):
            rejected += 1
    return {
        "exists": True,
        "rows": len(rows),
        "valid_rows": valid,
        "rejected_rows": rejected,
        "missing_fields": sorted(set(missing_fields)),
    }


def _detect_phase(taken: Dict[str, Any], near: Dict[str, Any], results: Dict[str, Any], blockers: List[str]) -> str:
    if blockers:
        return "invalid"
    taken_count = taken.get("valid_rows", 0)
    near_count = near.get("valid_rows", 0)
    result_count = results.get("valid_rows", 0)
    if not taken_count and not near_count and not result_count:
        return "empty"
    if taken_count and not near_count:
        return "pre_match_ready"
    if taken_count and near_count and not result_count:
        return "near_close_ready"
    if taken_count and near_count and result_count:
        return "complete"
    if near_count and not taken_count:
        return "invalid"
    return "waiting_near_close"


def _next_actions(pack: str, detected: str) -> List[str]:
    if detected in {"empty", "pre_match_ready", "waiting_near_close"}:
        return phase_next_actions(pack, "pre_match", detected)
    if detected in {"near_close_ready", "waiting_results"}:
        return phase_next_actions(pack, "near_close", detected)
    if detected in {"post_match_ready", "complete"}:
        return phase_next_actions(pack, "post_match", detected)
    return [
        "Corriger les champs manquants ou les lignes invalides.",
        f"python matchday_status_report.py --pack {pack}",
    ]


def build_status_report(pack: str) -> Dict[str, Any]:
    target = Path(pack)
    status = pack_status(pack, write=False)
    taken = _manual_file_report(target / "matchday_manual_odds.csv", near_close=False)
    near = _manual_file_report(target / "matchday_near_close.csv", near_close=True)
    results = _results_file_report(target / "matchday_results.csv")
    warnings: List[str] = []
    blockers: List[str] = []
    for name, report in [("taken", taken), ("near-close", near), ("results", results)]:
        if not report.get("exists"):
            blockers.append(f"{name}: fichier absent")
        if report.get("rejected_rows"):
            warnings.append(f"{name}: {report.get('rejected_rows')} ligne(s) rejetee(s)")
        if report.get("missing_fields"):
            blockers.append(f"{name}: champs manquants {', '.join(report.get('missing_fields') or [])}")
    if taken.get("valid_rows", 0) and not near.get("valid_rows", 0):
        warnings.append("pre_match probable: near-close a collecter plus tard")
    if taken.get("valid_rows", 0) and near.get("valid_rows", 0) and not results.get("valid_rows", 0):
        warnings.append("near_close probable: resultats a collecter apres match")
    detected = _detect_phase(taken, near, results, blockers)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "pack_dir": str(target),
        "date": status.get("date"),
        "phase_detected": detected,
        "taken": {**status.get("taken", {}), **taken},
        "near_close": {**status.get("near_close", {}), **near},
        "results": {**status.get("results", {}), **results},
        "warnings": warnings,
        "blockers": blockers,
        "next_actions": _next_actions(pack, detected),
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Matchday Status</title></head><body><h1>Matchday Status</h1><pre>"
        + html.escape(json.dumps(report, ensure_ascii=False, indent=2))
        + "</pre></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Matchday status Oracle")
    print(f"- Pack: {report.get('pack_dir')}")
    print(f"- Phase detectee: {report.get('phase_detected')}")
    print(f"- Taken valides: {(report.get('taken') or {}).get('valid_rows')}")
    print(f"- Near-close valides: {(report.get('near_close') or {}).get('valid_rows')}")
    print(f"- Resultats valides: {(report.get('results') or {}).get('valid_rows')}")
    for item in report.get("warnings") or []:
        print(f"- Warning: {item}")
    for item in report.get("blockers") or []:
        print(f"- Bloquant: {item}")
    for item in report.get("next_actions") or []:
        print(f"- Action: {item}")
    print("- Observation seulement, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Rapport de statut d'un pack matchday.")
    parser.add_argument("--pack", required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = build_status_report(args.pack)
        if args.output:
            write_json(report, args.output)
        if args.html:
            write_html(report, args.html)
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
