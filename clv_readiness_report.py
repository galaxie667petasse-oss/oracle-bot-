import argparse
import csv
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


TAKEN_ODDS_COLUMNS = ("odds", "taken_odds")
ODDS_META_COLUMNS = ("odds_source_column", "market_type", "pari", "is_home_pick", "is_away_pick", "is_draw", "is_over", "is_under")
H2H_CLOSING_COLUMNS = ("C_LTH", "C_LTD", "C_LTA", "C_PHH", "C_PHD", "C_PHA")
OVER_UNDER_CLOSING_COLUMNS = ("C_LTO", "C_LTU", "C_VHO", "C_VHU", "C_OTB", "C_UTB", "C_PHO", "C_PHU")
BTTS_CLOSING_COLUMNS = ("C_HTB", "C_ATB", "C_PHB", "C_HNB", "C_ANB", "C_PNB")
KNOWN_CLOSING_COLUMNS = H2H_CLOSING_COLUMNS + OVER_UNDER_CLOSING_COLUMNS + BTTS_CLOSING_COLUMNS
GENERIC_CLOSING_TOKENS = ("closing", "close", "pinnacle", "b365")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_reports_path(path: str) -> Path:
    target = Path(path)
    parts = [part.lower() for part in target.parts]
    if "data" in parts:
        raise ValueError("Le rapport CLV readiness ne doit pas etre ecrit dans data/.")
    if "reports" not in parts:
        raise ValueError("Le rapport CLV readiness doit etre ecrit dans reports/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _present(fieldnames: Sequence[str], candidates: Iterable[str]) -> List[str]:
    lookup = {str(name).lower(): str(name) for name in fieldnames}
    out: List[str] = []
    for candidate in candidates:
        value = lookup.get(candidate.lower())
        if value:
            out.append(value)
    return out


def detect_closing_columns(fieldnames: Sequence[str]) -> Dict[str, Any]:
    c_columns = [name for name in fieldnames if str(name).upper().startswith("C_")]
    generic = [
        name for name in fieldnames
        if any(token in str(name).lower() for token in GENERIC_CLOSING_TOKENS)
    ]
    h2h = _present(fieldnames, H2H_CLOSING_COLUMNS)
    over_under = _present(fieldnames, OVER_UNDER_CLOSING_COLUMNS)
    btts = _present(fieldnames, BTTS_CLOSING_COLUMNS)
    all_columns = sorted(set(c_columns + generic + h2h + over_under + btts))
    return {
        "all": all_columns,
        "c_columns": sorted(set(c_columns)),
        "generic": sorted(set(generic)),
        "h2h": h2h,
        "over_under": over_under,
        "btts": btts,
    }


def _missing_for_market(present: Sequence[str], expected: Sequence[str]) -> List[str]:
    present_upper = {item.upper() for item in present}
    return [item for item in expected if item.upper() not in present_upper]


def analyze_readiness(features_path: str) -> Dict[str, Any]:
    path = Path(features_path)
    if not path.exists():
        return {
            "generated_at": now_iso(),
            "features_path": str(path),
            "status": "indisponible",
            "clv_calculable": False,
            "reason": f"Fichier introuvable: {features_path}",
            "columns_available": [],
            "missing_columns": list(KNOWN_CLOSING_COLUMNS),
            "markets": {},
            "checklist": _checklist(),
            "lab_only": True,
            "can_influence_picks": False,
        }
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        rows_checked = 0
        market_values = set()
        for row in reader:
            rows_checked += 1
            market = str(row.get("market_type") or "").strip()
            if market:
                market_values.add(market)
            if rows_checked >= 5000:
                break

    odds_columns = _present(fieldnames, TAKEN_ODDS_COLUMNS)
    odds_meta = _present(fieldnames, ODDS_META_COLUMNS)
    closing = detect_closing_columns(fieldnames)
    h2h_available = bool(closing["h2h"])
    ou_available = bool(closing["over_under"])
    btts_available = bool(closing["btts"])
    clv_calculable = bool(odds_columns and closing["all"])
    if not odds_columns:
        reason = "Colonne de cote prise absente: odds/taken_odds requis."
    elif not closing["all"]:
        reason = "Aucune colonne closing odds detectee: ajouter des colonnes C_* fiables avant clv_analysis.py."
    else:
        reason = "CLV partiellement calculable: verifier le mapping marche/cote closing avant interpretation."
    missing_columns = sorted(set(KNOWN_CLOSING_COLUMNS) - {name.upper() for name in closing["all"]})
    markets = {
        "detected_market_types": sorted(market_values),
        "h2h_closing_possible": h2h_available,
        "h2h_columns_detected": closing["h2h"],
        "h2h_missing_columns": _missing_for_market(closing["h2h"], H2H_CLOSING_COLUMNS),
        "over_under_closing_possible": ou_available,
        "over_under_columns_detected": closing["over_under"],
        "over_under_missing_columns": _missing_for_market(closing["over_under"], OVER_UNDER_CLOSING_COLUMNS),
        "btts_closing_possible": btts_available,
        "btts_columns_detected": closing["btts"],
        "btts_missing_columns": _missing_for_market(closing["btts"], BTTS_CLOSING_COLUMNS),
    }
    return {
        "generated_at": now_iso(),
        "features_path": str(path),
        "status": "partiel" if clv_calculable else "indisponible",
        "clv_calculable": clv_calculable,
        "reason": reason,
        "rows_sampled_for_markets": rows_checked,
        "columns_count": len(fieldnames),
        "columns_available": fieldnames,
        "odds_columns_detected": odds_columns,
        "odds_meta_columns_detected": odds_meta,
        "closing_columns_detected": closing["all"],
        "closing_c_columns_detected": closing["c_columns"],
        "closing_generic_columns_detected": closing["generic"],
        "missing_columns": missing_columns,
        "markets": markets,
        "checklist": _checklist(),
        "warnings": [
            "Ne pas inventer de closing odds.",
            "Verifier la fiabilite Football-Data/Pinnacle apres 2025-07-23 avant interpretation.",
            "Sans CLV positive fiable, tout signal reste observation/watchlist.",
        ],
        "lab_only": True,
        "can_influence_picks": False,
    }


def _checklist() -> List[str]:
    return [
        "Verifier si data/MATCHES.csv contient des colonnes C_* fiables sans modifier le fichier source.",
        "Enrichir feature_builder.py pour propager les colonnes closing necessaires vers un nouvel export de features.",
        "Verifier la validite de la source Football-Data apres 2025-07-23, surtout Pinnacle.",
        "Ne pas utiliser de closing douteux ni incomplet pour promouvoir un signal.",
        "Relancer clv_analysis.py uniquement apres ajout explicite des closing odds.",
    ]


def write_json(report: Dict[str, Any], path: str) -> Path:
    target = ensure_reports_path(path)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], path: str) -> Path:
    target = ensure_reports_path(path)
    markets = report.get("markets") or {}
    checklist = "".join(f"<li>{html.escape(str(item))}</li>" for item in report.get("checklist") or [])
    target.write_text("\n".join([
        "<!doctype html>",
        "<html lang='fr'><head><meta charset='utf-8'>",
        "<title>CLV Readiness Oracle Bot</title>",
        "<style>body{font-family:Arial,sans-serif;margin:32px;color:#1f2933}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px;text-align:left}th{background:#f3f4f6}.warn{background:#fff7ed;border:1px solid #fed7aa;padding:12px;border-radius:6px}</style>",
        "</head><body>",
        "<h1>CLV Readiness</h1>",
        f"<p>Statut: {html.escape(str(report.get('status')))}. Calculable: {report.get('clv_calculable')}.</p>",
        f"<p>{html.escape(str(report.get('reason')))}</p>",
        "<table><tbody>",
        f"<tr><th>Colonnes odds</th><td>{html.escape(', '.join(report.get('odds_columns_detected') or []))}</td></tr>",
        f"<tr><th>Colonnes closing</th><td>{html.escape(', '.join(report.get('closing_columns_detected') or []))}</td></tr>",
        f"<tr><th>H2H closing possible</th><td>{markets.get('h2h_closing_possible')}</td></tr>",
        f"<tr><th>Over/Under closing possible</th><td>{markets.get('over_under_closing_possible')}</td></tr>",
        f"<tr><th>BTTS closing possible</th><td>{markets.get('btts_closing_possible')}</td></tr>",
        "</tbody></table>",
        "<section class='warn'><h2>Checklist</h2><ul>",
        checklist,
        "</ul></section>",
        "<p>Rapport descriptif seulement: aucun pick automatique, aucune DB, aucun fichier data/ modifie.</p>",
        "</body></html>",
    ]), encoding="utf-8")
    return target


