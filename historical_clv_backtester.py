import argparse
import csv
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List


def ensure_reports_path(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le backtest CLV historique doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).strip().replace(",", "."))
    except Exception:
        return default


def _load(path: str) -> List[Dict[str, str]]:
    if not Path(path).exists():
        return []
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _max_drawdown(profits: Iterable[float]) -> float:
    peak = 0.0
    equity = 0.0
    max_dd = 0.0
    for profit in profits:
        equity += profit
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return round(max_dd, 6)


def _stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    valid = [row for row in rows if str(row.get("is_valid")) == "True" and str(row.get("clv_percent") or "").strip()]
    clvs = [_num(row.get("clv_percent")) for row in valid]
    profits = [_num(row.get("profit_unit")) for row in valid if str(row.get("profit_unit") or "").strip()]
    return {
        "sample": len(valid),
        "clv_mean": round(sum(clvs) / len(clvs), 6) if clvs else None,
        "clv_median": round(sorted(clvs)[len(clvs) // 2], 6) if clvs else None,
        "clv_positive_rate": round(sum(1 for value in clvs if value > 0) / len(clvs) * 100.0, 2) if clvs else None,
        "roi_unit": round(sum(profits) / len(profits), 6) if profits else None,
        "profit_unit_total": round(sum(profits), 6) if profits else None,
        "winrate": round(sum(1 for row in valid if row.get("result") == row.get("side")) / len(valid) * 100.0, 2) if valid else None,
        "max_drawdown_units": _max_drawdown(profits),
    }


def _split(rows: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get(key) or "unknown"), []).append(row)
    return {name: _stats(group_rows) for name, group_rows in sorted(grouped.items())}


def _odds_bucket(value: Any) -> str:
    odds = _num(value)
    if odds < 1.5:
        return "<1.50"
    if odds < 2.0:
        return "1.50-1.99"
    if odds < 3.0:
        return "2.00-2.99"
    if odds < 5.0:
        return "3.00-4.99"
    return "5.00+"


def build_backtest(path: str) -> Dict[str, Any]:
    rows = _load(path)
    for row in rows:
        row["odds_bucket"] = _odds_bucket(row.get("opening_odds"))
    stats = _stats(rows)
    blockers = []
    if stats["sample"] < 1000:
        blockers.append("sample historique CLV < 1000")
    if stats["clv_mean"] is None:
        blockers.append("CLV historique absente")
    elif stats["clv_mean"] <= 0:
        blockers.append("CLV historique moyenne <= 0")
    if stats["roi_unit"] is None:
        blockers.append("ROI historique indisponible")
    elif stats["roi_unit"] <= 0:
        blockers.append("ROI historique <= 0")
    verdict = "historical_watchlist" if not blockers and stats["sample"] >= 1000 else "historical_evidence_only"
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input": path,
        "summary": stats,
        "splits": {
            "league": _split(rows, "league"),
            "bookmaker": _split(rows, "bookmaker"),
            "side": _split(rows, "side"),
            "odds_bucket": _split(rows, "odds_bucket"),
        },
        "blockers": blockers,
        "verdict": verdict,
        "message": "Preuve historique seulement: ne valide pas automatiquement le live shadow.",
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = ensure_reports_path(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = ensure_reports_path(output)
    summary = report.get("summary") or {}
    blockers = "".join(f"<li>{html.escape(str(item))}</li>" for item in report.get("blockers") or [])
    target.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>Backtest CLV historique</h1>"
        f"<p>Verdict: {html.escape(str(report.get('verdict')))}</p>"
        f"<p>Sample: {summary.get('sample')} | CLV moyenne: {summary.get('clv_mean')} | ROI unite: {summary.get('roi_unit')}</p>"
        f"<h2>Blockers</h2><ul>{blockers or '<li>Aucun</li>'}</ul>"
        "</body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any]) -> None:
    summary = report.get("summary") or {}
    print("Backtest CLV historique Oracle")
    print(f"- Sample: {summary.get('sample')}")
    print(f"- CLV moyenne: {summary.get('clv_mean')}")
    print(f"- ROI unite: {summary.get('roi_unit')}")
    print(f"- Verdict: {report.get('verdict')}")
    print("- Preuve historique seulement, observation locale.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Backteste un fichier CLV historique normalise.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = build_backtest(args.input)
        if args.output:
            write_json(report, args.output)
        if args.html:
            write_html(report, args.html)
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
