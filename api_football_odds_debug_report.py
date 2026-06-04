import argparse
import csv
import html
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

from api_football_valid_odds_selector import FINISHED_STATUSES, _extract_status


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le debug odds API-Football doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def load_rows(path: str) -> List[Dict[str, str]]:
    if not Path(path).exists():
        return []
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _counts(values: Iterable[Any], limit: int = 30) -> Dict[str, int]:
    return dict(Counter(str(value or "missing") for value in values).most_common(limit))


def build_debug_report(odds_path: str, max_examples: int = 10) -> Dict[str, Any]:
    rows = load_rows(odds_path)
    valid_rows = [row for row in rows if row.get("validation_status") == "valid"]
    valid_h2h = [row for row in valid_rows if row.get("market_type") == "h2h"]
    selected_candidates = [
        row for row in valid_h2h
        if row.get("side") in {"home", "away"}
        and (_extract_status(row) in {"", "NS", "TBD"})
        and not str(row.get("is_live") or "").lower() == "true"
        and not str(row.get("is_near_close") or "").lower() == "true"
    ]
    selected_ids = {row.get("snapshot_id") for row in selected_candidates}
    rejected = [row for row in rows if row.get("snapshot_id") not in selected_ids]
    status_values = [_extract_status(row) or "missing" for row in rows]
    valid_h2h_by_status: Dict[str, int] = {}
    for row in valid_h2h:
        status = _extract_status(row) or "missing"
        valid_h2h_by_status[status] = valid_h2h_by_status.get(status, 0) + 1
    valid_h2h_by_bookmaker: Dict[str, int] = {}
    for row in valid_h2h:
        bookmaker = row.get("bookmaker") or "missing"
        valid_h2h_by_bookmaker[bookmaker] = valid_h2h_by_bookmaker.get(bookmaker, 0) + 1
    return {
        "input": odds_path,
        "total_rows": len(rows),
        "validation_status_counts": _counts(row.get("validation_status") for row in rows),
        "market_type_counts": _counts(row.get("market_type") for row in rows),
        "side_counts": _counts(row.get("side") for row in rows),
        "bookmaker_counts": _counts(row.get("bookmaker") for row in rows),
        "league_counts": _counts(row.get("league") for row in rows),
        "status_counts": _counts(status_values),
        "valid_h2h_count": len(valid_h2h),
        "valid_h2h_not_finished_count": sum(1 for row in valid_h2h if (_extract_status(row) or "missing") not in FINISHED_STATUSES),
        "valid_h2h_by_status": dict(sorted(valid_h2h_by_status.items(), key=lambda item: item[1], reverse=True)[:30]),
        "valid_h2h_by_bookmaker": dict(sorted(valid_h2h_by_bookmaker.items(), key=lambda item: item[1], reverse=True)[:30]),
        "examples_selected_candidates": selected_candidates[:max_examples],
        "examples_rejected_rows": rejected[:max_examples],
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
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>API-Football odds debug</h1><pre>"
        + html.escape(json.dumps(report, ensure_ascii=False, indent=2))
        + "</pre><p>Diagnostic local, aucune mise.</p></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("API-Football odds debug")
    print(f"- Lignes totales: {report.get('total_rows')}")
    print(f"- H2H valides: {report.get('valid_h2h_count')}")
    print(f"- H2H valides non termines: {report.get('valid_h2h_not_finished_count')}")
    print(f"- Status: {report.get('status_counts')}")
    print("- Diagnostic local, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Rapport debug pour odds API-Football enrichies.")
    parser.add_argument("--odds", required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    parser.add_argument("--max-examples", type=int, default=10)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = build_debug_report(args.odds, max_examples=args.max_examples)
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
