import argparse
import csv
import html
import json
import statistics
from pathlib import Path
from typing import Any, Dict, Iterable, List

from shadow_ledger import read_ledger


def ensure_reports_path(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le rapport shadow CLV ne doit pas etre ecrit dans data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _float(value: Any):
    try:
        return float(str(value).strip().replace(",", "."))
    except Exception:
        return None


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "oui", "y"}


def _clv_decimal(row: Dict[str, str]):
    direct = _float(row.get("clv"))
    if direct is not None:
        return direct
    pct = _float(row.get("clv_pct"))
    if pct is not None:
        return pct / 100.0
    legacy = _float(row.get("clv_percent"))
    if legacy is not None and (_truthy(row.get("clv_available")) or str(row.get("closing_odds") or "").strip()):
        return legacy
    return None


def _has_closing(row: Dict[str, str]) -> bool:
    status = str(row.get("closing_status") or "").strip().lower()
    return status == "captured" or bool(str(row.get("closing_odds") or "").strip())


def _closing_status(row: Dict[str, str]) -> str:
    status = str(row.get("closing_status") or "").strip().lower()
    if status:
        return status
    return "captured" if _has_closing(row) else "missing"


def _closing_quality(row: Dict[str, str]) -> str:
    quality = str(row.get("closing_quality") or "").strip()
    if quality:
        return quality
    if _has_closing(row):
        return "manual_unverified"
    return "unavailable"


def _counts(values: Iterable[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for value in values:
        key = str(value or "inconnu").strip() or "inconnu"
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items(), key=lambda item: (-item[1], item[0])))


def _median(values: List[float]):
    return round(statistics.median(values), 6) if values else None


def _max_drawdown(profits: List[float]) -> float:
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for profit in profits:
        cumulative += profit
        peak = max(peak, cumulative)
        max_dd = min(max_dd, cumulative - peak)
    return round(max_dd, 6)


def _profit(row: Dict[str, str]):
    result = str(row.get("result") or "").lower()
    odds = _float(row.get("taken_odds"))
    if odds is None or result not in {"win", "loss", "push", "void"}:
        return None
    if result == "win":
        return odds - 1.0
    if result == "loss":
        return -1.0
    return 0.0


def _split_status(sample: int, clvs: List[float], roi: Any) -> str:
    if sample <= 0:
        return "insufficient_sample"
    if not clvs:
        return "clv_missing"
    clv_mean = sum(clvs) / len(clvs)
    if clv_mean <= 0:
        return "clv_negative"
    if sample < 1000:
        return "watchlist" if roi is not None and roi > 0 else "observation"
    if roi is not None and roi > 0:
        return "watchlist"
    return "observation"


def _group_stats(rows: Iterable[Dict[str, str]], key: str) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get(key) or "inconnu"), []).append(row)
    out: Dict[str, Dict[str, Any]] = {}
    for group, items in grouped.items():
        clvs = [_clv_decimal(item) for item in items if _clv_decimal(item) is not None]
        clvs = [value for value in clvs if value is not None]
        profits = [_profit(item) for item in items]
        profits = [value for value in profits if value is not None]
        roi = round(sum(profits) / len(profits) * 100.0, 2) if profits else None
        out[group] = {
            "n": len(items),
            "with_clv": len(clvs),
            "coverage": round(len(clvs) / len(items) * 100.0, 2) if items else 0.0,
            "clv_mean": round(sum(clvs) / len(clvs), 6) if clvs else None,
            "clv_median": _median(clvs),
            "clv_positive_rate": round(sum(1 for value in clvs if value > 0) / len(clvs) * 100.0, 2) if clvs else None,
            "profit": round(sum(profits), 6) if profits else None,
            "roi": roi,
            "max_drawdown": _max_drawdown(profits) if profits else None,
            "status": _split_status(len(items), clvs, roi),
        }
    return out


def _month(row: Dict[str, str]) -> str:
    return str(row.get("match_date") or "")[:7] or "inconnu"


