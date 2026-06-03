import argparse
import csv
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from odds_snapshot_store import load_snapshots
from shadow_ledger import read_ledger


TEST_MARKERS = ["test", "demo", "fictif", "simulation", "synthetic"]


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le rapport guard doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _contains_marker(row: Dict[str, Any]) -> bool:
    text = json.dumps(row, ensure_ascii=False).lower()
    return any(marker in text for marker in TEST_MARKERS)


def _key(row: Dict[str, Any]) -> Tuple[str, ...]:
    return (
        str(row.get("match_date") or "").strip().lower(),
        str(row.get("league") or "").strip().lower(),
        str(row.get("normalized_home") or row.get("home_team") or "").strip().lower(),
        str(row.get("normalized_away") or row.get("away_team") or "").strip().lower(),
        str(row.get("market_type") or "").strip().lower(),
        str(row.get("side") or "").strip().lower(),
    )


def _parse_dt(value: str):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        try:
            return datetime.fromisoformat(text[:10])
        except Exception:
            return None


def _minutes_before(row: Dict[str, Any]) -> float | None:
    captured = _parse_dt(str(row.get("captured_at") or ""))
    kickoff = _parse_dt(str(row.get("kickoff_time") or ""))
    if not captured or not kickoff:
        return None
    try:
        return (kickoff - captured).total_seconds() / 60.0
    except Exception:
        return None


def build_guard_report(
    ledger: str = "reports/shadow_ledger.csv",
    snapshots: str = "reports/odds_snapshots.csv",
    max_near_close_minutes: int = 30,
    phase: str = "full_day",
    scope: str = "ledger",
) -> Dict[str, Any]:
    phase = str(phase or "full_day").strip().lower()
    if phase not in {"pre_match", "near_close", "post_match", "full_day"}:
        raise ValueError("phase invalide: pre_match, near_close, post_match, full_day")
    scope = str(scope or "ledger").strip().lower()
    if scope not in {"ledger", "snapshots", "both"}:
        raise ValueError("scope invalide: ledger, snapshots, both")
    ledger_rows = read_ledger(ledger)
    snapshot_rows = load_snapshots(snapshots)
    warnings: List[str] = []
    blockers: List[str] = []
    test_rows = []
    real_rows = []
    sources = []
    if scope in {"ledger", "both"}:
        sources.append(("ledger", ledger_rows))
    if scope in {"snapshots", "both"}:
        sources.append(("snapshots", snapshot_rows))
    for source_name, rows in sources:
        for idx, row in enumerate(rows, start=2):
            source = str(row.get("source") or "").lower()
            if source == "demo" or _contains_marker(row):
                test_rows.append({"source": source_name, "line": idx, "row": row})
            else:
                real_rows.append({"source": source_name, "line": idx, "row": row})
            if source_name == "snapshots":
                if str(row.get("bookmaker") or "").strip().lower() == "manual" and not str(row.get("raw_payload_ref") or row.get("notes") or "").strip():
                    warnings.append(f"ligne snapshot {idx}: bookmaker manual avec notes vides")
                if not str(row.get("captured_at") or "").strip():
                    blockers.append(f"ligne snapshot {idx}: captured_at absent")
                if not str(row.get("bookmaker") or "").strip():
                    blockers.append(f"ligne snapshot {idx}: bookmaker absent")
                if not str(row.get("league") or "").strip():
                    warnings.append(f"ligne snapshot {idx}: league absente")
                if str(row.get("is_near_close") or "").lower() == "true":
                    minutes = _minutes_before(row)
                    if minutes is not None and abs(minutes) > max_near_close_minutes:
                        warnings.append(f"ligne snapshot {idx}: near-close eloigne du kickoff ({round(minutes, 1)} min)")
    near_without_taken = []
    taken_without_near = []
    if scope in {"snapshots", "both"}:
        usable = [row for row in snapshot_rows if row.get("validation_status") in {"", "valid", None}]
        taken_keys = {_key(row) for row in usable if str(row.get("is_near_close") or "").lower() != "true"}
        close_keys = {_key(row) for row in usable if str(row.get("is_near_close") or "").lower() == "true"}
        near_without_taken = sorted(close_keys - taken_keys)
        taken_without_near = sorted(taken_keys - close_keys)
    if scope in {"ledger", "both"}:
        ledger_missing_close = sorted(_key(row) for row in ledger_rows if not str(row.get("closing_odds") or "").strip())
        # En scope ledger, seules les observations shadow selectionnees comptent.
        if scope == "ledger":
            taken_without_near = ledger_missing_close
        else:
            taken_without_near = sorted(set(taken_without_near) | set(ledger_missing_close))
    if near_without_taken:
        blockers.append("near-close sans taken correspondant")
    if taken_without_near:
        if phase in {"near_close", "post_match"}:
            blockers.append("taken sans near-close correspondant")
        else:
            warnings.append("taken sans near-close correspondant")
    missing_results = [
        row for row in ledger_rows
        if str(row.get("result") or "unknown").strip().lower() == "unknown"
    ]
    if phase == "post_match" and ledger_rows and missing_results:
        blockers.append("resultats manquants en phase post_match")
    odds_values = [str(row.get("odds") or "").strip() for row in snapshot_rows if str(row.get("odds") or "").strip()]
    if len(odds_values) >= 5 and len(set(odds_values)) == 1:
        warnings.append("cotes identiques partout, verification humaine requise")
    ledger_fictive_results = [row for row in ledger_rows if _contains_marker(row) and str(row.get("result") or "").lower() in {"win", "loss", "push", "void"}]
    if ledger_fictive_results:
        blockers.append("ledger avec resultats fictifs")
    if not ledger_rows and (scope == "ledger" or not snapshot_rows):
        verdict = "empty"
    elif test_rows and real_rows:
        verdict = "mixed_test_and_real"
    elif blockers:
        verdict = "invalid"
    elif warnings or test_rows:
        verdict = "needs_review"
    else:
        verdict = "clean_real_collection"
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "phase": phase,
        "scope": scope,
        "ledger": ledger,
        "snapshots": snapshots,
        "ledger_rows": len(ledger_rows),
        "snapshot_rows": len(snapshot_rows),
        "test_like_rows": len(test_rows),
        "real_like_rows": len(real_rows),
        "near_close_without_taken_count": len(near_without_taken),
        "taken_without_near_close_count": len(taken_without_near),
        "missing_results_count": len(missing_results),
        "near_close_without_taken": ["|".join(item) for item in near_without_taken[:20]],
        "taken_without_near_close": ["|".join(item) for item in taken_without_near[:20]],
        "warnings": warnings,
        "blockers": blockers,
        "verdict": verdict,
        "lab_only": True,
        "can_influence_picks": False,
    }


