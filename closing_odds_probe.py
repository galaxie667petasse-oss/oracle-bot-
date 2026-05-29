import argparse
import csv
import html
import json
import re
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


H2H_CLOSING_COLUMNS = (
    "C_LTH", "C_LTD", "C_LTA",
    "C_VCH", "C_VCD", "C_VCA",
    "PSCH", "PSCD", "PSCA",
    "B365CH", "B365CD", "B365CA",
    "MaxCH", "MaxCD", "MaxCA",
    "AvgCH", "AvgCD", "AvgCA",
)
H2H_HOME_COLUMNS = ("C_LTH", "C_VCH", "PSCH", "B365CH", "MaxCH", "AvgCH", "closing_home", "closing_home_odds")
H2H_DRAW_COLUMNS = ("C_LTD", "C_VCD", "PSCD", "B365CD", "MaxCD", "AvgCD", "closing_draw", "closing_draw_odds")
H2H_AWAY_COLUMNS = ("C_LTA", "C_VCA", "PSCA", "B365CA", "MaxCA", "AvgCA", "closing_away", "closing_away_odds")
H2H_OPENING_COLUMNS = ("B365H", "B365D", "B365A", "PSH", "PSD", "PSA", "MaxH", "MaxD", "MaxA", "AvgH", "AvgD", "AvgA")
TOTAL_OVER_COLUMNS = ("C_LTO", "PCO", "B365C>2.5", "MaxC>2.5", "AvgC>2.5", "closing_over", "closing_over_odds")
TOTAL_UNDER_COLUMNS = ("C_LTU", "PCU", "B365C<2.5", "MaxC<2.5", "AvgC<2.5", "closing_under", "closing_under_odds")
TOTAL_CLOSING_COLUMNS = TOTAL_OVER_COLUMNS + TOTAL_UNDER_COLUMNS
BTTS_CLOSING_HINTS = ("btts", "bothteamstoscore", "gg", "ng")
PINNACLE_WARNING_DATE = "2025-07-23"
ODDS_MIN = 1.01
ODDS_MAX = 100.0
ODDS_TYPICAL_MAX = 20.0
MOSTLY_EMPTY_RATE = 0.10


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


def _to_float(value: Any) -> Optional[float]:
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        number = float(text)
    except Exception:
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _percentile(sorted_values: Sequence[float], percentile: float) -> Optional[float]:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return round(float(sorted_values[0]), 6)
    position = (len(sorted_values) - 1) * percentile / 100.0
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    value = sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction
    return round(float(value), 6)


