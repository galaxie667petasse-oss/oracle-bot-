import argparse
import csv
import html
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


CLOSING_GENERIC_COLUMNS = (
    "closing_odds",
    "close_odds",
    "closing_price",
    "closing_decimal_odds",
    "pinnacle_closing_odds",
)

HOME_CLOSING_COLUMNS = ("C_LTH", "C_VHD", "C_HTB", "C_PHB", "closing_home_odds", "close_home")
AWAY_CLOSING_COLUMNS = ("C_LTA", "C_VAD", "C_ATB", "C_PHA", "closing_away_odds", "close_away")
DRAW_CLOSING_COLUMNS = ("C_LTD", "C_VDD", "C_DTB", "C_PHD", "closing_draw_odds", "close_draw")
OVER_CLOSING_COLUMNS = ("C_LTO", "C_VHO", "C_OTB", "C_PHO", "closing_over_odds", "close_over")
UNDER_CLOSING_COLUMNS = ("C_LTU", "C_VHU", "C_UTB", "C_PHU", "closing_under_odds", "close_under")

PINNACLE_DATE_WARNING = "2025-07-23"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def parse_float(value: Any) -> Optional[float]:
    text = str(value or "").strip().replace(",", ".")
    if not text or text.lower() in {"na", "n/a", "nan", "none", "null", "-"}:
        return None
    try:
        number = float(text)
    except Exception:
        return None
    if not math.isfinite(number) or number <= 1.0:
        return None
    return number


def implied_probability(odds: float) -> Optional[float]:
    if odds <= 1.0:
        return None
    return 1.0 / odds


def odds_bucket(odds: float) -> str:
    if odds < 1.50:
        return "<1.50"
    if odds < 1.80:
        return "1.50-1.79"
    if odds < 2.20:
        return "1.80-2.19"
    if odds < 3.00:
        return "2.20-2.99"
    return ">=3.00"


def year_from_row(row: Dict[str, Any]) -> str:
    value = str(row.get("year") or "").strip()
    if value:
        return value[:4]
    date = str(row.get("date") or row.get("date_key") or "").strip()
    return date[:4] if len(date) >= 4 else "inconnue"


def normalize_columns(fieldnames: Iterable[str]) -> Dict[str, str]:
    return {str(name).lower(): str(name) for name in fieldnames}


def first_present(fieldnames: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    normalized = normalize_columns(fieldnames)
    for candidate in candidates:
        if candidate.lower() in normalized:
            return normalized[candidate.lower()]
    return None


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "oui", "y"}


def infer_side(row: Dict[str, Any]) -> str:
    market = str(row.get("market_type") or "").lower()
    pari = str(row.get("pari") or "").lower()
    home = str(row.get("home") or row.get("home_team") or "").lower()
    away = str(row.get("away") or row.get("away_team") or "").lower()
    if truthy(row.get("is_home_pick")) or (home and home in pari):
        return "home"
    if truthy(row.get("is_away_pick")) or (away and away in pari):
        return "away"
    if truthy(row.get("is_draw")) or market == "draw" or "draw" in pari or "nul" in pari:
        return "draw"
    if truthy(row.get("is_over")) or "over" in pari or "plus" in pari:
        return "over"
    if truthy(row.get("is_under")) or "under" in pari or "moins" in pari:
        return "under"
    return ""


def closing_column_for_row(row: Dict[str, Any], fieldnames: Sequence[str]) -> Optional[str]:
    generic = first_present(fieldnames, CLOSING_GENERIC_COLUMNS)
    if generic:
        return generic
    source_column = str(row.get("closing_odds_column") or row.get("odds_source_column") or "").strip()
    if source_column and source_column in row and parse_float(row.get(source_column)) is not None:
        return source_column
    side = infer_side(row)
    if side == "home":
        return first_present(fieldnames, HOME_CLOSING_COLUMNS)
    if side == "away":
        return first_present(fieldnames, AWAY_CLOSING_COLUMNS)
    if side == "draw":
        return first_present(fieldnames, DRAW_CLOSING_COLUMNS)
    if side == "over":
        return first_present(fieldnames, OVER_CLOSING_COLUMNS)
    if side == "under":
        return first_present(fieldnames, UNDER_CLOSING_COLUMNS)
    return None


def detect_closing_columns(fieldnames: Sequence[str]) -> List[str]:
    candidates = set(CLOSING_GENERIC_COLUMNS + HOME_CLOSING_COLUMNS + AWAY_CLOSING_COLUMNS + DRAW_CLOSING_COLUMNS + OVER_CLOSING_COLUMNS + UNDER_CLOSING_COLUMNS)
    out = []
    for name in fieldnames:
        if name in candidates or name.upper().startswith("C_"):
            out.append(name)
    return sorted(out)


