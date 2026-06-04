import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from historical_odds_schema_detector import _to_float, detect_schema


OUTPUT_COLUMNS = [
    "match_date",
    "league",
    "home_team",
    "away_team",
    "bookmaker",
    "market_type",
    "side",
    "opening_odds",
    "closing_odds",
    "clv_percent",
    "result",
    "profit_unit",
    "source_row",
    "is_valid",
    "validation_reason",
]


def ensure_reports_path(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("L'import CLV historique doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _read_json(path: str) -> Dict[str, Any]:
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _safe_odds(value: Any) -> Optional[float]:
    number = _to_float(value)
    if number is None:
        return None
    if 1.01 <= number <= 100:
        return number
    return None


def _result_from_row(row: Dict[str, Any], schema: Dict[str, Any]) -> str:
    detected = schema.get("detected_columns") or {}
    result_col = detected.get("result")
    if result_col and row.get(result_col):
        value = str(row.get(result_col) or "").strip().upper()
        if value in {"H", "HOME", "1"}:
            return "home"
        if value in {"D", "DRAW", "X"}:
            return "draw"
        if value in {"A", "AWAY", "2"}:
            return "away"
    hg_col = detected.get("home_goals")
    ag_col = detected.get("away_goals")
    hg = _to_float(row.get(hg_col)) if hg_col else None
    ag = _to_float(row.get(ag_col)) if ag_col else None
    if hg is None or ag is None:
        return "unknown"
    if hg > ag:
        return "home"
    if hg < ag:
        return "away"
    return "draw"


def _profit(side: str, result: str, opening_odds: float) -> Optional[float]:
    if result == "unknown":
        return None
    if side == result:
        return round(opening_odds - 1.0, 8)
    return -1.0


def _row_base(row: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
    detected = schema.get("detected_columns") or {}
    return {
        "match_date": row.get(detected.get("date") or "") or "",
        "league": row.get(detected.get("league") or "") or "",
        "home_team": row.get(detected.get("home_team") or "") or "",
        "away_team": row.get(detected.get("away_team") or "") or "",
        "bookmaker": row.get(detected.get("bookmaker") or "") or "",
        "market_type": "h2h",
    }


def import_historical_clv(csv_path: str, schema_path: str = "", output: str = "", max_rows: int = 0) -> Dict[str, Any]:
    schema = _read_json(schema_path) if schema_path else detect_schema(csv_path)
    detected = schema.get("detected_columns") or {}
    side_columns = {
        "home": (detected.get("opening_home"), detected.get("closing_home")),
        "draw": (detected.get("opening_draw"), detected.get("closing_draw")),
        "away": (detected.get("opening_away"), detected.get("closing_away")),
    }
    source = Path(csv_path)
    normalized: List[Dict[str, Any]] = []
    rows_read = 0
    rejected = 0
    rejection_reasons: Dict[str, int] = {}
    with source.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for source_idx, row in enumerate(reader, start=2):
            rows_read += 1
            if max_rows and rows_read > max_rows:
                break
            result = _result_from_row(row, schema)
            base = _row_base(row, schema)
            for side, (opening_col, closing_col) in side_columns.items():
                if not opening_col or not closing_col:
                    reason = f"colonnes {side} incompletes"
                    rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                    continue
                opening = _safe_odds(row.get(opening_col))
                closing = _safe_odds(row.get(closing_col))
                if opening is None or closing is None:
                    rejected += 1
                    reason = f"cotes {side} non plausibles"
                    rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                    normalized.append({**base, "side": side, "opening_odds": row.get(opening_col, ""), "closing_odds": row.get(closing_col, ""), "clv_percent": "", "result": result, "profit_unit": "", "source_row": source_idx, "is_valid": "False", "validation_reason": reason})
                    continue
                profit = _profit(side, result, opening)
                normalized.append({
                    **base,
                    "side": side,
                    "opening_odds": opening,
                    "closing_odds": closing,
                    "clv_percent": round(opening / closing - 1.0, 8),
                    "result": result,
                    "profit_unit": "" if profit is None else profit,
                    "source_row": source_idx,
                    "is_valid": "True",
                    "validation_reason": "",
                })
    valid = [row for row in normalized if str(row.get("is_valid")) == "True"]
    if output:
        write_csv(normalized, output)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input_csv": csv_path,
        "schema_path": schema_path or None,
        "output": output or None,
        "rows_read": rows_read,
        "rows_written": len(normalized),
        "valid_rows": len(valid),
        "rejected_rows": len(normalized) - len(valid),
        "rejection_reasons": rejection_reasons,
        "clv_mean": round(sum(float(row["clv_percent"]) for row in valid) / len(valid), 6) if valid else None,
        "clv_positive_rate": round(sum(1 for row in valid if float(row["clv_percent"]) > 0) / len(valid) * 100.0, 2) if valid else None,
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_csv(rows: Iterable[Dict[str, Any]], output: str) -> Path:
    target = ensure_reports_path(output)
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in OUTPUT_COLUMNS})
    return target


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = ensure_reports_path(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Import CLV historique Oracle")
    print(f"- Lignes source lues: {report.get('rows_read')}")
    print(f"- Lignes normalisees valides: {report.get('valid_rows')}")
    print(f"- CLV moyenne: {report.get('clv_mean')}")
    print("- Import laboratoire seulement, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Importe un CSV historique opening/closing vers un format CLV normalise.")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--schema", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary-json", default="")
    parser.add_argument("--max-rows", type=int, default=0)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = import_historical_clv(args.csv, schema_path=args.schema, output=args.output, max_rows=args.max_rows)
        if args.summary_json:
            write_json(report, args.summary_json)
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