def check_notes(csv_path: str) -> Dict[str, Any]:
    path = Path(csv_path)
    if not path.exists():
        return {"path": csv_path, "exists": False, "markers": []}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = [dict(row) for row in csv.DictReader(fh)]
    markers = []
    for idx, row in enumerate(rows, start=2):
        if _contains_marker(row):
            markers.append({"line": idx, "row": row})
    return {"path": csv_path, "exists": True, "rows": len(rows), "markers": markers, "marker_count": len(markers)}


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Real Observation Guard</title></head><body><h1>Real Observation Guard</h1><pre>"
        + html.escape(json.dumps(report, ensure_ascii=False, indent=2))
        + "</pre></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Real Observation Guard Oracle")
    print(f"- Verdict: {report.get('verdict')}")
    print(f"- Phase: {report.get('phase') or 'n/a'}")
    print(f"- Scope: {report.get('scope') or 'n/a'}")
    print(f"- Lignes ledger: {report.get('ledger_rows')}")
    print(f"- Lignes snapshots: {report.get('snapshot_rows')}")
    print(f"- Near-close sans taken: {report.get('near_close_without_taken_count')}")
    print(f"- Taken sans near-close: {report.get('taken_without_near_close_count')}")
    for item in report.get("blockers") or []:
        print(f"- Bloquant: {item}")
    for item in report.get("warnings") or []:
        print(f"- Warning: {item}")
    print("- Observation seulement, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Controle le melange test/demo/reel dans les observations.")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--snapshots", default="reports/odds_snapshots.csv")
    parser.add_argument("--check-notes", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    parser.add_argument("--max-near-close-minutes", type=int, default=30)
    parser.add_argument("--phase", default="full_day", choices=["pre_match", "near_close", "post_match", "full_day"])
    parser.add_argument("--scope", default="ledger", choices=["ledger", "snapshots", "both"])
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.check_notes:
            report = check_notes(args.check_notes)
        else:
            report = build_guard_report(args.ledger, args.snapshots, args.max_near_close_minutes, phase=args.phase, scope=args.scope)
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
