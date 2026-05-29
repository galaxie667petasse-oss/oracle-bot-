import argparse
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_LEAGUES = {
    "EPL": "understat_epl_2020_2025",
    "LaLiga": "laliga_2020_2025",
    "Bundesliga": "bundesliga_2020_2025",
    "SerieA": "seriea_2020_2025",
    "Ligue1": "ligue1_2020_2025",
}

REPORT_ALIASES = {
    "EPL": {
        "join": ["epl_join_diagnostics.json", "understat_epl_join_diagnostics.json"],
    },
    "LaLiga": {
        "join": ["laliga_join_diagnostics.json"],
    },
    "Bundesliga": {
        "join": ["bundesliga_join_diagnostics.json"],
    },
    "SerieA": {
        "join": ["seriea_join_diagnostics.json"],
    },
    "Ligue1": {
        "join": ["ligue1_join_diagnostics.json"],
    },
}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def ensure_reports_path(path: str) -> Path:
    target = Path(path)
    parts = [part.lower() for part in target.parts]
    if "data" in parts:
        raise ValueError("Le rapport Big 5 xG ne doit pas etre ecrit dans data/.")
    if "reports" not in parts:
        raise ValueError("Le rapport Big 5 xG doit etre ecrit dans reports/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _sibling(path: Path, suffix: str) -> Path:
    name = path.name
    if name.endswith("_xg_model.json"):
        return path.with_name(name.replace("_xg_model.json", f"_{suffix}.json"))
    return path.with_name(f"{path.stem}_{suffix}.json")


def _first_existing(default_path: Path, alternates: Iterable[Path]) -> Path:
    for path in [default_path, *list(alternates)]:
        if path.exists():
            return path
    return default_path


def _report_paths(reports_dir: Path, league: str, prefix: str, model_path: str = "") -> Dict[str, Path]:
    if model_path:
        model = Path(model_path)
        return {
            "quality": _sibling(model, "quality"),
            "join": _sibling(model, "join_diagnostics"),
            "model": model,
            "pipeline": _sibling(model, "pipeline_summary"),
        }
    aliases = REPORT_ALIASES.get(league, {})
    join_default = reports_dir / f"{prefix}_join_diagnostics.json"
    join_alternates = [reports_dir / name for name in aliases.get("join", [])]
    return {
        "quality": reports_dir / f"{prefix}_quality.json",
        "join": _first_existing(join_default, join_alternates),
        "model": reports_dir / f"{prefix}_xg_model.json",
        "pipeline": reports_dir / f"{prefix}_pipeline_summary.json",
    }


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _join_quality_from_rate(rate: Any) -> str:
    value = safe_float(rate)
    if value is None:
        return ""
    if value >= 90.0:
        return "excellent"
    if value >= 75.0:
        return "exploitable_prudent"
    if value >= 50.0:
        return "fragile"
    return "insuffisant"


def _comparison_metrics(model: Dict[str, Any]) -> Dict[str, Any]:
    comparison = model.get("comparison") or {}
    verdict = model.get("verdict") or {}
    selected = verdict.get("selected_test") or {}
    market = comparison.get("market") or ((model.get("market_baseline") or {}).get("test") or {})
    with_xg = comparison.get("with_xg") or {}
    without_xg = comparison.get("without_xg") or {}
    return {
        "market_brier": safe_float(market.get("brier")),
        "market_log_loss": safe_float(market.get("log_loss")),
        "without_xg_brier": safe_float(without_xg.get("brier")),
        "without_xg_log_loss": safe_float(without_xg.get("log_loss")),
        "xg_brier": safe_float(with_xg.get("brier")),
        "xg_log_loss": safe_float(with_xg.get("log_loss")),
        "delta_brier": safe_float(comparison.get("delta_brier_xg_vs_market")),
        "delta_log_loss": safe_float(comparison.get("delta_log_loss_xg_vs_market")),
        "roi_edge_test": safe_float(selected.get("roi")),
        "sample_edge_test": int(selected.get("picks") or 0),
        "promotion_allowed": bool(verdict.get("promotion_allowed")),
        "clv_available": bool(verdict.get("clv_available")),
        "xg_improves_brier": bool(verdict.get("xg_improves_brier")),
        "xg_improves_log_loss": bool(verdict.get("xg_improves_log_loss")),
        "rejection_reasons": list(verdict.get("rejection_reasons") or []),
        "governance_note": verdict.get("governance_note") or "",
    }


def _status_for_league(item: Dict[str, Any]) -> Tuple[str, List[str]]:
    reasons = list(item.get("rejection_reasons") or [])
    if item.get("join_quality") == "insuffisant":
        reasons.append("jointure externe insuffisante")
        return "rejet", list(dict.fromkeys(reasons))
    if item.get("quality_verdict") and item.get("quality_verdict") != "exploitable_rolling_xg":
        reasons.append("quality gate xG fragile")
        return "observation stricte", list(dict.fromkeys(reasons))
    if item.get("roi_edge_test") is not None and item.get("roi_edge_test") <= 0:
        if item.get("xg_improves_brier") or item.get("xg_improves_log_loss"):
            reasons.append("ROI test negatif malgre amelioration probabiliste")
            return "observation technique", list(dict.fromkeys(reasons))
        reasons.append("ROI test negatif")
        return "rejet", list(dict.fromkeys(reasons))
    if item.get("sample_edge_test", 0) < 1000:
        reasons.append("sample edge test inferieur a 1000")
        if item.get("clv_available"):
            return "observation", list(dict.fromkeys(reasons))
    if not item.get("clv_available"):
        reasons.append("CLV absente")
        return "watchlist maximum" if (item.get("roi_edge_test") or 0) > 0 else "observation technique", list(dict.fromkeys(reasons))
    if item.get("promotion_allowed"):
        return "candidat a revoir humainement", list(dict.fromkeys(reasons))
    return "observation", list(dict.fromkeys(reasons))


def build_league_summary(league: str, paths: Dict[str, Path]) -> Dict[str, Any]:
    quality = read_json(paths["quality"])
    join = read_json(paths["join"])
    model = read_json(paths["model"])
    pipeline = read_json(paths["pipeline"])
    final = pipeline.get("final_status") or {}
    model_summary = final.get("xg_model") or {}
    metrics = _comparison_metrics(model)
    join_context = model.get("join_quality_context") or {}
    rolling = (pipeline.get("rolling_features") or {}).get("data") or {}
    item = {
        "league": league,
        "dataset_present": bool(quality or model or pipeline),
        "quality_report_present": bool(quality),
        "join_report_present": bool(join),
        "model_report_present": bool(model),
        "pipeline_summary_present": bool(pipeline),
        "quality_verdict": quality.get("verdict") or final.get("quality_verdict"),
        "join_rate": _first_present(
            join.get("join_rate_after_alias"),
            join_context.get("join_rate"),
            join_context.get("join_rate_after_alias"),
            final.get("join_rate_after_alias"),
            final.get("join_rate"),
        ),
        "join_quality": _first_present(join.get("join_quality"), join_context.get("join_quality"), final.get("join_quality")),
        "rolling_avg3": _first_present(rolling.get("avg3_rows"), final.get("rolling_avg3_rows")),
        "rolling_avg5": _first_present(rolling.get("avg5_rows"), final.get("rolling_avg5_rows")),
        "unique_matches_rolling": _first_present(
            model.get("unique_matches_with_rolling_xg"),
            rolling.get("matched_external_matches"),
            final.get("unique_matches_rolling"),
        ),
        "market_brier": _first_present(metrics["market_brier"], model_summary.get("market_brier_test")),
        "market_log_loss": _first_present(metrics["market_log_loss"], model_summary.get("market_log_loss_test")),
        "xg_brier": _first_present(metrics["xg_brier"], model_summary.get("xg_brier_test")),
        "xg_log_loss": _first_present(metrics["xg_log_loss"], model_summary.get("xg_log_loss_test")),
        "delta_brier": metrics["delta_brier"],
        "delta_log_loss": metrics["delta_log_loss"],
        "roi_edge_test": _first_present(metrics["roi_edge_test"], model_summary.get("roi_edge_test")),
        "sample_edge_test": _first_present(metrics["sample_edge_test"], model_summary.get("sample_edge_test")) or 0,
        "promotion_allowed": bool(_first_present(metrics["promotion_allowed"], model_summary.get("promotion_allowed"), False)),
        "clv_available": bool(metrics["clv_available"]),
        "xg_improves_brier": bool(metrics["xg_improves_brier"]),
        "xg_improves_log_loss": bool(metrics["xg_improves_log_loss"]),
        "rejection_reasons": metrics["rejection_reasons"],
        "lab_only": True,
        "can_influence_picks": False,
    }
    if not item.get("join_quality") and item.get("join_rate") is not None:
        item["join_quality"] = _join_quality_from_rate(item.get("join_rate"))
    if item["delta_brier"] is None and item["market_brier"] is not None and item["xg_brier"] is not None:
        item["delta_brier"] = round(float(item["xg_brier"]) - float(item["market_brier"]), 6)
    if item["delta_log_loss"] is None and item["market_log_loss"] is not None and item["xg_log_loss"] is not None:
        item["delta_log_loss"] = round(float(item["xg_log_loss"]) - float(item["market_log_loss"]), 6)
    status, reasons = _status_for_league(item)
    item["status"] = status
    item["rejection_reasons"] = reasons
    item["promotion_allowed"] = bool(
        item.get("promotion_allowed")
        and item.get("clv_available")
        and (item.get("sample_edge_test") or 0) >= 1000
        and item.get("join_quality") in {"excellent", "exploitable_prudent"}
        and item.get("quality_verdict") == "exploitable_rolling_xg"
    )
    return item


def parse_league_reports(values: Iterable[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--league-report doit utiliser le format Ligue=chemin.json")
        league, path = value.split("=", 1)
        out[league.strip()] = path.strip()
    return out


def build_summary(reports_dir: str = "reports", league_reports: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    root = Path(reports_dir)
    clv_readiness = read_json(root / "clv_readiness.json")
    clv_scope = clv_readiness.get("clv_scope") or "none"
    clv_partial = clv_scope not in {"full", "none"}
    explicit = league_reports or {}
    expected_leagues = list(DEFAULT_LEAGUES.keys())
    league_items: List[Dict[str, Any]] = []
    for league, prefix in DEFAULT_LEAGUES.items():
        paths = _report_paths(root, league, prefix, explicit.get(league, ""))
        league_items.append(build_league_summary(league, paths))
    for league, path in explicit.items():
        if league in DEFAULT_LEAGUES:
            continue
        league_items.append(build_league_summary(league, _report_paths(root, league, league.lower(), path)))

    available = [item for item in league_items if item.get("dataset_present")]
    available_names = {item.get("league") for item in available}
    missing_leagues = [league for league in expected_leagues if league not in available_names]
    exploitable = [item for item in available if item.get("quality_verdict") == "exploitable_rolling_xg" and item.get("join_quality") in {"excellent", "exploitable_prudent"}]
    improves_brier = [item for item in available if item.get("xg_improves_brier") or ((item.get("delta_brier") or 0) < 0)]
    improves_log = [item for item in available if item.get("xg_improves_log_loss") or ((item.get("delta_log_loss") or 0) < 0)]
    roi_positive = [item for item in available if (item.get("roi_edge_test") or 0) > 0]
    sample_ok = [item for item in available if (item.get("sample_edge_test") or 0) >= 1000]
    clv_ok = [item for item in available if item.get("clv_available")]
    positive_roi_no_full_clv = [item for item in roi_positive if clv_scope != "full"]
    candidates = [
        item for item in available
        if item.get("promotion_allowed") and item.get("clv_available") and (item.get("sample_edge_test") or 0) >= 1000
    ]
    ready_for_big5 = len(missing_leagues) == 0
    clv_blocker = len(clv_ok) == 0
    if not ready_for_big5:
        conclusion = "Conclusion partielle Big 5: ligues manquantes, aucun candidat robuste."
        if clv_blocker:
            conclusion += " CLV absente sur les ligues disponibles."
        if clv_partial:
            conclusion += " CLV partielle utile au diagnostic H2H, pas a la promotion globale."
    elif clv_blocker:
        conclusion = "Big 5 complet mais CLV absente: aucun candidat robuste, observations seulement."
    elif clv_partial:
        conclusion = "Big 5 xG partiellement evaluable avec CLV H2H: aucun candidat robuste sans CLV complete par marche/cote."
    elif not candidates:
        conclusion = "Aucun candidat robuste Big 5: verifier CLV, sample, jointure et stabilite avant toute promotion."
    else:
        conclusion = "Candidats Big 5 a revue humaine stricte; aucun pari automatique."

    return {
        "generated_at": now_iso(),
        "reports_dir": str(root),
        "leagues": league_items,
        "global": {
            "total_leagues_expected": len(expected_leagues),
            "total_leagues_available": len(available),
            "expected_leagues": expected_leagues,
            "missing_leagues": missing_leagues,
            "ready_for_big5_conclusion": ready_for_big5,
            "clv_blocker": clv_blocker,
            "clv_scope": clv_scope,
            "clv_partial": clv_partial,
            "clv_global_blocker": clv_scope != "full",
            "leagues_with_positive_roi_but_no_full_clv": len(positive_roi_no_full_clv),
            "leagues_available": len(available),
            "leagues_exploitable": len(exploitable),
            "leagues_xg_improves_brier": len(improves_brier),
            "leagues_xg_improves_log_loss": len(improves_log),
            "leagues_roi_edge_positive": len(roi_positive),
            "leagues_sample_ge_1000": len(sample_ok),
            "leagues_clv_available": len(clv_ok),
            "robust_candidates": len(candidates),
            "observations": sum(1 for item in available if "observation" in item.get("status", "")),
            "watchlist": sum(1 for item in available if "watchlist" in item.get("status", "")),
            "rejected": sum(1 for item in available if item.get("status") == "rejet"),
            "conclusion": conclusion,
        },
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_json(report: Dict[str, Any], path: str) -> Path:
    target = ensure_reports_path(path)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], path: str) -> Path:
    target = ensure_reports_path(path)
    rows = []
    for item in report.get("leagues") or []:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('league')))}</td>"
            f"<td>{html.escape(str(item.get('dataset_present')))}</td>"
            f"<td>{html.escape(str(item.get('quality_verdict')))}</td>"
            f"<td>{html.escape(str(item.get('join_rate')))}</td>"
            f"<td>{html.escape(str(item.get('join_quality')))}</td>"
            f"<td>{html.escape(str(item.get('market_brier')))} / {html.escape(str(item.get('xg_brier')))}</td>"
            f"<td>{html.escape(str(item.get('market_log_loss')))} / {html.escape(str(item.get('xg_log_loss')))}</td>"
            f"<td>{html.escape(str(item.get('roi_edge_test')))}</td>"
            f"<td>{html.escape(str(item.get('sample_edge_test')))}</td>"
            f"<td>{html.escape(str(item.get('status')))}</td>"
            f"<td>{html.escape(', '.join(item.get('rejection_reasons') or []))}</td>"
            "</tr>"
        )
    global_data = report.get("global") or {}
    target.write_text("\n".join([
        "<!doctype html>",
        "<html lang='fr'><head><meta charset='utf-8'>",
        "<title>Big 5 xG Lab Summary</title>",
        "<style>body{font-family:Arial,sans-serif;margin:32px;color:#1f2933}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px;text-align:left}th{background:#f3f4f6}.warn{background:#fff7ed;border:1px solid #fed7aa;padding:12px;border-radius:6px}</style>",
        "</head><body>",
        "<h1>Big 5 xG Lab Summary</h1>",
        f"<p>{html.escape(str(global_data.get('conclusion')))}</p>",
        "<ul>",
        f"<li>Big 5 complet: {global_data.get('ready_for_big5_conclusion')}</li>",
        f"<li>Ligues disponibles: {global_data.get('leagues_available')}</li>",
        f"<li>Ligues manquantes: {html.escape(', '.join(global_data.get('missing_leagues') or []) or 'aucune')}</li>",
        f"<li>Ligues exploitables: {global_data.get('leagues_exploitable')}</li>",
        f"<li>Ligues avec ROI edge positif: {global_data.get('leagues_roi_edge_positive')}</li>",
        f"<li>Ligues avec CLV disponible: {global_data.get('leagues_clv_available')}</li>",
        f"<li>Scope CLV: {html.escape(str(global_data.get('clv_scope')))}</li>",
        f"<li>CLV partielle: {global_data.get('clv_partial')}</li>",
        f"<li>Candidats robustes: {global_data.get('robust_candidates')}</li>",
        "</ul>",
        "<table><thead><tr><th>Ligue</th><th>Present</th><th>Quality</th><th>Join rate</th><th>Join quality</th><th>Brier marche/xG</th><th>Log loss marche/xG</th><th>ROI edge</th><th>Sample</th><th>Statut</th><th>Blocages</th></tr></thead><tbody>",
        *rows,
        "</tbody></table>",
        "<p>Rapport local descriptif: aucun pick automatique, aucun Telegram, aucun Railway.</p>",
        "</body></html>",
    ]), encoding="utf-8")
    return target


