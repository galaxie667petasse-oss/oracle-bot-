import argparse
import csv
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_PROGRESS = "reports/progress_loop.csv"
FIELDNAMES = ["entry_id", "created_at", "phase", "title", "status", "related_file", "related_report", "issue", "fix", "notes"]
VALID_PHASES = {"collecter", "tester", "mesurer", "corriger", "documenter"}
VALID_STATUSES = {"todo", "doing", "done", "blocked", "skipped"}


def _guard_reports(path: str) -> None:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le journal de progression ne doit pas etre ecrit dans data/.")


def init_progress(path: str = DEFAULT_PROGRESS) -> Path:
    _guard_reports(path)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        with target.open("w", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, fieldnames=FIELDNAMES).writeheader()
    return target


def load_entries(path: str = DEFAULT_PROGRESS) -> List[Dict[str, str]]:
    target = Path(path)
    if not target.exists():
        return []
    with target.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def add_entry(path: str = DEFAULT_PROGRESS, phase: str = "collecter", title: str = "", status: str = "todo", related_file: str = "", related_report: str = "", issue: str = "", fix: str = "", notes: str = "") -> Dict[str, Any]:
    if phase not in VALID_PHASES:
        raise ValueError("phase invalide")
    if status not in VALID_STATUSES:
        raise ValueError("status invalide")
    init_progress(path)
    entries = load_entries(path)
    row = {
        "entry_id": f"pl_{len(entries) + 1:06d}",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "phase": phase,
        "title": title,
        "status": status,
        "related_file": related_file,
        "related_report": related_report,
        "issue": issue,
        "fix": fix,
        "notes": notes,
    }
    with Path(path).open("a", newline="", encoding="utf-8") as fh:
        csv.DictWriter(fh, fieldnames=FIELDNAMES).writerow(row)
    return row


def summarize_progress(path: str = DEFAULT_PROGRESS) -> Dict[str, Any]:
    entries = load_entries(path)
    by_phase = {phase: 0 for phase in sorted(VALID_PHASES)}
    by_status = {status: 0 for status in sorted(VALID_STATUSES)}
    for row in entries:
        if row.get("phase") in by_phase:
            by_phase[row["phase"]] += 1
        if row.get("status") in by_status:
            by_status[row["status"]] += 1
    return {
        "path": path,
        "entries": len(entries),
        "by_phase": by_phase,
        "by_status": by_status,
        "open_items": [row for row in entries if row.get("status") in {"todo", "doing", "blocked"}],
        "lab_only": True,
    }


def write_html(path: str = DEFAULT_PROGRESS, output: str = "reports/progress_loop.html") -> Path:
    _guard_reports(output)
    summary = summarize_progress(path)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Boucle progression</title></head><body><h1>Boucle de progression</h1><pre>"
        + html.escape(json.dumps(summary, ensure_ascii=False, indent=2))
        + "</pre></body></html>",
        encoding="utf-8",
    )
    return target


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Journal local de progression Oracle.")
    parser.add_argument("--path", default=DEFAULT_PROGRESS)
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--add", action="store_true")
    parser.add_argument("--phase", default="collecter")
    parser.add_argument("--title", default="")
    parser.add_argument("--status", default="todo")
    parser.add_argument("--related-file", default="")
    parser.add_argument("--related-report", default="")
    parser.add_argument("--issue", default="")
    parser.add_argument("--fix", default="")
    parser.add_argument("--notes", default="")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.init:
        init_progress(args.path)
        print(f"Journal initialise: {args.path}")
    if args.add:
        row = add_entry(args.path, args.phase, args.title, args.status, args.related_file, args.related_report, args.issue, args.fix, args.notes)
        print("Entree ajoutee")
        print(json.dumps(row, ensure_ascii=False, indent=2))
    if args.summary or not any([args.init, args.add, args.html]):
        print("Resume boucle de progression")
        print(json.dumps(summarize_progress(args.path), ensure_ascii=False, indent=2))
    if args.html:
        write_html(args.path, args.html)
        print(f"HTML progression ecrit: {args.html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