def build_shadow_clv_report(ledger_path: str) -> Dict[str, Any]:
    rows = read_ledger(ledger_path)
    clvs = [_clv_decimal(row) for row in rows if _clv_decimal(row) is not None]
    clvs = [value for value in clvs if value is not None]
    profits = [_profit(row) for row in rows]
    profits = [value for value in profits if value is not None]
    wins = sum(1 for row in rows if str(row.get("result") or "").lower() == "win")
    losses = sum(1 for row in rows if str(row.get("result") or "").lower() == "loss")
    settled = wins + losses + sum(1 for row in rows if str(row.get("result") or "").lower() == "push")
    signals_with_closing = sum(1 for row in rows if _has_closing(row))
    pending_closing = sum(1 for row in rows if not _has_closing(row))
    overdue_missing = sum(1 for row in rows if _closing_status(row) == "overdue_missing")
    pending_results = sum(1 for row in rows if str(row.get("result") or "unknown").lower() == "unknown")
    clv_mean = round(sum(clvs) / len(clvs), 6) if clvs else None
    roi = round(sum(profits) / len(profits) * 100.0, 2) if profits else None
    closing_rows = [
        {
            "shadow_id": row.get("shadow_id"),
            "match_date": row.get("match_date"),
            "league": row.get("league"),
            "match": f"{row.get('home_team') or ''} - {row.get('away_team') or ''}".strip(),
            "market_type": row.get("market_type"),
            "side": row.get("side"),
            "taken_odds": row.get("taken_odds"),
            "closing_odds": row.get("closing_odds"),
            "closing_bookmaker": row.get("closing_bookmaker") or row.get("bookmaker"),
            "closing_quality": _closing_quality(row),
            "closing_status": _closing_status(row),
            "clv": _clv_decimal(row),
        }
        for row in rows
        if _has_closing(row)
    ]
    warnings: List[str] = []
    if len(rows) < 100:
        warnings.append("sample <30: bruit extreme") if len(rows) < 30 else None
        warnings.append("sample <100: preuve shadow tres insuffisante")
    if len(rows) < 500:
        warnings.append("sample <500: observation seulement")
    if len(rows) < 1000:
        warnings.append("sample <1000: promotion impossible")
    if not clvs:
        warnings.append("CLV absente: non valide")
    if clv_mean is not None and clv_mean <= 0:
        warnings.append("CLV negative ou nulle: signal shadow bloque")
    if roi is not None and roi > 0 and clv_mean is not None and clv_mean <= 0:
        warnings.append("ROI positif mais CLV negative: probablement bruit court terme")
    if roi is not None and roi < 0 and clv_mean is not None and clv_mean > 0:
        warnings.append("CLV positive mais ROI court terme negatif: observation seulement")
    if not clvs:
        verdict = "not_validated"
    elif len(rows) < 1000:
        verdict = "not_validated" if clv_mean is None or clv_mean <= 0 else "observation_only"
    elif clv_mean is not None and clv_mean <= 0:
        verdict = "clv_negative"
    elif roi is not None and roi > 0 and clv_mean and clv_mean > 0:
        verdict = "deep_analysis_candidate"
    else:
        verdict = "observation_only"
    rows_by_month = []
    for row in rows:
        item = dict(row)
        item["_month"] = _month(row)
        rows_by_month.append(item)
    return {
        "ledger": ledger_path,
        "signals_total": len(rows),
        "signals_with_closing": signals_with_closing,
        "signals_with_clv": len(clvs),
        "signals_with_closing_details": closing_rows,
        "pending_closing": pending_closing,
        "overdue_missing": overdue_missing,
        "pending_results": pending_results,
        "clv_coverage": round(len(clvs) / len(rows) * 100.0, 2) if rows else 0.0,
        "clv_mean": clv_mean,
        "clv_median": _median(clvs),
        "clv_positive_rate": round(sum(1 for value in clvs if value > 0) / len(clvs) * 100.0, 2) if clvs else None,
        "closing_quality_breakdown": _counts(_closing_quality(row) for row in rows),
        "closing_status_breakdown": _counts(_closing_status(row) for row in rows),
        "clv_by_league": _group_stats(rows, "league"),
        "clv_by_market": _group_stats(rows, "market_type"),
        "clv_by_side": _group_stats(rows, "side"),
        "clv_by_strategy": _group_stats(rows, "strategy_name"),
        "clv_by_confidence": _group_stats(rows, "confidence_label"),
        "clv_by_bookmaker": _group_stats(rows, "bookmaker"),
        "clv_by_month": _group_stats(rows_by_month, "_month"),
        "roi": roi,
        "profit": round(sum(profits), 6) if profits else None,
        "settled_signals": settled,
        "winrate": round(wins / (wins + losses) * 100.0, 2) if wins + losses else None,
        "drawdown": _max_drawdown(profits) if profits else None,
        "sample_size": len(rows),
        "warnings": warnings,
        "verdict": verdict,
        "lab_only": True,
        "can_influence_picks": False,
        "message": "Observation shadow seulement: aucune mise automatique, aucune recommandation de mise.",
    }


def write_summary_csv(report: Dict[str, Any], path: str) -> Path:
    target = ensure_reports_path(path)
    rows = []
    for split_name in ["clv_by_league", "clv_by_market", "clv_by_side", "clv_by_strategy", "clv_by_confidence", "clv_by_bookmaker", "clv_by_month"]:
        for key, stats in (report.get(split_name) or {}).items():
            rows.append({
                "split": split_name,
                "value": key,
                **stats,
            })
    fieldnames = ["split", "value", "n", "with_clv", "coverage", "clv_mean", "clv_median", "clv_positive_rate", "profit", "roi", "max_drawdown", "status"]
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return target