def print_report(report: Dict[str, Any]) -> None:
    global_data = report.get("global") or {}
    print("Big 5 xG Lab Summary")
    print(f"- Dossier rapports: {report.get('reports_dir')}")
    print(f"- Big 5 complet: {global_data.get('ready_for_big5_conclusion')}")
    print(f"- Ligues disponibles: {global_data.get('leagues_available')}")
    print(f"- Ligues manquantes: {', '.join(global_data.get('missing_leagues') or []) or 'aucune'}")
    print(f"- Ligues exploitables: {global_data.get('leagues_exploitable')}")
    print(f"- Ligues avec Brier xG meilleur: {global_data.get('leagues_xg_improves_brier')}")
    print(f"- Ligues avec log loss xG meilleur: {global_data.get('leagues_xg_improves_log_loss')}")
    print(f"- Ligues ROI edge positif: {global_data.get('leagues_roi_edge_positive')}")
    print(f"- Ligues sample >= 1000: {global_data.get('leagues_sample_ge_1000')}")
    print(f"- Ligues avec CLV disponible: {global_data.get('leagues_clv_available')}")
    print(f"- Scope CLV: {global_data.get('clv_scope')}")
    print(f"- CLV partielle: {global_data.get('clv_partial')}")
    print(f"- Bloqueur CLV: {global_data.get('clv_blocker')}")
    print(f"- Candidats robustes: {global_data.get('robust_candidates')}")
    for item in report.get("leagues") or []:
        if item.get("dataset_present"):
            print(f"  - {item.get('league')}: statut={item.get('status')}, join={item.get('join_rate')}%, ROI={item.get('roi_edge_test')}, sample={item.get('sample_edge_test')}")
    print(f"- Conclusion: {global_data.get('conclusion')}")
    print("- Statut: laboratoire seulement, aucun pick automatique.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Agregateur xG Big 5 local, sans recuperation reseau.")
    parser.add_argument("--reports-dir", default="reports", help="Dossier reports/ a scanner")
    parser.add_argument("--league-report", action="append", default=[], help="Format Ligue=chemin_xg_model.json")
    parser.add_argument("--output", default="", help="Rapport JSON dans reports/")
    parser.add_argument("--html", default="", help="Rapport HTML dans reports/")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = build_summary(args.reports_dir, parse_league_reports(args.league_report))
        if args.output:
            path = write_json(report, args.output)
            print(f"- Rapport JSON Big 5 ecrit: {path}")
        if args.html:
            path = write_html(report, args.html)
            print(f"- Rapport HTML Big 5 ecrit: {path}")
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
