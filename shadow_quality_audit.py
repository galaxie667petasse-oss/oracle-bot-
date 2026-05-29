import argparse
import csv
import html
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from shadow_ledger import LEDGER_COLUMNS, VALID_RESULT, read_ledger


ALLOWED_MARKETS = {"h2h", "total", "btts", "draw", "asian_handicap", "handicap", "unknown", ""}
ALLOWED_SIDES = {"home", "away", "draw", "over", "under", "yes", "no", "unknown", ""}


def ensure_reports_path(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le rapport qualite shadow ne doit pas etre ecrit dans data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _float(value: Any):
    try:
        number = float(str(value).strip().replace(",", "."))
    except Exception:
        return None
    return number if math.isfinite(number) else None


def _is_decimal_odds(value: Any) -> bool:
    number = _float(value)
    return number is not None and number > 1.01 and number <= 100.0


def _valid_date(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        datetime.fromisoformat(text[:10])
        return True
    except Exception:
        return False


def _dedupe_key(row: Dict[str, Any]) -> Tuple[str, ...]:
    return (
        str(row.get("match_date") or "").strip().lower(),
        str(row.get("league") or "").strip().lower(),
        str(row.get("home_team") or "").strip().lower(),
        str(row.get("away_team") or "").strip().lower(),
        str(row.get("market_type") or "").strip().lower(),
        str(row.get("side") or "").strip().lower(),
        str(row.get("taken_odds") or "").strip().replace(",", "."),
    )


def _counts(rows: List[Dict[str, str]], key: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "inconnu").strip() or "inconnu"
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items(), key=lambda item: (-item[1], item[0])))


