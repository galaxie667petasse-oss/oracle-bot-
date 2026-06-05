import argparse
import csv
import html
import json
import statistics
from pathlib import Path
from typing import Any, Dict, Iterable, List


OPENING_H2H_COLUMNS = {
    "B365": ("B365H", "B365D", "B365A"),
    "BW": ("BWH", "BWD", "BWA"),
    "IW": ("IWH", "IWD", "IWA"),
    "PS": ("PSH", "PSD", "PSA"),
    "WH": ("WHH", "WHD", "WHA"),
    "VC": ("VCH", "VCD", "VCA"),
    "Max": ("MaxH", "MaxD", "MaxA"),
    "Avg": ("AvgH", "AvgD", "AvgA"),
}

EXPLICIT_CLOSING_H2H_COLUMNS = {
    "B365C": ("B365CH", "B365CD", "B365CA"),
    "PSC": ("PSCH", "PSCD", "PSCA"),
    "MaxC": ("MaxCH", "MaxCD", "MaxCA"),
    "AvgC": ("AvgCH", "AvgCD", "AvgCA"),
}


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("L'import Football-Data gratuit doit ecrire hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _read_csv(path: str) -> List[Dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _decimal(value: Any) -> float | None:
    try:
        number = float(str(value or "").strip().replace(",", "."))
    except Exception:
        return None
    if 1.01 < number < 100:
        return number
    return None


def _columns_present(columns: Iterable[str], group: Dict[str, tuple]) -> Dict[str, List[str]]:
    available = set(columns)
    return {name: [col for col in cols if col in available] for name, cols in group.items() if any(col in available for col in cols)}


def _plausible_triplet(rows: List[Dict[str, str]], cols: tuple) -> bool:
    values = []
    for row in rows:
        for col in cols:
            if col in row:
                parsed = _decimal(row.get(col))
                if parsed is not None:
                    values.append(parsed)
    return bool(values) and (sum(1 for value in values if 1.01 < value < 20) / len(values) >= 0.8)


def build_import(
    csv_path: str,
    output: str = "",
    summary_json: str = "",
    html_output: str = "",
    auto_detect: bool = False,
    run_historical_clv: bool = False,
) -> Dict[str, Any]:
    rows = _read_csv(csv_path)
    columns = list(rows[0].keys()) if rows else []
    opening = _columns_present(columns, OPENING_H2H_COLUMNS)
    closing_candidates = _columns_present(columns, EXPLICIT_CLOSING_H2H_COLUMNS)
    true_closing = {
        name: cols for name, cols in closing_candidates.items()
        if len(cols) == 3 and _plausible_triplet(rows, tuple(cols))
    }
    normalized: List[Dict[str, Any]] = []
    for row in rows:
        home_goals = row.get("FTHG", "")
        away_goals = row.get("FTAG", "")
        base = {
            "match_date": row.get("Date", ""),
            "league": row.get("Div", ""),
            "home_team": row.get("HomeTeam", ""),
            "away_team": row.get("AwayTeam", ""),
            "home_goals": home_goals,
            "away_goals": away_goals,
            "result": row.get("FTR", ""),
        }
        for bookmaker, cols in OPENING_H2H_COLUMNS.items():
            if not any(col in row for col in cols):
                continue
            payload = dict(base)
            payload.update({
                "bookmaker": bookmaker,
                "home_odds": row.get(cols[0], ""),
                "draw_odds": row.get(cols[1], ""),
                "away_odds": row.get(cols[2], ""),
            })
            normalized.append(payload)
    has_results = all(col in columns for col in ("FTHG", "FTAG", "FTR"))
    has_odds = bool(opening)
    has_true_closing = bool(true_closing)
    warnings = []
    if has_odds and not has_true_closing:
        warnings.append("historical_odds_available_but_closing_uncertain")
    if not has_odds:
        warnings.append("aucune colonne odds H2H gratuite detectee")
    if run_historical_clv and not has_true_closing:
        warnings.append("run_historical_clv ignore: aucune closing decimale explicite plausible")
    report = {
        "input": csv_path,
        "rows": len(rows),
        "normalized_rows": len(normalized),
        "leagues": sorted({row.get("Div", "") for row in rows if row.get("Div")}),
        "date_range": {
            "min": min([row.get("Date") for row in rows if row.get("Date")] or [""]),
            "max": max([row.get("Date") for row in rows if row.get("Date")] or [""]),
        },
        "bookmaker_columns": opening,
        "closing_columns": true_closing,
        "has_results": has_results,
        "has_odds": has_odds,
        "has_true_closing_odds": has_true_closing,
        "can_compute_roi": bool(has_results and has_odds),
        "can_compute_clv": has_true_closing,
        "warnings": warnings,
        "historical_clv_command": (
            f"python historical_clv_importer.py --csv {output} --output reports/historical_clv.csv"
            if has_true_closing and output else ""
        ),
        "lab_only": True,
        "can_influence_picks": False,
    }
    if output:
        write_normalized(normalized, output)
    if summary_json:
        write_json(report, summary_json)
    if html_output:
        write_html(report, html_output)
    return report


def write_normalized(rows: List[Dict[str, Any]], output: str) -> Path:
    target = _safe_output(output)
    fields = sorted({key for row in rows for key in row.keys()}) or ["empty"]
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return target


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>Football-Data Free Importer</h1><pre>"
        + html.escape(json.dumps(report, ensure_ascii=False, indent=2))
        + "</pre><p>Import gratuit local, aucune CLV inventee.</p></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Football-Data free importer")
    print(f"- Lignes: {report.get('rows')}")
    print(f"- Odds disponibles: {report.get('has_odds')}")
    print(f"- Resultats disponibles: {report.get('has_results')}")
    print(f"- Closing vraie plausible: {report.get('has_true_closing_odds')}")
    print(f"- CLV calculable: {report.get('can_compute_clv')}")
    for warning in report.get("warnings") or []:
        print(f"- Warning: {warning}")
    print("- Aucun fichier data/ modifie.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Importe un CSV Football-Data gratuit en laboratoire local.")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--summary-json", default="")
    parser.add_argument("--html", default="")
    parser.add_argument("--auto-detect", action="store_true")
    parser.add_argument("--run-historical-clv", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = build_import(
            args.csv,
            output=args.output,
            summary_json=args.summary_json,
            html_output=args.html,
            auto_detect=args.auto_detect,
            run_historical_clv=args.run_historical_clv,
        )
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