def _column_profile(rows: List[Dict[str, Any]], column: str, max_sample_values: int = 10) -> Dict[str, Any]:
    raw_examples: List[str] = []
    numeric_examples: List[float] = []
    numeric_values: List[float] = []
    non_empty = 0
    empty = 0
    text_count = 0
    numeric_count = 0
    count_le_zero = 0
    count_between_zero_one = 0
    count_plausible_1_100 = 0
    count_plausible_1_20 = 0
    count_very_large = 0
    for row in rows:
        raw = str(row.get(column) or "").strip()
        if not raw:
            empty += 1
            continue
        non_empty += 1
        if len(raw_examples) < max_sample_values:
            raw_examples.append(raw)
        number = _to_float(raw)
        if number is None:
            text_count += 1
            continue
        numeric_count += 1
        numeric_values.append(number)
        if len(numeric_examples) < max_sample_values:
            numeric_examples.append(round(number, 6))
        if number <= 0:
            count_le_zero += 1
        if 0 < number <= 1:
            count_between_zero_one += 1
        if ODDS_MIN <= number <= ODDS_MAX:
            count_plausible_1_100 += 1
        if ODDS_MIN <= number <= ODDS_TYPICAL_MAX:
            count_plausible_1_20 += 1
        if number > ODDS_MAX:
            count_very_large += 1

    total_rows = len(rows)
    sorted_numbers = sorted(numeric_values)
    non_empty_rate = round(non_empty / total_rows * 100.0, 2) if total_rows else 0.0
    numeric_rate = round(numeric_count / non_empty * 100.0, 2) if non_empty else 0.0
    plausible_rate = count_plausible_1_100 / numeric_count if numeric_count else 0.0
    typical_rate = count_plausible_1_20 / numeric_count if numeric_count else 0.0
    bad_small_rate = (count_le_zero + count_between_zero_one) / numeric_count if numeric_count else 0.0

    if non_empty == 0 or (total_rows >= 10 and non_empty / total_rows <= MOSTLY_EMPTY_RATE):
        verdict = "mostly_empty"
        reason = "Colonne majoritairement vide: couverture insuffisante pour une closing line."
    elif numeric_count / max(non_empty, 1) < 0.50:
        verdict = "text_or_code"
        reason = "Les valeurs non vides sont surtout du texte ou des codes, pas des cotes."
    elif plausible_rate >= 0.80 and typical_rate >= 0.70 and bad_small_rate <= 0.10:
        verdict = "decimal_odds_plausible"
        reason = "La grande majorite des valeurs numeriques est dans l'intervalle des cotes decimales plausibles."
    elif numeric_count:
        verdict = "numeric_but_not_odds"
        reason = "La colonne est numerique, mais les valeurs ne ressemblent pas majoritairement a des cotes decimales."
    else:
        verdict = "unknown"
        reason = "Profil insuffisant pour conclure."

    return {
        "column": column,
        "rows_sampled": total_rows,
        "non_empty_count": non_empty,
        "non_empty_rate": non_empty_rate,
        "raw_examples": raw_examples,
        "numeric_examples": numeric_examples,
        "min": round(min(sorted_numbers), 6) if sorted_numbers else None,
        "max": round(max(sorted_numbers), 6) if sorted_numbers else None,
        "mean": round(statistics.fmean(sorted_numbers), 6) if sorted_numbers else None,
        "median": round(statistics.median(sorted_numbers), 6) if sorted_numbers else None,
        "percentiles": {
            "p01": _percentile(sorted_numbers, 1),
            "p05": _percentile(sorted_numbers, 5),
            "p50": _percentile(sorted_numbers, 50),
            "p95": _percentile(sorted_numbers, 95),
            "p99": _percentile(sorted_numbers, 99),
        },
        "count_plausible_1_100": count_plausible_1_100,
        "count_plausible_1_20": count_plausible_1_20,
        "count_le_zero": count_le_zero,
        "count_between_zero_one": count_between_zero_one,
        "count_very_large": count_very_large,
        "text_count": text_count,
        "type_distribution": {
            "empty": empty,
            "numeric": numeric_count,
            "text_or_code": text_count,
        },
        "verdict": verdict,
        "verdict_reason": reason,
    }


def _profile_columns(rows: List[Dict[str, Any]], columns: Sequence[str], max_sample_values: int) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for column in columns:
        if column not in out:
            out[column] = _column_profile(rows, column, max_sample_values=max_sample_values)
    return out


def _name_suggests_odds(name: str) -> bool:
    lower = str(name).lower()
    norm = _norm(name)
    return (
        "odd" in lower
        or "odds" in lower
        or "price" in lower
        or "book" in lower
        or "close" in lower
        or "closing" in lower
        or norm.startswith(("b365", "ps", "max", "avg", "pin"))
        or norm.startswith("c")
    )


def _name_suggests_closing(name: str) -> bool:
    lower = str(name).lower()
    norm = _norm(name)
    return (
        lower.startswith("c_")
        or "close" in lower
        or "closing" in lower
        or re.search(r"c(?:h|d|a|o|u)$", norm) is not None
        or _norm(name) in {_norm(item) for item in H2H_CLOSING_COLUMNS + TOTAL_CLOSING_COLUMNS}
    )