def audit_shadow_ledger(ledger_path: str) -> Dict[str, Any]:
    target = Path(ledger_path)
    errors: List[str] = []
    warnings: List[str] = []
    recommendations: List[str] = []
    if not target.exists():
        return {
            "ledger": ledger_path,
            "rows": 0,
            "verdict": "invalid",
            "blocking_errors": [f"Ledger introuvable: {ledger_path}"],
            "warnings": [],
            "recommendations": ["Initialiser le ledger avec python shadow_workflow.py --init"],
            "lab_only": True,
            "can_influence_picks": False,
        }
    with target.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        rows = [dict(row) for row in reader]
    missing_columns = [column for column in LEDGER_COLUMNS if column not in fieldnames]
    if missing_columns:
        errors.append("Colonnes obligatoires manquantes: " + ", ".join(missing_columns))
    ids: Dict[str, int] = {}
    duplicate_keys: Dict[Tuple[str, ...], int] = {}
    line_errors: List[Dict[str, Any]] = []
    clv_rows = 0
    result_rows = 0
    for idx, row in enumerate(rows, start=2):
        line_issue = []
        shadow_id = str(row.get("shadow_id") or "").strip()
        ids[shadow_id] = ids.get(shadow_id, 0) + 1
        if not shadow_id:
            line_issue.append("shadow_id vide")
        if not _valid_date(row.get("match_date")):
            line_issue.append("date invalide ou absente")
        if not _is_decimal_odds(row.get("taken_odds")):
            line_issue.append("taken_odds non plausible")
        closing_text = str(row.get("closing_odds") or "").strip()
        if closing_text:
            if not _is_decimal_odds(closing_text):
                line_issue.append("closing_odds non plausible")
            else:
                clv_rows += 1
                taken = _float(row.get("taken_odds"))
                closing = _float(closing_text)
                observed = _float(row.get("clv_percent"))
                if taken is not None and closing is not None and observed is not None:
                    expected = taken / closing - 1.0
                    if abs(expected - observed) > 0.0001:
                        line_issue.append("clv_percent incoherent")
                else:
                    line_issue.append("clv_percent absent ou invalide")
        result = str(row.get("result") or "unknown").strip().lower()
        if result not in VALID_RESULT:
            line_issue.append("result invalide")
        if result not in {"", "unknown"}:
            result_rows += 1
        market = str(row.get("market_type") or "").strip().lower()
        if market not in ALLOWED_MARKETS:
            line_issue.append("market_type inattendu")
        side = str(row.get("side") or "").strip().lower()
        if side not in ALLOWED_SIDES:
            line_issue.append("side inattendu")
        if not str(row.get("home_team") or "").strip() or not str(row.get("away_team") or "").strip():
            line_issue.append("equipes absentes")
        duplicate_keys[_dedupe_key(row)] = duplicate_keys.get(_dedupe_key(row), 0) + 1
        if line_issue:
            line_errors.append({"line": idx, "shadow_id": shadow_id, "issues": line_issue})
    duplicate_ids = [shadow_id for shadow_id, count in ids.items() if shadow_id and count > 1]
    duplicate_rows = [key for key, count in duplicate_keys.items() if count > 1]
    if duplicate_ids:
        errors.append("shadow_id dupliques: " + ", ".join(duplicate_ids[:10]))
    if duplicate_rows:
        warnings.append(f"Doublons probables: {len(duplicate_rows)}")
    missing_closing = sum(1 for row in rows if not str(row.get("closing_odds") or "").strip())
    missing_results = sum(1 for row in rows if str(row.get("result") or "unknown").lower() == "unknown")
    no_odds = sum(1 for row in rows if not _is_decimal_odds(row.get("taken_odds")))
    if not rows:
        warnings.append("Ledger vide: preuve non demarree")
    if missing_closing:
        warnings.append(f"Closing odds manquantes: {missing_closing}")
    if missing_results:
        warnings.append(f"Resultats manquants: {missing_results}")
    if no_odds:
        errors.append(f"Observations avec taken_odds invalide: {no_odds}")
    if line_errors:
        errors.append(f"Lignes avec erreurs bloquantes: {len(line_errors)}")
    if errors:
        verdict = "invalid" if missing_columns or duplicate_ids or no_odds or any("Lignes" in item for item in errors) else "poor_quality"
    elif len(rows) == 0:
        verdict = "usable_with_warnings"
    elif warnings:
        verdict = "usable_with_warnings"
    else:
        verdict = "clean"
    if clv_rows < len(rows):
        recommendations.append("Renseigner les closing odds manuelles fiables.")
    if result_rows < len(rows):
        recommendations.append("Importer les resultats avec results_manual_import.py.")
    if len(rows) < 1000:
        recommendations.append("Continuer la collecte: sample shadow inferieur a 1000.")
    recommendations.append("Relancer shadow_clv_report.py puis evidence_gate.py.")
    return {
        "ledger": ledger_path,
        "rows": len(rows),
        "columns_present": fieldnames,
        "missing_columns": missing_columns,
        "unique_shadow_ids": len([shadow_id for shadow_id in ids if shadow_id]),
        "duplicate_shadow_ids": duplicate_ids,
        "duplicate_count": len(duplicate_rows),
        "missing_closing": missing_closing,
        "missing_results": missing_results,
        "observations_without_valid_odds": no_odds,
        "samples_by_strategy": _counts(rows, "strategy_name"),
        "samples_by_league": _counts(rows, "league"),
        "samples_by_market": _counts(rows, "market_type"),
        "clv_coverage": round(clv_rows / len(rows) * 100.0, 2) if rows else 0.0,
        "result_coverage": round(result_rows / len(rows) * 100.0, 2) if rows else 0.0,
        "error_rate": round(len(line_errors) / len(rows) * 100.0, 2) if rows else 0.0,
        "blocking_errors": errors,
        "line_errors": line_errors[:50],
        "warnings": warnings,
        "recommendations": recommendations,
        "next_commands": [
            "python shadow_workflow.py --make-closing-template",
            "python results_manual_import.py --ledger reports/shadow_ledger.csv --results-csv reports/manual_results_import.csv",
            "python shadow_clv_report.py --ledger reports/shadow_ledger.csv --output reports/shadow_clv_report.json --html reports/shadow_clv_report.html",
        ],
        "verdict": verdict,
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_json(report: Dict[str, Any], path: str) -> Path:
    target = ensure_reports_path(path)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], path: str) -> Path:
    target = ensure_reports_path(path)
    errors = "".join(f"<li>{html.escape(str(item))}</li>" for item in report.get("blocking_errors") or [])
    warnings = "".join(f"<li>{html.escape(str(item))}</li>" for item in report.get("warnings") or [])
    recos = "".join(f"<li>{html.escape(str(item))}</li>" for item in report.get("recommendations") or [])
    target.write_text("\n".join([
        "<!doctype html>",
        "<html lang='fr'><head><meta charset='utf-8'><title>Shadow Quality Audit</title>",
        "<style>body{font-family:Arial,sans-serif;margin:32px;color:#1f2933}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px;text-align:left}th{background:#f3f4f6}.warn{background:#fff7ed;border:1px solid #fed7aa;padding:12px;border-radius:6px}</style>",
        "</head><body><h1>Shadow Quality Audit</h1>",
        "<table><tbody>",
        f"<tr><th>Ledger</th><td>{html.escape(str(report.get('ledger')))}</td></tr>",
        f"<tr><th>Lignes</th><td>{report.get('rows')}</td></tr>",
        f"<tr><th>Verdict</th><td>{html.escape(str(report.get('verdict')))}</td></tr>",
        f"<tr><th>Coverage CLV</th><td>{report.get('clv_coverage')}%</td></tr>",
        f"<tr><th>Coverage resultats</th><td>{report.get('result_coverage')}%</td></tr>",
        "</tbody></table>",
        f"<section class='warn'><h2>Erreurs bloquantes</h2><ul>{errors or '<li>Aucune</li>'}</ul></section>",
        f"<section class='warn'><h2>Warnings</h2><ul>{warnings or '<li>Aucun</li>'}</ul></section>",
        f"<section><h2>Recommandations</h2><ul>{recos}</ul></section>",
        "<p>Mode laboratoire: aucune mise, aucun Telegram, aucune activation automatique.</p>",
        "</body></html>",
    ]), encoding="utf-8")
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Shadow Quality Audit Oracle Bot")
    print(f"- Ledger: {report.get('ledger')}")
    print(f"- Lignes: {report.get('rows')}")
    print(f"- Verdict: {report.get('verdict')}")
    print(f"- Coverage CLV: {report.get('clv_coverage')}%")
    print(f"- Coverage resultats: {report.get('result_coverage')}%")
    for error in report.get("blocking_errors") or []:
        print(f"- Bloquant: {error}")
    for warning in report.get("warnings") or []:
        print(f"- Warning: {warning}")
    print("- Observation shadow seulement, aucune mise conseillee.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Audite la qualite du ledger shadow.")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = audit_shadow_ledger(args.ledger)
        if args.output:
            write_json(report, args.output)
        if args.html:
            write_html(report, args.html)
        print_report(report)
        return 0 if report.get("verdict") != "invalid" else 1
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
