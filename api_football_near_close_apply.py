import argparse
import csv
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


V97_LEDGER_COLUMNS = [
    "closing_odds",
    "closing_bookmaker",
    "closing_source",
    "closing_captured_at",
    "closing_fixture_id",
    "closing_quality",
    "clv",
    "clv_pct",
    "closing_status",
]

LEGACY_CLV_COLUMNS = ["clv_percent", "clv_available"]
VALID_CLOSING_QUALITY = {
    "same_bookmaker",
    "cross_bookmaker_same_market",
    "best_available_same_market",
    "manual_unverified",
    "unavailable",
}


def _read_csv(path: str) -> Tuple[List[str], List[Dict[str, str]]]:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"Fichier introuvable: {path}")
    with target.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), [dict(row) for row in reader]


def _safe_ledger_path(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le ledger shadow ne doit pas etre ecrit dans data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _write_ledger(path: str, fieldnames: List[str], rows: Iterable[Dict[str, Any]]) -> Path:
    target = _safe_ledger_path(path)
    materialized = [dict(row) for row in rows]
    columns = list(fieldnames)
    for column in V97_LEDGER_COLUMNS + LEGACY_CLV_COLUMNS:
        if column not in columns:
            columns.append(column)
    for row in materialized:
        for column in row.keys():
            if column not in columns:
                columns.append(column)
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in materialized:
            writer.writerow({column: row.get(column, "") for column in columns})
    return target


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> Optional[float]:
    try:
        number = float(str(value).strip().replace(",", "."))
    except Exception:
        return None
    return number if math.isfinite(number) else None


def _decimal_odds(value: Any) -> Optional[float]:
    number = _float(value)
    if number is None or number <= 1.01 or number > 1000.0:
        return None
    return number


def _extract_from_notes(notes: str, keys: Iterable[str]) -> str:
    for key in keys:
        pattern = rf"(?:^|[;\s]){re.escape(key)}=([^;\s]+)"
        match = re.search(pattern, notes or "")
        if match:
            return match.group(1).strip()
    return ""


def row_fixture_id(row: Dict[str, Any]) -> str:
    for key in ("source_event_id", "fixture_id", "closing_fixture_id", "raw_payload_ref"):
        value = _text(row.get(key))
        if value:
            return value
    return _extract_from_notes(_text(row.get("notes")), ("source_event_id", "fixture_id"))


def _candidate_key(row: Dict[str, Any]) -> Tuple[str, str, str]:
    return (row_fixture_id(row), _norm(row.get("market_type")), _norm(row.get("side")))


def _ledger_candidates(
    ledger_rows: List[Dict[str, str]],
    near_rows: List[Dict[str, str]],
    shadow_id: str = "",
) -> List[Dict[str, str]]:
    valid_event_keys = {_candidate_key(row) for row in near_rows if row_fixture_id(row)}
    if shadow_id:
        selected = [row for row in ledger_rows if _text(row.get("shadow_id")) == shadow_id]
        if not selected:
            return []
        row = selected[0]
        return [row] if _candidate_key(row) in valid_event_keys else []
    candidates = []
    for row in ledger_rows:
        if _candidate_key(row) not in valid_event_keys:
            continue
        candidates.append(row)
    exact = []
    for row in candidates:
        bookmaker = _norm(row.get("bookmaker"))
        if bookmaker and any(
            _candidate_key(row) == _candidate_key(near_row) and _norm(near_row.get("bookmaker")) == bookmaker
            for near_row in near_rows
        ):
            exact.append(row)
    return exact or candidates


def _near_candidates_for_ledger(
    near_rows: List[Dict[str, str]],
    ledger_row: Dict[str, str],
) -> List[Dict[str, str]]:
    event_id = row_fixture_id(ledger_row)
    market = _norm(ledger_row.get("market_type"))
    side = _norm(ledger_row.get("side"))
    candidates = []
    for row in near_rows:
        if row_fixture_id(row) != event_id:
            continue
        if _norm(row.get("market_type")) != market:
            continue
        if _norm(row.get("side")) != side:
            continue
        if _decimal_odds(row.get("odds")) is None:
            continue
        candidates.append(row)
    return candidates


def _select_near_close(
    near_rows: List[Dict[str, str]],
    ledger_row: Dict[str, str],
) -> Tuple[Optional[Dict[str, str]], str, str]:
    candidates = _near_candidates_for_ledger(near_rows, ledger_row)
    if not candidates:
        return None, "unavailable", "missing"
    wanted_bookmaker = _norm(ledger_row.get("bookmaker"))
    exact = [row for row in candidates if _norm(row.get("bookmaker")) == wanted_bookmaker and wanted_bookmaker]
    if len(exact) == 1:
        return exact[0], "same_bookmaker", "captured"
    if len(exact) > 1:
        return None, "unavailable", "ambiguous"
    if len(candidates) == 1:
        bookmaker = _norm(candidates[0].get("bookmaker"))
        quality = "cross_bookmaker_same_market" if bookmaker else "best_available_same_market"
        return candidates[0], quality, "captured"
    return None, "unavailable", "ambiguous"


def _compute_clv_fields(taken_odds: float, closing_odds: float) -> Dict[str, Any]:
    clv = round(closing_odds / taken_odds - 1.0, 8)
    legacy = round(taken_odds / closing_odds - 1.0, 8)
    return {
        "clv": clv,
        "clv_pct": round(clv * 100.0, 4),
        "clv_percent": legacy,
        "clv_available": "True",
    }


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def apply_near_close(
    ledger: str,
    near_close_file: str,
    shadow_id: str = "",
    apply: bool = False,
) -> Dict[str, Any]:
    ledger_fields, ledger_rows = _read_csv(ledger)
    _, near_rows = _read_csv(near_close_file)
    matched_ledger = _ledger_candidates(ledger_rows, near_rows, shadow_id=shadow_id)
    selected_ledger: Optional[Dict[str, str]] = None
    selected_near: Optional[Dict[str, str]] = None
    quality = "unavailable"
    status = "missing"
    candidate_count = 0
    errors: List[str] = []

    if shadow_id and len([row for row in ledger_rows if _text(row.get("shadow_id")) == shadow_id]) > 1:
        status = "ambiguous"
        errors.append(f"shadow_id ambigu dans le ledger: {shadow_id}")
    elif len(matched_ledger) == 1:
        selected_ledger = matched_ledger[0]
        candidates = _near_candidates_for_ledger(near_rows, selected_ledger)
        candidate_count = len(candidates)
        selected_near, quality, status = _select_near_close(near_rows, selected_ledger)
    elif len(matched_ledger) > 1:
        status = "ambiguous"
        candidate_count = sum(len(_near_candidates_for_ledger(near_rows, row)) for row in matched_ledger)
        errors.append("Plusieurs observations ledger correspondent a la near-close.")
    else:
        candidate_count = len([row for row in near_rows if _decimal_odds(row.get("odds")) is not None])
        status = "missing"
        errors.append("Aucune observation ledger compatible trouvee.")

    would_update = 1 if selected_ledger is not None and selected_near is not None and status == "captured" else 0
    updated = 0
    closing_odds = _decimal_odds(selected_near.get("odds")) if selected_near else None
    taken_odds = _decimal_odds(selected_ledger.get("taken_odds")) if selected_ledger else None
    if would_update and (closing_odds is None or taken_odds is None):
        would_update = 0
        status = "missing"
        quality = "unavailable"
        errors.append("Cote prise ou cote closing invalide.")

    if would_update and apply:
        assert selected_ledger is not None and selected_near is not None and closing_odds is not None and taken_odds is not None
        for row in ledger_rows:
            if _text(row.get("shadow_id")) != _text(selected_ledger.get("shadow_id")):
                continue
            row["closing_odds"] = str(closing_odds)
            row["closing_bookmaker"] = _text(selected_near.get("bookmaker"))
            row["closing_source"] = "api_football_near_close"
            row["closing_captured_at"] = _text(selected_near.get("captured_at")) or _now_iso()
            row["closing_fixture_id"] = row_fixture_id(selected_near)
            row["closing_quality"] = quality if quality in VALID_CLOSING_QUALITY else "unavailable"
            row["closing_status"] = "captured"
            row.update(_compute_clv_fields(taken_odds, closing_odds))
            if "closing_missing" in row:
                row["closing_missing"] = "false"
            updated = 1
            break
        _write_ledger(ledger, ledger_fields, ledger_rows)

    clv_value = None
    clv_pct = None
    if closing_odds is not None and taken_odds is not None:
        clv_value = round(closing_odds / taken_odds - 1.0, 8)
        clv_pct = round(clv_value * 100.0, 4)

    return {
        "ledger": ledger,
        "near_close_file": near_close_file,
        "shadow_id": shadow_id,
        "near_close_candidates": candidate_count,
        "ledger_matches": len(matched_ledger),
        "would_update": would_update,
        "updated": updated,
        "applied": bool(apply and updated),
        "dry_run": not apply,
        "closing_odds": closing_odds,
        "closing_bookmaker": _text(selected_near.get("bookmaker")) if selected_near else "",
        "closing_fixture_id": row_fixture_id(selected_near) if selected_near else "",
        "closing_status": status,
        "closing_quality": quality,
        "clv": clv_value,
        "clv_pct": clv_pct,
        "errors": errors,
        "lab_only": True,
        "can_influence_picks": False,
        "message": "Observation uniquement, aucune mise.",
    }


def print_report(report: Dict[str, Any]) -> None:
    print(f"Ledger: {report.get('ledger')}")
    print(f"Near-close file: {report.get('near_close_file')}")
    print(f"Candidats near-close: {report.get('near_close_candidates')}")
    print(f"Matchs ledger trouvés: {report.get('ledger_matches')}")
    action = report.get("updated") if report.get("applied") else report.get("would_update")
    print(f"Would update / updated: {action}")
    print(f"Closing odds: {report.get('closing_odds') if report.get('closing_odds') is not None else 'n/a'}")
    print(f"CLV: {report.get('clv') if report.get('clv') is not None else 'n/a'}")
    print(f"Quality: {report.get('closing_quality')}")
    print(f"Applied: {str(bool(report.get('applied'))).lower()}")
    for error in report.get("errors") or []:
        print(f"Erreur: {error}")
    print("Observation uniquement, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Applique une near-close API-Football au ledger shadow en mode laboratoire.")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--near-close-file", required=True)
    parser.add_argument("--shadow-id", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = apply_near_close(
            args.ledger,
            args.near_close_file,
            shadow_id=args.shadow_id,
            apply=bool(args.apply),
        )
        print_report(report)
        return 0 if report.get("closing_status") != "ambiguous" else 1
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
