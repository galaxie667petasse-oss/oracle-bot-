import argparse
import csv
import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


H2H_CLOSING_COLUMNS = (
    "C_LTH", "C_LTD", "C_LTA",
    "C_VCH", "C_VCD", "C_VCA",
    "PSCH", "PSCD", "PSCA",
    "B365CH", "B365CD", "B365CA",
    "MaxCH", "MaxCD", "MaxCA",
    "AvgCH", "AvgCD", "AvgCA",
)
H2H_OPENING_COLUMNS = ("B365H", "B365D", "B365A", "PSH", "PSD", "PSA", "MaxH", "MaxD", "MaxA", "AvgH", "AvgD", "AvgA")
TOTAL_CLOSING_COLUMNS = ("C_LTO", "C_LTU", "PCO", "PCU", "B365C>2.5", "B365C<2.5", "MaxC>2.5", "MaxC<2.5", "AvgC>2.5", "AvgC<2.5")
BTTS_CLOSING_HINTS = ("btts", "bothteamstoscore", "gg", "ng")
PINNACLE_WARNING_DATE = "2025-07-23"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_reports_path(path: str) -> Path:
    target = Path(path)
    parts = [part.lower() for part in target.parts]
    if "data" in parts:
        raise ValueError("Le rapport closing odds ne doit pas etre ecrit dans data/.")
    if "reports" not in parts:
        raise ValueError("Le rapport closing odds doit etre ecrit dans reports/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _norm(name: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name or "").lower())


def _present(fieldnames: Sequence[str], candidates: Iterable[str]) -> List[str]:
    lookup = {_norm(name): str(name) for name in fieldnames}
    out: List[str] = []
    for candidate in candidates:
        value = lookup.get(_norm(candidate))
        if value and value not in out:
            out.append(value)
    return out


def _generic_closing_columns(fieldnames: Sequence[str]) -> List[str]:
    out: List[str] = []
    known = {_norm(name) for name in H2H_CLOSING_COLUMNS + TOTAL_CLOSING_COLUMNS}
    for name in fieldnames:
        norm = _norm(name)
        lower = str(name).lower()
        if norm in known:
            continue
        if "closing" in lower or "close" in lower:
            out.append(str(name))
            continue
        if re.search(r"c(?:h|d|a|o|u)$", norm) and any(prefix in norm for prefix in ("b365", "ps", "max", "avg", "pin", "vc")):
            out.append(str(name))
    return sorted(set(out))


def _btts_closing_columns(fieldnames: Sequence[str]) -> List[str]:
    out: List[str] = []
    for name in fieldnames:
        norm = _norm(name)
        if any(hint in norm for hint in BTTS_CLOSING_HINTS) and ("close" in norm or norm.startswith("c")):
            out.append(str(name))
    return sorted(set(out))


def _date_range(rows: List[Dict[str, Any]]) -> Dict[str, str]:
    dates = []
    for row in rows:
        value = str(row.get("Date") or row.get("date") or row.get("DateKey") or row.get("date_key") or "").strip()[:10]
        if len(value) >= 10:
            dates.append(value)
    return {"date_min": min(dates) if dates else "", "date_max": max(dates) if dates else ""}


def _recommended_mapping(h2h: List[str], total: List[str], btts: List[str]) -> Dict[str, Any]:
    mapping: Dict[str, Any] = {}
    lookup = {_norm(name): name for name in h2h + total + btts}
    for key, candidates in {
        "h2h_home": ("C_LTH", "C_VCH", "PSCH", "B365CH", "MaxCH", "AvgCH"),
        "h2h_draw": ("C_LTD", "C_VCD", "PSCD", "B365CD", "MaxCD", "AvgCD"),
        "h2h_away": ("C_LTA", "C_VCA", "PSCA", "B365CA", "MaxCA", "AvgCA"),
        "total_over": ("C_LTO", "PCO", "B365C>2.5", "MaxC>2.5", "AvgC>2.5"),
        "total_under": ("C_LTU", "PCU", "B365C<2.5", "MaxC<2.5", "AvgC<2.5"),
    }.items():
        for candidate in candidates:
            value = lookup.get(_norm(candidate))
            if value:
                mapping[key] = value
                break
    if btts:
        mapping["btts_raw_candidates"] = btts
    return mapping


def probe_csv(csv_path: str, sample_rows: int = 5000) -> Dict[str, Any]:
    path = Path(csv_path)
    if not path.exists():
        return {
            "generated_at": now_iso(),
            "csv_path": str(path),
            "status": "erreur",
            "error": f"Fichier introuvable: {csv_path}",
            "closing_available": False,
            "h2h_closing_available": False,
            "total_closing_available": False,
            "btts_closing_available": False,
            "detected_columns": {},
            "missing_columns": list(H2H_CLOSING_COLUMNS[:3]),
            "recommended_mapping": {},
            "message": "Ce rapport ne calcule pas la CLV, il verifie seulement la disponibilite des colonnes.",
        }
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        rows = []
        for row in reader:
            rows.append(row)
            if len(rows) >= sample_rows:
                break

    h2h_closing = _present(fieldnames, H2H_CLOSING_COLUMNS)
    h2h_opening = _present(fieldnames, H2H_OPENING_COLUMNS)
    total_closing = _present(fieldnames, TOTAL_CLOSING_COLUMNS)
    btts_closing = _btts_closing_columns(fieldnames)
    generic_closing = _generic_closing_columns(fieldnames)
    detected_all = sorted(set(h2h_closing + total_closing + btts_closing + generic_closing))
    h2h_available = any(_norm(col) in {_norm(c) for c in H2H_CLOSING_COLUMNS[:3]} for col in h2h_closing) or len(h2h_closing) >= 3
    total_available = bool(total_closing)
    btts_available = bool(btts_closing)
    date_info = _date_range(rows)
    warnings: List[str] = []
    if date_info.get("date_max") and date_info["date_max"] >= PINNACLE_WARNING_DATE and any(_norm(col).startswith("ps") for col in detected_all):
        warnings.append("Colonnes Pinnacle/PS detectees apres 2025-07-23: verifier la fiabilite de source avant CLV.")
    if not detected_all:
        warnings.append("Aucune colonne closing detectee dans ce CSV.")
    missing = []
    for column in ("C_LTH", "C_LTD", "C_LTA"):
        if _norm(column) not in {_norm(value) for value in detected_all}:
            missing.append(column)
    return {
        "generated_at": now_iso(),
        "csv_path": str(path),
        "status": "ok",
        "rows_sampled": len(rows),
        "columns_count": len(fieldnames),
        "date_min": date_info.get("date_min", ""),
        "date_max": date_info.get("date_max", ""),
        "closing_available": bool(detected_all),
        "h2h_closing_available": h2h_available,
        "total_closing_available": total_available,
        "btts_closing_available": btts_available,
        "detected_columns": {
            "h2h_closing": h2h_closing,
            "h2h_opening": h2h_opening,
            "total_closing": total_closing,
            "btts_closing": btts_closing,
            "generic_closing": generic_closing,
            "all_closing": detected_all,
        },
        "missing_columns": missing,
        "recommended_mapping": _recommended_mapping(h2h_closing + generic_closing, total_closing + generic_closing, btts_closing),
        "warnings": warnings,
        "message": "Ce rapport ne calcule pas la CLV, il verifie seulement la disponibilite des colonnes.",
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_json(report: Dict[str, Any], path: str) -> Path:
    target = ensure_reports_path(path)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], path: str) -> Path:
    target = ensure_reports_path(path)
    detected = report.get("detected_columns") or {}
    target.write_text("\n".join([
        "<!doctype html>",
        "<html lang='fr'><head><meta charset='utf-8'>",
        "<title>Closing Odds Probe</title>",
        "<style>body{font-family:Arial,sans-serif;margin:32px;color:#1f2933}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px;text-align:left}th{background:#f3f4f6}.warn{background:#fff7ed;border:1px solid #fed7aa;padding:12px;border-radius:6px}</style>",
        "</head><body>",
        "<h1>Closing Odds Probe</h1>",
        f"<p>{html.escape(str(report.get('message')))}</p>",
        "<table><tbody>",
        f"<tr><th>CSV</th><td>{html.escape(str(report.get('csv_path')))}</td></tr>",
        f"<tr><th>Closing disponible</th><td>{report.get('closing_available')}</td></tr>",
        f"<tr><th>H2H closing</th><td>{report.get('h2h_closing_available')}</td></tr>",
        f"<tr><th>Total closing</th><td>{report.get('total_closing_available')}</td></tr>",
        f"<tr><th>BTTS closing</th><td>{report.get('btts_closing_available')}</td></tr>",
        f"<tr><th>Colonnes H2H</th><td>{html.escape(', '.join(detected.get('h2h_closing') or []))}</td></tr>",
        f"<tr><th>Colonnes total</th><td>{html.escape(', '.join(detected.get('total_closing') or []))}</td></tr>",
        "</tbody></table>",
        "<section class='warn'><h2>Avertissements</h2><ul>",
        *[f"<li>{html.escape(str(item))}</li>" for item in report.get("warnings") or []],
        "</ul></section>",
        "<p>Rapport local descriptif: aucun calcul CLV, aucune modification data/DB.</p>",
        "</body></html>",
    ]), encoding="utf-8")
    return target