def print_report(report: Dict[str, Any]) -> None:
    markets = report.get("markets") or {}
    print("CLV Readiness Oracle Bot")
    print(f"- Features: {report.get('features_path')}")
    print(f"- Statut: {report.get('status')}")
    print(f"- CLV calculable: {report.get('clv_calculable')}")
    print(f"- Raison: {report.get('reason')}")
    print(f"- Colonnes odds detectees: {', '.join(report.get('odds_columns_detected') or []) or 'aucune'}")
    print(f"- Colonnes closing detectees: {', '.join(report.get('closing_columns_detected') or []) or 'aucune'}")
    print(f"- Marches detectes: {', '.join(markets.get('detected_market_types') or []) or 'non echantillonnes'}")
    print(f"- H2H closing possible: {markets.get('h2h_closing_possible')}")
    print(f"- Over/Under closing possible: {markets.get('over_under_closing_possible')}")
    print(f"- BTTS closing possible: {markets.get('btts_closing_possible')}")
    print("- Checklist:")
    for item in report.get("checklist") or []:
        print(f"  - {item}")
    for warning in report.get("warnings") or []:
        print(f"- Avertissement: {warning}")
    print("- Aucun pick automatique et aucune modification DB/data.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Rapport local de readiness CLV, sans calculer de closing invente.")
    parser.add_argument("--features", required=True, help="CSV de features a inspecter")
    parser.add_argument("--output", default="", help="Rapport JSON dans reports/")
    parser.add_argument("--html", default="", help="Rapport HTML dans reports/")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = analyze_readiness(args.features)
        if args.output:
            path = write_json(report, args.output)
            print(f"- Rapport JSON CLV readiness ecrit: {path}")
        if args.html:
            path = write_html(report, args.html)
            print(f"- Rapport HTML CLV readiness ecrit: {path}")
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