def _candidate_column_report(fieldnames: Sequence[str], profiles: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    likely_odds_columns: List[str] = []
    possible_closing_columns: List[str] = []
    invalid_closing_candidates: List[Dict[str, str]] = []
    ignored_columns: List[str] = []
    for name in fieldnames:
        profile = profiles.get(str(name))
        if not profile:
            ignored_columns.append(str(name))
            continue
        verdict = profile.get("verdict")
        suggests_closing = _name_suggests_closing(str(name))
        suggests_odds = _name_suggests_odds(str(name))
        if verdict == "decimal_odds_plausible" and suggests_closing:
            possible_closing_columns.append(str(name))
        elif verdict == "decimal_odds_plausible" and suggests_odds:
            likely_odds_columns.append(str(name))
        elif suggests_closing:
            invalid_closing_candidates.append({
                "column": str(name),
                "verdict": str(verdict),
                "reason": str(profile.get("verdict_reason") or ""),
            })
        else:
            ignored_columns.append(str(name))
    return {
        "likely_odds_columns": sorted(set(likely_odds_columns)),
        "possible_closing_columns": sorted(set(possible_closing_columns)),
        "invalid_closing_candidates": invalid_closing_candidates,
        "ignored_columns_count": len(ignored_columns),
    }


def _validated_columns(columns: Sequence[str], profiles: Dict[str, Dict[str, Any]]) -> List[str]:
    return [column for column in columns if (profiles.get(column) or {}).get("verdict") == "decimal_odds_plausible"]


def _decimal_odds_plausible(profiles: Dict[str, Dict[str, Any]], columns: Sequence[str]) -> bool:
    return any((profiles.get(column) or {}).get("verdict") == "decimal_odds_plausible" for column in columns)


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


def _availability(*flags: bool) -> str:
    count = sum(1 for flag in flags if flag)
    if count == 0:
        return "none"
    if count == len(flags):
        return "complete"
    return "partial"


def probe_csv(
    csv_path: str,
    sample_rows: int = 5000,
    profile_columns: Optional[Sequence[str]] = None,
    max_sample_values: int = 10,
) -> Dict[str, Any]:
    path = Path(csv_path)
    if not path.exists():
        return {
            "generated_at": now_iso(),
            "csv_path": str(path),
            "status": "erreur",
            "error": f"Fichier introuvable: {csv_path}",
            "closing_available": False,
            "h2h_closing_available": "none",
            "h2h_home_closing_available": False,
            "h2h_draw_closing_available": False,
            "h2h_away_closing_available": False,
            "total_closing_available": "none",
            "btts_closing_available": "none",
            "detected_columns": {},
            "column_profiles": {},
            "candidate_column_report": {},
            "validated_closing_columns": [],
            "rejected_closing_columns": {},
            "missing_columns": list(H2H_CLOSING_COLUMNS[:3]),
            "recommended_mapping": {},
            "recommended_mapping_by_name": {},
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
    h2h_home = _present(fieldnames, H2H_HOME_COLUMNS)
    h2h_draw = _present(fieldnames, H2H_DRAW_COLUMNS)
    h2h_away = _present(fieldnames, H2H_AWAY_COLUMNS)
    h2h_opening = _present(fieldnames, H2H_OPENING_COLUMNS)
    total_closing = _present(fieldnames, TOTAL_CLOSING_COLUMNS)
    total_over = _present(fieldnames, TOTAL_OVER_COLUMNS)
    total_under = _present(fieldnames, TOTAL_UNDER_COLUMNS)
    btts_closing = _btts_closing_columns(fieldnames)
    generic_closing = _generic_closing_columns(fieldnames)
    detected_all = sorted(set(h2h_closing + total_closing + btts_closing + generic_closing))
    requested_profiles = []
    for column in profile_columns or []:
        column = str(column).strip()
        if column:
            requested_profiles.append(column)
    all_profiles = _profile_columns(rows, fieldnames, max_sample_values=max_sample_values)
    candidate_report = _candidate_column_report(fieldnames, all_profiles)
    profile_names = sorted(set(detected_all + requested_profiles + candidate_report.get("possible_closing_columns", []) + [item["column"] for item in candidate_report.get("invalid_closing_candidates", [])]))
    column_profiles = {name: all_profiles[name] for name in profile_names if name in all_profiles}
    validated_closing_columns = _validated_columns(detected_all, all_profiles)
    rejected_closing_columns = {
        column: (all_profiles.get(column) or {}).get("verdict_reason", "Profil indisponible")
        for column in detected_all
        if column not in validated_closing_columns
    }
    for item in candidate_report.get("invalid_closing_candidates", []):
        column = str(item.get("column") or "")
        if column and column not in rejected_closing_columns:
            rejected_closing_columns[column] = str(item.get("reason") or "Profil non plausible")
    h2h_closing_validated = _validated_columns(h2h_closing, all_profiles)
    h2h_home_validated = _validated_columns(h2h_home, all_profiles)
    h2h_draw_validated = _validated_columns(h2h_draw, all_profiles)
    h2h_away_validated = _validated_columns(h2h_away, all_profiles)
    total_closing_validated = _validated_columns(total_closing, all_profiles)
    total_over_validated = _validated_columns(total_over, all_profiles)
    total_under_validated = _validated_columns(total_under, all_profiles)
    btts_closing_validated = _validated_columns(btts_closing, all_profiles)
    h2h_home_available = bool(h2h_home)
    h2h_draw_available = bool(h2h_draw)
    h2h_away_available = bool(h2h_away)
    h2h_available = _availability(h2h_home_available, h2h_draw_available, h2h_away_available)
    total_available = _availability(bool(total_over), bool(total_under))
    btts_available = "partial" if btts_closing else "none"
    date_info = _date_range(rows)
    warnings: List[str] = []
    if date_info.get("date_max") and date_info["date_max"] >= PINNACLE_WARNING_DATE and any(_norm(col).startswith("ps") for col in detected_all):
        warnings.append("Colonnes Pinnacle/PS detectees apres 2025-07-23: verifier la fiabilite de source avant CLV.")
    if not detected_all:
        warnings.append("Aucune colonne closing detectee dans ce CSV.")
    h2h_decimal_plausible = _decimal_odds_plausible(all_profiles, h2h_closing)
    total_decimal_plausible = _decimal_odds_plausible(all_profiles, total_closing)
    btts_decimal_plausible = _decimal_odds_plausible(all_profiles, btts_closing)
    if detected_all and not any((h2h_decimal_plausible, total_decimal_plausible, btts_decimal_plausible)):
        warnings.append("Colonnes closing detectees, mais les valeurs echantillonnees ne ressemblent pas a des cotes decimales exploitables.")
    if rejected_closing_columns:
        warnings.append("Colonnes detectees par nom mais rejetees par profil de valeurs.")
    if h2h_available == "partial":
        warnings.append("Closing H2H partiel: ne pas valider les sides non couverts, notamment le draw si C_LTD est absent.")
    if total_available != "complete":
        warnings.append("Closing Over/Under absent ou partiel: ne pas calculer de CLV total avec des colonnes H2H.")
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
        "closing_odds_usable": bool(validated_closing_columns),
        "h2h_closing_available": h2h_available,
        "h2h_home_closing_available": h2h_home_available,
        "h2h_draw_closing_available": h2h_draw_available,
        "h2h_away_closing_available": h2h_away_available,
        "h2h_closing_validated": _availability(bool(h2h_home_validated), bool(h2h_draw_validated), bool(h2h_away_validated)),
        "h2h_home_closing_validated": bool(h2h_home_validated),
        "h2h_draw_closing_validated": bool(h2h_draw_validated),
        "h2h_away_closing_validated": bool(h2h_away_validated),
        "total_closing_available": total_available,
        "total_closing_validated": _availability(bool(total_over_validated), bool(total_under_validated)),
        "btts_closing_available": btts_available,
        "btts_closing_validated": "partial" if btts_closing_validated else "none",
        "decimal_odds_plausible": {
            "h2h": h2h_decimal_plausible,
            "total": total_decimal_plausible,
            "btts": btts_decimal_plausible,
        },
        "detected_columns": {
            "h2h_closing": h2h_closing,
            "h2h_home_closing": h2h_home,
            "h2h_draw_closing": h2h_draw,
            "h2h_away_closing": h2h_away,
            "h2h_opening": h2h_opening,
            "total_closing": total_closing,
            "total_over_closing": total_over,
            "total_under_closing": total_under,
            "btts_closing": btts_closing,
            "generic_closing": generic_closing,
            "all_closing": detected_all,
        },
        "validated_closing_columns": validated_closing_columns,
        "rejected_closing_columns": rejected_closing_columns,
        "column_profiles": column_profiles,
        "candidate_column_report": candidate_report,
        "missing_columns": missing,
        "recommended_mapping": _recommended_mapping(h2h_closing_validated + _validated_columns(generic_closing, all_profiles), total_closing_validated + _validated_columns(generic_closing, all_profiles), btts_closing_validated),
        "recommended_mapping_by_name": _recommended_mapping(h2h_closing + generic_closing, total_closing + generic_closing, btts_closing),
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
    profiles = report.get("column_profiles") or {}
    profile_rows = []
    for column, profile in profiles.items():
        profile_rows.append(
            "<tr>"
            f"<td>{html.escape(str(column))}</td>"
            f"<td>{html.escape(str(profile.get('verdict')))}</td>"
            f"<td>{profile.get('non_empty_count')}</td>"
            f"<td>{profile.get('non_empty_rate')}%</td>"
            f"<td>{profile.get('min')}</td>"
            f"<td>{profile.get('max')}</td>"
            f"<td>{profile.get('median')}</td>"
            f"<td>{profile.get('count_plausible_1_100')}</td>"
            f"<td>{profile.get('count_between_zero_one')}</td>"
            f"<td>{html.escape(str(profile.get('verdict_reason')))}</td>"
            "</tr>"
        )
    candidates = report.get("candidate_column_report") or {}
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
        f"<tr><th>Home closing</th><td>{report.get('h2h_home_closing_available')}</td></tr>",
        f"<tr><th>Draw closing</th><td>{report.get('h2h_draw_closing_available')}</td></tr>",
        f"<tr><th>Away closing</th><td>{report.get('h2h_away_closing_available')}</td></tr>",
        f"<tr><th>Total closing</th><td>{report.get('total_closing_available')}</td></tr>",
        f"<tr><th>BTTS closing</th><td>{report.get('btts_closing_available')}</td></tr>",
        f"<tr><th>Closing utilisable comme cotes</th><td>{report.get('closing_odds_usable')}</td></tr>",
        f"<tr><th>Colonnes validees</th><td>{html.escape(', '.join(report.get('validated_closing_columns') or []))}</td></tr>",
        f"<tr><th>Colonnes rejetees</th><td>{html.escape(', '.join((report.get('rejected_closing_columns') or {}).keys()))}</td></tr>",
        f"<tr><th>Colonnes H2H</th><td>{html.escape(', '.join(detected.get('h2h_closing') or []))}</td></tr>",
        f"<tr><th>Colonnes total</th><td>{html.escape(', '.join(detected.get('total_closing') or []))}</td></tr>",
        f"<tr><th>Closing plausibles recommandees</th><td>{html.escape(', '.join(candidates.get('possible_closing_columns') or []))}</td></tr>",
        "</tbody></table>",
        "<h2>Profils de colonnes suspectes</h2>",
        "<table><thead><tr><th>Colonne</th><th>Verdict</th><th>Non vides</th><th>Coverage</th><th>Min</th><th>Max</th><th>Mediane</th><th>1.01-100</th><th>0-1</th><th>Raison</th></tr></thead><tbody>",
        *profile_rows,
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
    print(f"- H2H home closing: {report.get('h2h_home_closing_available')}")
    print(f"- H2H draw closing: {report.get('h2h_draw_closing_available')}")
    print(f"- H2H away closing: {report.get('h2h_away_closing_available')}")
    print(f"- Total closing disponible: {report.get('total_closing_available')}")
    print(f"- BTTS closing disponible: {report.get('btts_closing_available')}")
    print(f"- Colonnes closing detectees: {', '.join(detected.get('all_closing') or []) or 'aucune'}")
    print(f"- Colonnes closing validees comme cotes: {', '.join(report.get('validated_closing_columns') or []) or 'aucune'}")
    rejected = report.get("rejected_closing_columns") or {}
    if rejected:
        print(f"- Colonnes closing rejetees: {', '.join(rejected.keys())}")
    print(f"- Mapping recommande: {report.get('recommended_mapping')}")
    for column, profile in (report.get("column_profiles") or {}).items():
        print(
            f"- Profil {column}: verdict={profile.get('verdict')}, "
            f"non_vides={profile.get('non_empty_count')} ({profile.get('non_empty_rate')}%), "
            f"min={profile.get('min')}, mediane={profile.get('median')}, max={profile.get('max')}, "
            f"plausibles_1_100={profile.get('count_plausible_1_100')}, entre_0_1={profile.get('count_between_zero_one')}"
        )
        if profile.get("raw_examples"):
            print(f"  Exemples bruts: {profile.get('raw_examples')}")
        if profile.get("numeric_examples"):
            print(f"  Exemples numeriques: {profile.get('numeric_examples')}")
        print(f"  Raison: {profile.get('verdict_reason')}")
    for warning in report.get("warnings") or []:
        print(f"- Avertissement: {warning}")
    print("- Ce rapport ne calcule pas la CLV, il verifie seulement la disponibilite des colonnes.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Inspecte un CSV source pour les colonnes closing odds, sans modifier le fichier.")
    parser.add_argument("--csv", required=True, help="CSV source a inspecter, ex: data/MATCHES.csv")
    parser.add_argument("--sample-rows", type=int, default=5000, help="Nombre de lignes a echantillonner")
    parser.add_argument("--sample-values", action="store_true", help="Afficher les exemples bruts/numeriques des colonnes suspectes")
    parser.add_argument("--max-sample", type=int, default=50, help="Nombre maximum d'exemples par colonne profilee")
    parser.add_argument("--column", action="append", default=[], help="Colonne precise a profiler, option repetable")
    parser.add_argument("--profile-columns", default="", help="Liste de colonnes a profiler, separees par des virgules")
    parser.add_argument("--output", default="", help="Rapport JSON dans reports/")
    parser.add_argument("--html", default="", help="Rapport HTML dans reports/")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        requested_columns = list(args.column or [])
        if args.profile_columns:
            requested_columns.extend([item.strip() for item in args.profile_columns.split(",") if item.strip()])
        max_sample_values = args.max_sample if args.sample_values or requested_columns else 10
        report = probe_csv(args.csv, sample_rows=args.sample_rows, profile_columns=requested_columns, max_sample_values=max_sample_values)
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