def print_report(report: Dict[str, Any]) -> None:
    detected = report.get("detected_columns") or {}
    print("Closing Odds Probe Oracle Bot")
    print(f"- CSV: {report.get('csv_path')}")
    print(f"- Closing disponible: {report.get('closing_available')}")
    print(f"- H2H closing disponible: {report.get('h2h_closing_available')}")
    print(f"- Total closing disponible: {report.get('total_closing_available')}")
    print(f"- BTTS closing disponible: {report.get('btts_closing_available')}")
    print(f"- Colonnes closing detectees: {', '.join(detected.get('all_closing') or []) or 'aucune'}")
    print(f"- Mapping recommande: {report.get('recommended_mapping')}")
    for warning in report.get("warnings") or []:
        print(f"- Avertissement: {warning}")
    print("- Ce rapport ne calcule pas la CLV, il verifie seulement la disponibilite des colonnes.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Inspecte un CSV source pour les colonnes closing odds, sans modifier le fichier.")
    parser.add_argument("--csv", required=True, help="CSV source a inspecter, ex: data/MATCHES.csv")
    parser.add_argument("--sample-rows", type=int, default=5000, help="Nombre de lignes a echantillonner")
    parser.add_argument("--output", default="", help="Rapport JSON dans reports/")
    parser.add_argument("--html", default="", help="Rapport HTML dans reports/")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = probe_csv(args.csv, sample_rows=args.sample_rows)
        if args.output:
            path = write_json(report, args.output)
            print(f"- Rapport JSON closing odds ecrit: {path}")
        if args.html:
            path = write_html(report, args.html)
            print(f"- Rapport HTML closing odds ecrit: {path}")
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
