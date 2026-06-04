import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from shadow_ledger import read_ledger, write_ledger
from team_name_normalizer import normalize_team_name


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Les sorties result matcher doivent rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _match_key(row: Dict[str, Any]) -> Tuple[str, str, str, str]:
    league = str(row.get("league") or "")
    return (
        _norm(row.get("match_date") or row.get("date")),
        _norm(league),
        normalize_team_name(row.get("home_team") or "", league=league).lower(),
        normalize_team_name(row.get("away_team") or "", league=league).lower(),
    )


def _result_for_side(side: str, home_goals: int, away_goals: int) -> str:
    if home_goals == away_goals:
        outcome = "draw"
    elif home_goals > away_goals:
        outcome = "home"
    else:
        outcome = "away"
    if side == outcome:
        return "win"
    if side in {"home", "away", "draw"}:
        return "loss"
    return "unknown"


def _load_results(path: str) -> List[Dict[str, str]]:
    if not Path(path).exists():
        return []
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def match_results(ledger_path: str, results_csv: str, overwrite: bool = False, dry_run: bool = False) -> Dict[str, Any]:
    ledger_rows = read_ledger(ledger_path)
    results = [row for row in _load_results(results_csv) if str(row.get("is_finished") or "").lower() == "true"]
    grouped: Dict[Tuple[str, str, str, str], List[Dict[str, str]]] = {}
    for row in results:
        grouped.setdefault(_match_key(row), []).append(row)
    updated = 0
    matched = 0
    unmatched = 0
    ambiguous = 0
    errors: List[str] = []
    preview: List[Dict[str, Any]] = []
    for row in ledger_rows:
        if row.get("result") not in {"", "unknown"} and not overwrite:
            continue
        candidates = grouped.get(_match_key(row), [])
        if not candidates:
            unmatched += 1
            continue
        if len(candidates) > 1:
            ambiguous += 1
            continue
        candidate = candidates[0]
        try:
            hg = int(float(candidate.get("home_goals") or ""))
            ag = int(float(candidate.get("away_goals") or ""))
        except Exception as exc:
            errors.append(f"{row.get('shadow_id')}: score invalide ({exc})")
            continue
        result = _result_for_side(str(row.get("side") or "").lower(), hg, ag)
        matched += 1
        preview.append({"shadow_id": row.get("shadow_id"), "result": result, "score": f"{hg}-{ag}"})
        if not dry_run:
            row["result"] = result
            row["status"] = "settled" if result in {"win", "loss", "push", "void"} else row.get("status", "")
            updated += 1
    if not dry_run:
        write_ledger(ledger_rows, ledger_path)
    return {
        "ledger": ledger_path,
        "results_csv": results_csv,
        "ledger_rows": len(ledger_rows),
        "finished_results": len(results),
        "matched": matched,
        "updated": updated,
        "unmatched": unmatched,
        "ambiguous": ambiguous,
        "errors": errors,
        "dry_run": dry_run,
        "preview": preview[:30],
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Matcher resultats shadow")
    print(f"- Lignes ledger: {report.get('ledger_rows')}")
    print(f"- Resultats termines: {report.get('finished_results')}")
    print(f"- Matchs trouves: {report.get('matched')}")
    print(f"- Mises a jour: {report.get('updated')}")
    print("- Resultats manuels ou API seulement, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Associe des resultats normalises au shadow ledger.")
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--summary-json", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = match_results(args.ledger, args.results, overwrite=args.overwrite, dry_run=args.dry_run)
        if args.summary_json:
            write_json(report, args.summary_json)
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