def write_json(report: Dict[str, Any], path: str) -> Path:
    target = ensure_reports_path(path)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], path: str) -> Path:
    target = ensure_reports_path(path)
    warnings = "".join(f"<li>{html.escape(str(item))}</li>" for item in report.get("warnings") or [])
    quality = "".join(
        f"<li>{html.escape(str(key))}: {value}</li>"
        for key, value in (report.get("closing_quality_breakdown") or {}).items()
    )
    status = "".join(
        f"<li>{html.escape(str(key))}: {value}</li>"
        for key, value in (report.get("closing_status_breakdown") or {}).items()
    )
    target.write_text("\n".join([
        "<!doctype html>",
        "<html lang='fr'><head><meta charset='utf-8'>",
        "<title>Shadow CLV Report</title>",
        "<style>body{font-family:Arial,sans-serif;margin:32px;color:#1f2933}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px;text-align:left}th{background:#f3f4f6}.warn{background:#fff7ed;border:1px solid #fed7aa;padding:12px;border-radius:6px}</style>",
        "</head><body>",
        "<h1>Shadow CLV Report</h1>",
        f"<p>{html.escape(str(report.get('message')))}</p>",
        "<table><tbody>",
        f"<tr><th>Signaux</th><td>{report.get('signals_total')}</td></tr>",
        f"<tr><th>Avec closing</th><td>{report.get('signals_with_closing')}</td></tr>",
        f"<tr><th>Pending closing</th><td>{report.get('pending_closing')}</td></tr>",
        f"<tr><th>Overdue missing</th><td>{report.get('overdue_missing')}</td></tr>",
        f"<tr><th>Pending resultats</th><td>{report.get('pending_results')}</td></tr>",
        f"<tr><th>Coverage CLV</th><td>{report.get('clv_coverage')}%</td></tr>",
        f"<tr><th>CLV moyenne</th><td>{report.get('clv_mean')}</td></tr>",
        f"<tr><th>CLV mediane</th><td>{report.get('clv_median')}</td></tr>",
        f"<tr><th>CLV positive</th><td>{report.get('clv_positive_rate')}%</td></tr>",
        f"<tr><th>ROI</th><td>{report.get('roi')}</td></tr>",
        f"<tr><th>Profit unite</th><td>{report.get('profit')}</td></tr>",
        f"<tr><th>Max drawdown</th><td>{report.get('drawdown')}</td></tr>",
        f"<tr><th>Verdict</th><td>{html.escape(str(report.get('verdict')))}</td></tr>",
        "</tbody></table>",
        f"<section><h2>Closing quality</h2><ul>{quality or '<li>Aucun</li>'}</ul></section>",
        f"<section><h2>Closing status</h2><ul>{status or '<li>Aucun</li>'}</ul></section>",
        f"<section class='warn'><h2>Avertissements</h2><ul>{warnings}</ul></section>",
        "<p>Aucun Telegram, aucune mise, aucun pick automatique.</p>",
        "</body></html>",
    ]), encoding="utf-8")
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Shadow CLV Report Oracle Bot")
    print(f"- Ledger: {report.get('ledger')}")
    print(f"- Signaux shadow: {report.get('signals_total')}")
    print(f"- Signaux avec closing odds: {report.get('signals_with_closing')}")
    print(f"- Pending closing: {report.get('pending_closing')}")
    print(f"- Overdue missing: {report.get('overdue_missing')}")
    print(f"- Pending resultats: {report.get('pending_results')}")
    print(f"- Coverage CLV: {report.get('clv_coverage')}%")
    print(f"- CLV moyenne: {report.get('clv_mean')}")
    print(f"- CLV mediane: {report.get('clv_median')}")
    print(f"- CLV positive: {report.get('clv_positive_rate')}%")
    print(f"- Breakdown closing_quality: {json.dumps(report.get('closing_quality_breakdown'), ensure_ascii=False)}")
    print(f"- Breakdown closing_status: {json.dumps(report.get('closing_status_breakdown'), ensure_ascii=False)}")
    print(f"- ROI resultats disponibles: {report.get('roi')}")
    print(f"- Profit unite: {report.get('profit')}")
    print(f"- Winrate: {report.get('winrate')}")
    print(f"- Drawdown: {report.get('drawdown')}")
    print(f"- Verdict: {report.get('verdict')}")
    for warning in report.get("warnings") or []:
        print(f"- Avertissement: {warning}")
    print("- Observation shadow seulement: aucune mise, aucun pick automatique.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Analyse le shadow ledger avec CLV manuelle.")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    parser.add_argument("--summary-csv", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = build_shadow_clv_report(args.ledger)
        if args.output:
            path = write_json(report, args.output)
            print(f"- Rapport JSON shadow CLV ecrit: {path}")
        if args.html:
            path = write_html(report, args.html)
            print(f"- Rapport HTML shadow CLV ecrit: {path}")
        if args.summary_csv:
            path = write_summary_csv(report, args.summary_csv)
            print(f"- Resume CSV shadow CLV ecrit: {path}")
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