def is_recent_pinnacle(row: Dict[str, Any], closing_column: str) -> bool:
    date = str(row.get("date") or row.get("date_key") or "").strip()[:10]
    if date < PINNACLE_DATE_WARNING:
        return False
    joined = " ".join(str(row.get(key) or "") for key in ("bookmaker", "odds_source", "closing_source", "odds_source_column"))
    return "pinnacle" in joined.lower() or closing_column.upper().startswith("C_P")


def new_accumulator() -> Dict[str, Any]:
    return {
        "n": 0,
        "clv_absolute_sum": 0.0,
        "clv_percent_sum": 0.0,
        "clv_prob_edge_sum": 0.0,
        "positive": 0,
        "values": [],
    }


def add_value(acc: Dict[str, Any], clv_absolute: float, clv_percent: float, clv_prob_edge: float) -> None:
    acc["n"] += 1
    acc["clv_absolute_sum"] += clv_absolute
    acc["clv_percent_sum"] += clv_percent
    acc["clv_prob_edge_sum"] += clv_prob_edge
    acc["positive"] += 1 if clv_percent > 0 else 0
    acc["values"].append(clv_percent)


def finalize_acc(acc: Dict[str, Any]) -> Dict[str, Any]:
    n = int(acc.get("n") or 0)
    if n <= 0:
        return {"n": 0, "clv_mean": None, "clv_median": None, "clv_positive_rate": None, "clv_absolute_mean": None, "clv_prob_edge_mean": None}
    values = sorted(acc["values"])
    median = values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2.0
    return {
        "n": n,
        "clv_mean": round(acc["clv_percent_sum"] / n, 6),
        "clv_median": round(median, 6),
        "clv_positive_rate": round(acc["positive"] / n * 100.0, 2),
        "clv_absolute_mean": round(acc["clv_absolute_sum"] / n, 6),
        "clv_prob_edge_mean": round(acc["clv_prob_edge_sum"] / n, 6),
    }


