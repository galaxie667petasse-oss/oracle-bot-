import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from shadow_ledger import read_ledger, write_ledger
from team_name_normalizer import normalize_team_name


RESULT_COLUMNS_V98 = [
    "result_status",
    "result_home_goals",
    "result_away_goals",
    "result_winner",
    "result_date",
    "result_source",
    "result_fixture_id",
    "result_captured_at",
    "is_result_final",
    "profit_units",
    "roi_percent",
    "settled_at",
    "settlement_status",
]


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Les sorties result matcher doivent rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _date_only(value: Any) -> str:
    return str(value or "").strip()[:10]


def _match_key(row: Dict[str, Any]) -> Tuple[str, str, str, str]:
    league = str(row.get("league") or "")
    return (
        _norm(_date_only(row.get("match_date") or row.get("date"))),
        _norm(league),
        normalize_team_name(row.get("home_team") or "", league=league).lower(),
        normalize_team_name(row.get("away_team") or "", league=league).lower(),
    )


def _source_event_id(row: Dict[str, Any]) -> str:
    direct = str(row.get("source_event_id") or row.get("fixture_id") or row.get("result_fixture_id") or "").strip()
    if direct:
        return direct
    notes = str(row.get("notes") or "")
    for part in notes.split(";"):
        if "source_event_id=" in part:
            return part.split("source_event_id=", 1)[1].strip()
        if "fixture_id=" in part:
            return part.split("fixture_id=", 1)[1].strip()
    return ""


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "oui", "y"}


def _is_finished(row: Dict[str, Any]) -> bool:
    status = str(row.get("status") or "").strip().upper()
    return _truthy(row.get("is_finished")) or status in {"FT", "AET", "PEN"}


def _to_int(value: Any) -> int:
    return int(float(str(value).strip().replace(",", ".")))


def _float(value: Any):
    try:
        return float(str(value).strip().replace(",", "."))
    except Exception:
        return None


def _fmt_float(value: float, digits: int = 2) -> str:
    return str(round(float(value), digits))


