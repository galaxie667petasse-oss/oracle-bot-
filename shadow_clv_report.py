import argparse
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
    if odds is None or result not in {"win", "loss", "push"}:
        return None
    if result == "win":
        return odds - 1.0
    if result == "loss":
        return -1.0
    return 0.0


def _group_stats(rows: Iterable[Dict[str, str]], key: str) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get(key) or "inconnu"), []).append(row)
    out: Dict[str, Dict[str, Any]] = {}
    for group, items in grouped.items():
        clvs = [_float(item.get("clv_percent")) for item in items if _truthy(item.get("clv_available"))]
        clvs = [value for value in clvs if value is not None]
        out[group] = {
            "n": len(items),
            "with_clv": len(clvs),
            "clv_mean": round(sum(clvs) / len(clvs), 6) if clvs else None,
            "clv_median": _median(clvs),
            "clv_positive_rate": round(sum(1 for value in clvs if value > 0) / len(clvs) * 100.0, 2) if clvs else None,
        }
    return out


def build_shadow_clv_report(ledger_path: str) -> Dict[str, Any]:
    rows = read_ledger(ledger_path)
    clvs = [_float(row.get("clv_percent")) for row in rows if _truthy(row.get("clv_available"))]
    clvs = [value for value in clvs if value is not None]
    profits = [_profit(row) for row in rows]
    profits = [value for value in profits if value is not None]
    wins = sum(1 for row in rows if str(row.get("result") or "").lower() == "win")
    losses = sum(1 for row in rows if str(row.get("result") or "").lower() == "loss")
    settled = wins + losses + sum(1 for row in rows if str(row.get("result") or "").lower() == "push")
    clv_mean = round(sum(clvs) / len(clvs), 6) if clvs else None
    roi = round(sum(profits) / len(profits) * 100.0, 2) if profits else None
    warnings: List[str] = []
    if len(rows) < 100:
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
    elif len(rows) < 100:
        verdict = "sample_insufficient"
    elif clv_mean is not None and clv_mean <= 0:
        verdict = "clv_negative"
    elif len(rows) >= 500 and clv_mean and clv_mean > 0:
        verdict = "promising_shadow"
    else:
        verdict = "observation_only"
    return {
        "ledger": ledger_path,
        "signals_total": len(rows),
        "signals_with_closing": len(clvs),
        "clv_coverage": round(len(clvs) / len(rows) * 100.0, 2) if rows else 0.0,
        "clv_mean": clv_mean,
        "clv_median": _median(clvs),
        "clv_positive_rate": round(sum(1 for value in clvs if value > 0) / len(clvs) * 100.0, 2) if clvs else None,
        "clv_by_league": _group_stats(rows, "league"),
        "clv_by_market": _group_stats(rows, "market_type"),
        "clv_by_strategy": _group_stats(rows, "strategy_name"),
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
        "message": "Observation shadow seulement: aucune mise automatique, aucun conseil de pari.",
    }


def write_json(report: Dict[str, Any], path: str) -> Path:
    target = ensure_reports_path(path)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], path: str) -> Path:
    target = ensure_reports_path(path)
    warnings = "".join(f"<li>{html.escape(str(item))}</li>" for item in report.get("warnings") or [])
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
        f"<tr><th>Coverage CLV</th><td>{report.get('clv_coverage')}%</td></tr>",
        f"<tr><th>CLV moyenne</th><td>{report.get('clv_mean')}</td></tr>",
        f"<tr><th>CLV positive</th><td>{report.get('clv_positive_rate')}%</td></tr>",
        f"<tr><th>ROI</th><td>{report.get('roi')}</td></tr>",
        f"<tr><th>Verdict</th><td>{html.escape(str(report.get('verdict')))}</td></tr>",
        "</tbody></table>",
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
    print(f"- Coverage CLV: {report.get('clv_coverage')}%")
    print(f"- CLV moyenne: {report.get('clv_mean')}")
    print(f"- CLV mediane: {report.get('clv_median')}")
    print(f"- CLV positive: {report.get('clv_positive_rate')}%")
    print(f"- ROI resultats disponibles: {report.get('roi')}")
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
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
