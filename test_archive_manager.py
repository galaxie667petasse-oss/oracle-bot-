import argparse
import csv
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from manual_odds_import import write_template as write_manual_odds_template
from odds_snapshot_store import init_store
from shadow_ledger import init_ledger
from shadow_templates import create_closing_template, create_results_template


ARCHIVE_NAMES = [
    "shadow_ledger.csv",
    "odds_snapshots.csv",
    "shadow_clv_report.json",
    "shadow_clv_report.html",
    "evidence_gate.json",
    "evidence_gate.html",
    "shadow_quality_audit.json",
    "shadow_quality_audit.html",
    "odds_intake_audit.json",
    "odds_intake_audit.html",
    "manual_results_import_template.csv",
]
TEMPLATE_NAMES = ["manual_odds_snapshot_template.csv", "manual_closing_import_template.csv"]
TEST_MARKERS = ["test", "demo", "fictif", "simulation", "synthetic"]


def _reports_dir(path: str = "reports") -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("L'archive de tests doit rester hors data/.")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _contains_test_markers(rows: List[Dict[str, str]]) -> bool:
    text = json.dumps(rows, ensure_ascii=False).lower()
    return any(marker in text for marker in TEST_MARKERS)


def status(reports_dir: str = "reports") -> Dict[str, Any]:
    reports = _reports_dir(reports_dir)
    ledger = reports / "shadow_ledger.csv"
    snapshots = reports / "odds_snapshots.csv"
    ledger_rows = _read_csv_rows(ledger)
    snapshot_rows = _read_csv_rows(snapshots)
    marker_found = _contains_test_markers(ledger_rows) or _contains_test_markers(snapshot_rows)
    existing_reports = [name for name in ARCHIVE_NAMES + TEMPLATE_NAMES if (reports / name).exists()]
    workspace_kind = "test" if marker_found else ("reel_possible" if ledger_rows or snapshot_rows else "vide")
    return {
        "reports_dir": str(reports),
        "ledger_exists": ledger.exists(),
        "snapshots_exists": snapshots.exists(),
        "ledger_rows": len(ledger_rows),
        "snapshot_rows": len(snapshot_rows),
        "test_markers_detected": marker_found,
        "existing_reports": existing_reports,
        "workspace_kind": workspace_kind,
        "ready_for_real_collection": workspace_kind in {"vide", "reel_possible"} and not marker_found,
    }


def list_archives(reports_dir: str = "reports") -> Dict[str, Any]:
    reports = _reports_dir(reports_dir)
    archives = sorted(path.name for path in reports.glob("test_archive_*") if path.is_dir())
    return {"reports_dir": str(reports), "archives": archives, "count": len(archives)}


def archive_current(reports_dir: str = "reports", label: str = "archive", include_templates: bool = False) -> Dict[str, Any]:
    reports = _reports_dir(reports_dir)
    safe_label = "".join(ch for ch in label if ch.isalnum() or ch in {"_", "-"}).strip("_") or "archive"
    archive = reports / f"test_archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_label}"
    archive.mkdir(parents=True, exist_ok=True)
    moved = []
    names = list(ARCHIVE_NAMES)
    if include_templates:
        names.extend(TEMPLATE_NAMES)
    for name in names:
        source = reports / name
        if source.exists():
            shutil.move(str(source), str(archive / name))
            moved.append(name)
    return {"archive_dir": str(archive), "moved": moved, "include_templates": include_templates}


def reset_live(reports_dir: str = "reports") -> Dict[str, Any]:
    reports = _reports_dir(reports_dir)
    ledger = init_ledger(str(reports / "shadow_ledger.csv"))
    store = init_store(str(reports / "odds_snapshots.csv"))
    manual_template = write_manual_odds_template(str(reports / "manual_odds_snapshot_template.csv"))
    closing_template = create_closing_template(str(reports / "manual_closing_import_template.csv"), ledger=str(ledger), force=True)
    results_template = create_results_template(str(reports / "manual_results_import_template.csv"), ledger=str(ledger), force=True)
    return {
        "reports_dir": str(reports),
        "ledger": str(ledger),
        "odds_snapshots": str(store),
        "templates": [str(manual_template), str(closing_template), str(results_template)],
        "message": "Pret pour observations reelles.",
    }


def archive_and_reset(reports_dir: str = "reports", label: str = "before_real", include_templates: bool = False) -> Dict[str, Any]:
    return {"archive": archive_current(reports_dir, label, include_templates), "reset": reset_live(reports_dir)}


def print_json(title: str, payload: Dict[str, Any]) -> None:
    print(title)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("- Observation seulement, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Archive les fichiers test/demo de reports avant une collecte reelle.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--status", action="store_true")
    group.add_argument("--archive-current", action="store_true")
    group.add_argument("--reset-live", action="store_true")
    group.add_argument("--archive-and-reset", action="store_true")
    group.add_argument("--list-archives", action="store_true")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--label", default="archive")
    parser.add_argument("--include-templates", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.archive_current:
            print_json("Archive tests Oracle", archive_current(args.reports_dir, args.label, args.include_templates))
        elif args.reset_live:
            print_json("Reset live Oracle", reset_live(args.reports_dir))
        elif args.archive_and_reset:
            print_json("Archive et reset Oracle", archive_and_reset(args.reports_dir, args.label, args.include_templates))
        elif args.list_archives:
            print_json("Archives tests Oracle", list_archives(args.reports_dir))
        else:
            print_json("Status archive tests Oracle", status(args.reports_dir))
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