def _winner(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "home"
    if away_goals > home_goals:
        return "away"
    return "draw"


def _result_for_side(market_type: str, side: str, home_goals: int, away_goals: int) -> str:
    market = str(market_type or "").strip().lower()
    side = str(side or "").strip().lower()
    if market != "h2h":
        return "unknown"
    if side == "home":
        if home_goals > away_goals:
            return "win"
        if home_goals < away_goals:
            return "loss"
        return "push"
    if side == "away":
        return "win" if away_goals > home_goals else "loss"
    if side == "draw":
        return "win" if home_goals == away_goals else "loss"
    return "unknown"


def _profit_units(result_status: str, taken_odds: Any):
    odds = _float(taken_odds)
    if odds is None:
        return None
    if result_status == "win":
        return round(odds - 1.0, 6)
    if result_status == "loss":
        return -1.0
    if result_status == "push":
        return 0.0
    return None


def _current_result_status(row: Dict[str, Any]) -> str:
    return str(row.get("result_status") or row.get("result") or "unknown").strip().lower()


def _has_settled_result(row: Dict[str, Any]) -> bool:
    return _current_result_status(row) in {"win", "loss", "push", "void"}


def _load_results(path: str) -> List[Dict[str, str]]:
    if not Path(path).exists():
        return []
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _index_results(results: List[Dict[str, str]]) -> Tuple[Dict[str, List[Dict[str, str]]], Dict[Tuple[str, str, str, str], List[Dict[str, str]]]]:
    by_fixture: Dict[str, List[Dict[str, str]]] = {}
    by_key: Dict[Tuple[str, str, str, str], List[Dict[str, str]]] = {}
    for row in results:
        fixture_id = _source_event_id(row)
        if fixture_id:
            by_fixture.setdefault(fixture_id, []).append(row)
        key = _match_key(row)
        if key[0] and key[2] and key[3]:
            by_key.setdefault(key, []).append(row)
    return by_fixture, by_key


def _candidate_rows(
    ledger_row: Dict[str, Any],
    by_fixture: Dict[str, List[Dict[str, str]]],
    by_key: Dict[Tuple[str, str, str, str], List[Dict[str, str]]],
    strict_fixture_id: bool,
) -> Tuple[List[Dict[str, str]], str]:
    fixture_id = _source_event_id(ledger_row)
    if fixture_id:
        candidates = by_fixture.get(fixture_id, [])
        if candidates or strict_fixture_id:
            return candidates, "fixture_id"
    key = _match_key(ledger_row)
    if not key[0]:
        return [], "date_missing"
    return by_key.get(key, []), "date_teams_league"


def _settlement_update(row: Dict[str, Any], candidate: Dict[str, str], overwritten: bool = False) -> Dict[str, Any]:
    home_goals = _to_int(candidate.get("home_goals"))
    away_goals = _to_int(candidate.get("away_goals"))
    result_status = _result_for_side(str(row.get("market_type") or ""), str(row.get("side") or ""), home_goals, away_goals)
    profit = _profit_units(result_status, row.get("taken_odds"))
    roi = None if profit is None else round(profit * 100.0, 2)
    captured_at = datetime.now().isoformat(timespec="seconds")
    status = "overwritten" if overwritten else "settled"
    update = {
        "result_status": result_status,
        "result_home_goals": str(home_goals),
        "result_away_goals": str(away_goals),
        "result_winner": _winner(home_goals, away_goals),
        "result_date": _date_only(candidate.get("date") or candidate.get("kickoff_time")),
        "result_source": "api_football_results",
        "result_fixture_id": _source_event_id(candidate),
        "result_captured_at": captured_at,
        "is_result_final": "True",
        "profit_units": "" if profit is None else _fmt_float(profit, 6),
        "roi_percent": "" if roi is None else _fmt_float(roi, 2),
        "settled_at": captured_at,
        "settlement_status": status,
        "result": result_status,
        "status": "settled",
        "observation_status": "completed",
    }
    return update


def match_results(
    ledger_path: str,
    results_csv: str,
    overwrite: bool = False,
    dry_run: bool = True,
    apply: bool = False,
    target_shadow_id: str = "",
    strict_fixture_id: bool = True,
) -> Dict[str, Any]:
    ledger_rows = read_ledger(ledger_path)
    results = _load_results(results_csv)
    finished_results = [row for row in results if _is_finished(row)]
    by_fixture, by_key = _index_results(results)
    applied = bool(apply and not dry_run)

    matches_found = 0
    updated = 0
    unmatched = 0
    ambiguous = 0
    already_settled = 0
    skipped_not_finished = 0
    errors: List[str] = []
    updates: List[Dict[str, Any]] = []

    for row in ledger_rows:
        shadow_id = str(row.get("shadow_id") or "")
        if target_shadow_id and shadow_id != target_shadow_id:
            continue
        if _has_settled_result(row) and not overwrite:
            already_settled += 1
            continue

        candidates, match_method = _candidate_rows(row, by_fixture, by_key, strict_fixture_id)
        if not candidates:
            unmatched += 1
            continue
        if len(candidates) > 1:
            ambiguous += 1
            continue
        candidate = candidates[0]
        matches_found += 1
        if not _is_finished(candidate):
            skipped_not_finished += 1
            continue
        try:
            update = _settlement_update(row, candidate, overwritten=_has_settled_result(row))
        except Exception as exc:
            errors.append(f"{shadow_id}: score invalide ({exc})")
            continue

        preview = {
            "shadow_id": shadow_id,
            "match": f"{row.get('home_team') or ''} - {row.get('away_team') or ''}".strip(),
            "score": f"{update['result_home_goals']}-{update['result_away_goals']}",
            "side": row.get("side"),
            "market_type": row.get("market_type"),
            "match_method": match_method,
            "result_status": update["result_status"],
            "profit_units": update["profit_units"],
            "roi_percent": update["roi_percent"],
            "settlement_status": update["settlement_status"],
        }
        updates.append(preview)
        if applied:
            row.update(update)
            updated += 1

    if applied:
        write_ledger(ledger_rows, ledger_path)

    return {
        "ledger": ledger_path,
        "results_csv": results_csv,
        "rows_ledger": len(ledger_rows),
        "results_finished": len(finished_results),
        "matches_found": matches_found,
        "updated": updated,
        "ambiguous": ambiguous,
        "already_settled": already_settled,
        "skipped_not_finished": skipped_not_finished,
        "unmatched": unmatched,
        "applied": applied,
        "overwrite": bool(overwrite),
        "target_shadow_id": target_shadow_id,
        "strict_fixture_id": bool(strict_fixture_id),
        "updates": updates,
        "errors": errors,
        "dry_run": not applied,
        "ledger_rows": len(ledger_rows),
        "finished_results": len(finished_results),
        "matched": matches_found,
        "preview": updates[:30],
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Matcher resultats shadow")
    print(f"- Lignes ledger: {report.get('rows_ledger')}")
    print(f"- Resultats termines: {report.get('results_finished')}")
    print(f"- Matchs trouves: {report.get('matches_found')}")
    print(f"- Mises a jour: {report.get('updated')}")
    print(f"- Ambigus: {report.get('ambiguous')}")
    print(f"- Deja renseignes: {report.get('already_settled')}")
    print(f"- Applied: {str(bool(report.get('applied'))).lower()}")
    for item in report.get("updates") or []:
        print(
            "- Update: "
            f"{item.get('shadow_id')} | {item.get('match')} | score={item.get('score')} | "
            f"side={item.get('side')} | resultat={item.get('result_status')} | "
            f"profit_units={item.get('profit_units')} | roi_percent={item.get('roi_percent')}"
        )
    for error in report.get("errors") or []:
        print(f"- Erreur: {error}")
    print("- Observation uniquement, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Associe des resultats normalises au shadow ledger.")
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--apply", action="store_true", help="Ecrit le settlement dans le ledger")
    parser.add_argument("--dry-run", action="store_true", help="Preview sans ecriture, comportement par defaut")
    parser.add_argument("--overwrite", action="store_true", help="Remplace un resultat existant")
    parser.add_argument("--summary-json", default="")
    parser.add_argument("--target-shadow-id", default="")
    parser.add_argument("--strict-fixture-id", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        effective_dry_run = bool(args.dry_run or not args.apply)
        report = match_results(
            args.ledger,
            args.results,
            overwrite=args.overwrite,
            dry_run=effective_dry_run,
            apply=args.apply,
            target_shadow_id=args.target_shadow_id,
            strict_fixture_id=args.strict_fixture_id,
        )
        if args.summary_json:
            write_json(report, args.summary_json)
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