def finalize_groups(groups: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {key: finalize_acc(value) for key, value in sorted(groups.items())}


def clv_verdict(summary: Dict[str, Any]) -> str:
    if not summary or not summary.get("n"):
        return "indisponible"
    mean = summary.get("clv_mean") or 0.0
    rate = summary.get("clv_positive_rate") or 0.0
    n = summary.get("n") or 0
    if mean > 0.005 and rate >= 55.0 and n >= 1000:
        return "CLV positif robuste"
    if mean > 0.0 and rate >= 50.0:
        return "CLV faible"
    if mean <= 0.0:
        return "CLV negatif"
    return "CLV faible"


def analyze_clv(features_path: str) -> Dict[str, Any]:
    path = Path(features_path)
    if not path.exists():
        return {
            "generated_at": now_iso(),
            "features_path": str(path),
            "status": "indisponible",
            "message": f"Fichier introuvable: {features_path}",
            "verdict": "indisponible",
            "warnings": [],
        }
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        closing_columns = detect_closing_columns(fieldnames)
        if not closing_columns and not first_present(fieldnames, CLOSING_GENERIC_COLUMNS):
            return {
                "generated_at": now_iso(),
                "features_path": str(path),
                "status": "indisponible",
                "message": "Closing odds indisponibles dans ce fichier : rapport CLV impossible, utiliser export enrichi avec colonnes C_*.",
                "closing_columns_detected": [],
                "rows_total": 0,
                "rows_with_closing": 0,
                "summary": finalize_acc(new_accumulator()),
                "groups": {},
                "verdict": "indisponible",
                "warnings": [],
            }
        total = 0
        used = 0
        warnings: List[str] = []
        warning_recent_pinnacle = False
        global_acc = new_accumulator()
        by_market: Dict[str, Dict[str, Any]] = {}
        by_bucket: Dict[str, Dict[str, Any]] = {}
        by_year: Dict[str, Dict[str, Any]] = {}
        by_strategy: Dict[str, Dict[str, Any]] = {}
        for row in reader:
            total += 1
            taken_odds = parse_float(row.get("odds") or row.get("taken_odds"))
            if taken_odds is None:
                continue
            closing_column = closing_column_for_row(row, fieldnames)
            if not closing_column:
                continue
            closing_odds = parse_float(row.get(closing_column))
            if closing_odds is None:
                continue
            used += 1
            clv_absolute = closing_odds - taken_odds
            clv_percent = taken_odds / closing_odds - 1.0
            taken_prob = implied_probability(taken_odds) or 0.0
            closing_prob = implied_probability(closing_odds) or 0.0
            clv_prob_edge = closing_prob - taken_prob
            add_value(global_acc, clv_absolute, clv_percent, clv_prob_edge)
            for groups, key in (
                (by_market, str(row.get("market_type") or "inconnu")),
                (by_bucket, odds_bucket(taken_odds)),
                (by_year, year_from_row(row)),
            ):
                groups.setdefault(key, new_accumulator())
                add_value(groups[key], clv_absolute, clv_percent, clv_prob_edge)
            strategy = str(row.get("strategy_name") or "").strip()
            if strategy:
                by_strategy.setdefault(strategy, new_accumulator())
                add_value(by_strategy[strategy], clv_absolute, clv_percent, clv_prob_edge)
            if is_recent_pinnacle(row, closing_column):
                warning_recent_pinnacle = True
        summary = finalize_acc(global_acc)
        if used == 0:
            status = "indisponible"
            message = "Closing odds detectees mais aucune ligne exploitable : verifier le mapping des cotes closing et du cote joue."
        else:
            status = "disponible"
            message = "Rapport CLV descriptif genere. Une CLV positive ne suffit jamais sans validation statistique complete."
        if warning_recent_pinnacle:
            warnings.append("Attention: source closing Pinnacle recente detectee apres 2025-07-23; ne pas surinterpreter cette CLV sans controle de source.")
        warnings.append("Convention: prendre 2.10 quand la closing line finit a 2.00 est positif; prendre 1.90 contre 2.00 est negatif.")
        return {
            "generated_at": now_iso(),
            "features_path": str(path),
            "status": status,
            "message": message,
            "closing_columns_detected": closing_columns,
            "rows_total": total,
            "rows_with_closing": used,
            "summary": summary,
            "groups": {
                "by_market": finalize_groups(by_market),
                "by_odds_bucket": finalize_groups(by_bucket),
                "by_year": finalize_groups(by_year),
                "by_strategy": finalize_groups(by_strategy),
            },
            "verdict": clv_verdict(summary),
            "warnings": warnings,
        }


def write_json(report: Dict[str, Any], path: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], path: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    summary = report.get("summary") or {}
    rows = []
    for group_name, group in (report.get("groups") or {}).items():
        for key, stat in (group or {}).items():
            rows.append(
                "<tr>"
                f"<td>{html.escape(group_name)}</td>"
                f"<td>{html.escape(str(key))}</td>"
                f"<td>{stat.get('n')}</td>"
                f"<td>{stat.get('clv_mean')}</td>"
                f"<td>{stat.get('clv_positive_rate')}</td>"
                "</tr>"
            )
    target.write_text("\n".join([
        "<!doctype html>",
        "<html lang='fr'><head><meta charset='utf-8'>",
        "<title>Rapport CLV Oracle Bot</title>",
        "<style>body{font-family:Arial,sans-serif;margin:32px;color:#1f2933}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px;text-align:left}th{background:#f3f4f6}.warn{background:#fff7ed;border:1px solid #fed7aa;padding:12px;border-radius:6px}</style>",
        "</head><body>",
        "<h1>CLV / Closing Line Value</h1>",
        f"<p>Statut: {html.escape(str(report.get('status')))}. Verdict: {html.escape(str(report.get('verdict')))}.</p>",
        f"<p>{html.escape(str(report.get('message') or ''))}</p>",
        "<ul>",
        f"<li>Lignes avec closing: {summary.get('n')}</li>",
        f"<li>CLV moyenne: {summary.get('clv_mean')}</li>",
        f"<li>CLV mediane: {summary.get('clv_median')}</li>",
        f"<li>% CLV positive: {summary.get('clv_positive_rate')}</li>",
        "</ul>",
        "<section class='warn'><h2>Warnings</h2><ul>",
        *[f"<li>{html.escape(str(item))}</li>" for item in report.get("warnings") or []],
        "</ul></section>",
        "<h2>Groupes</h2><table><thead><tr><th>Groupe</th><th>Cle</th><th>n</th><th>CLV moyenne</th><th>% positive</th></tr></thead><tbody>",
        *rows,
        "</tbody></table>",
        "<p>Rapport descriptif seulement: aucun pick Telegram, aucune DB, aucun staking.</p>",
        "</body></html>",
    ]), encoding="utf-8")
    return target


def print_report(report: Dict[str, Any]) -> None:
    summary = report.get("summary") or {}
    print("Rapport CLV Oracle Bot")
    print(f"- Statut: {report.get('status')}")
    print(f"- Message: {report.get('message')}")
    print(f"- Lignes exploitees: {summary.get('n')}")
    print(f"- CLV moyenne: {summary.get('clv_mean')}")
    print(f"- CLV mediane: {summary.get('clv_median')}")
    print(f"- CLV positive: {summary.get('clv_positive_rate')}%")
    print(f"- Verdict: {report.get('verdict')}")
    for warning in report.get("warnings") or []:
        print(f"- Avertissement: {warning}")
    print("- Aucun pick Telegram et aucune modification DB.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Analyse CLV locale et descriptive, sans pick automatique.")
    parser.add_argument("--features", required=True, help="CSV de features ou export enrichi avec cotes closing")
    parser.add_argument("--output", default="", help="Rapport JSON a ecrire")
    parser.add_argument("--html", default="", help="Rapport HTML a ecrire")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    report = analyze_clv(args.features)
    if args.output:
        path = write_json(report, args.output)
        print(f"- Rapport JSON CLV ecrit: {path}")
    if args.html:
        path = write_html(report, args.html)
        print(f"- Rapport HTML CLV ecrit: {path}")
    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
