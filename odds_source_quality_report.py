import argparse
import html
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from odds_snapshot_store import load_snapshots


def _pct(part: int, total: int) -> float:
    return round(part / total * 100.0, 2) if total else 0.0


def build_quality_report(snapshots_path: str) -> Dict[str, Any]:
    rows = load_snapshots(snapshots_path)
    valid = [row for row in rows if row.get("validation_status") == "valid"]
    near_close = [row for row in valid if str(row.get("is_near_close") or "").lower() == "true"]
    ids = [row.get("snapshot_id") for row in rows if row.get("snapshot_id")]
    match_counter = Counter(
        (
            row.get("match_date"),
            row.get("league"),
            row.get("normalized_home") or row.get("home_team"),
            row.get("normalized_away") or row.get("away_team"),
        )
        for row in valid
    )
    markets = Counter(row.get("market_type") or "unknown" for row in valid)
    near_markets = Counter(row.get("market_type") or "unknown" for row in near_close)
    if not near_close:
        clv_capacity = "none"
    elif near_markets.get("h2h", 0) and near_markets.get("total", 0):
        clv_capacity = "usable"
    else:
        clv_capacity = "partial"
    recommendations = []
    if not rows:
        recommendations.append("creer ou importer des snapshots de cotes")
    if not near_close:
        recommendations.append("capturer des snapshots near-close horodates")
    if markets.get("h2h", 0) == 0:
        recommendations.append("ajouter le marche h2h")
    if rows and len(valid) < len(rows):
        recommendations.append("corriger les lignes de cotes invalides")
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "snapshots": snapshots_path,
        "rows_total": len(rows),
        "valid_rows": len(valid),
        "invalid_rows": len(rows) - len(valid),
        "sources": dict(Counter(row.get("source") or "unknown" for row in valid)),
        "bookmakers": dict(Counter(row.get("bookmaker") or "unknown" for row in valid)),
        "leagues": dict(Counter(row.get("league") or "unknown" for row in valid)),
        "markets": dict(markets),
        "near_close_rows": len(near_close),
        "near_close_coverage": _pct(len(near_close), len(valid)),
        "duplicates": len(ids) - len(set(ids)),
        "matches_count": len(match_counter),
        "odds_per_match_mean": round(sum(match_counter.values()) / len(match_counter), 2) if match_counter else 0.0,
        "markets_covered": {
            "h2h": markets.get("h2h", 0) > 0,
            "total": markets.get("total", 0) > 0,
            "btts": markets.get("btts", 0) > 0,
        },
        "clv_capacity": clv_capacity,
        "recommendations": recommendations,
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = Path(output)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le rapport quality odds doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = Path(output)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le rapport HTML odds doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Odds Source Quality</title>",
        "<style>body{font-family:Arial,sans-serif;margin:32px}section{border:1px solid #ddd;padding:12px;margin:12px 0;border-radius:6px}</style></head><body>",
        "<h1>Odds Source Quality</h1>",
        f"<p>Snapshots: {html.escape(str(report.get('snapshots')))}</p>",
        "<section><h2>Resume</h2><ul>",
    ]
    for key in ("rows_total", "valid_rows", "invalid_rows", "near_close_rows", "near_close_coverage", "duplicates", "clv_capacity"):
        rows.append(f"<li>{html.escape(key)}: {html.escape(str(report.get(key)))}</li>")
    rows.append("</ul></section><section><h2>Recommandations</h2><ul>")
    for item in report.get("recommendations") or []:
        rows.append(f"<li>{html.escape(str(item))}</li>")
    rows.append("</ul></section><p>Laboratoire local: aucune mise conseillee.</p></body></html>")
    target.write_text("\n".join(rows), encoding="utf-8")
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Qualite des sources de cotes Oracle")
    print(f"- Lignes totales: {report.get('rows_total')}")
    print(f"- Lignes invalides: {report.get('invalid_rows')}")
    print(f"- Snapshots near-close: {report.get('near_close_rows')}")
    print(f"- Capacite CLV: {report.get('clv_capacity')}")
    print(f"- Recommandations: {', '.join(report.get('recommendations') or []) or 'aucune'}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Rapport qualite des sources de cotes collectees.")
    parser.add_argument("--snapshots", required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = build_quality_report(args.snapshots)
        print_report(report)
        if args.output:
            print(f"- JSON ecrit: {write_json(report, args.output)}")
        if args.html:
            print(f"- HTML ecrit: {write_html(report, args.html)}")
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
