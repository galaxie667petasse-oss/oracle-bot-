import argparse
import html
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from decision_policy import classify_strategy, robustness_score


GOVERNANCE_VERSION = "V6.7"
DEFAULT_FEATURES = "data/features_modern.csv"
DEFAULT_REGISTRY = "model_registry.json"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


def _short_metrics(stat: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "picks": int(stat.get("picks") or stat.get("n") or 0),
        "roi": _safe_float(stat.get("roi")),
        "profit": _safe_float(stat.get("profit")),
        "winrate": _safe_float(stat.get("winrate")),
        "max_drawdown": _safe_float(stat.get("max_drawdown") or stat.get("drawdown")),
        "average_odds": _safe_float(stat.get("average_odds")),
    }


def _section(name: str, builder: Callable[[], Any]) -> Dict[str, Any]:
    try:
        data = builder()
        return {"name": name, "ok": True, "error": "", "data": data}
    except Exception as exc:
        return {"name": name, "ok": False, "error": str(exc), "data": None}


def _load_db():
    os.environ["DATABASE_URL"] = ""
    from store import load_db

    return load_db()


def _registry_entry(
    name: str,
    kind: str,
    metrics: Dict[str, Any],
    version: str = GOVERNANCE_VERSION,
    features_used: Optional[List[str]] = None,
    notes: str = "",
) -> Dict[str, Any]:
    metrics = dict(metrics)
    metrics["governance_note"] = notes
    decision = classify_strategy(metrics)
    return {
        "name": name,
        "type": kind,
        "version": version,
        "train_period": metrics.get("train_period", "2015-01-01 -> 2022-12-31"),
        "validation_period": metrics.get("validation_period", "2023-01-01 -> 2023-12-31"),
        "test_period": metrics.get("test_period", "2024-01-01 -> fin"),
        "features_used": features_used or metrics.get("features_used") or [],
        "post_match_features_allowed": bool(metrics.get("post_match_features_allowed", False)),
        "leak_risk": metrics.get("leak_risk", "faible"),
        "validation_metrics": _short_metrics(metrics.get("validation") or {}),
        "test_metrics": _short_metrics(metrics.get("test") or {}),
        "robustness_score": decision["score"],
        "status": decision["status"],
        "decision": decision["decision"],
        "reason": decision["reason"],
        "created_at": now_iso(),
        "notes": notes,
    }


def _strategy_type(key: str) -> str:
    if key == "baseline_all":
        return "market"
    if key.startswith("oracle"):
        return "rule"
    if "favorite" in key or "total" in key or "draw" in key:
        return "segment"
    return "rule"


def _backtest_entries(backtest_report: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    strategies = backtest_report.get("strategies") or {}
    labels = {}
    try:
        from backtest_evaluator import STRATEGY_LABELS

        labels = STRATEGY_LABELS
    except Exception:
        labels = {}
    wanted = [
        "baseline_all",
        "totals_only",
        "totals_low",
        "totals_low_mid",
        "favorites_only",
        "favorites_h2h_only",
        "oracle_relaxed",
        "oracle_balanced",
        "oracle_strict",
        "strict_oracle",
    ]
    for key in wanted:
        stat = strategies.get(key)
        if not stat:
            continue
        metrics = {
            "test": stat,
            "post_match_features_allowed": False,
            "leak_risk": "faible",
            "features_used": ["odds", "market_type", "segments_historiques"],
        }
        entries.append(_registry_entry(labels.get(key, key), _strategy_type(key), metrics, notes="Backtest modern; aucune activation automatique."))
    return entries


def _favorite_entries(favorite_report: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    overall = favorite_report.get("overall")
    if overall:
        metrics = {
            "train": overall.get("train", {}),
            "validation": overall.get("validation", {}),
            "test": overall.get("test", {}),
            "post_match_features_allowed": False,
            "leak_risk": "faible",
            "features_used": ["odds", "h2h_favorite", "elo/form si disponible"],
        }
        entries.append(_registry_entry("Favoris H2H - tous", "segment", metrics, notes=overall.get("status", "")))
    for group in favorite_report.get("groups") or []:
        for segment in (group.get("segments") or [])[:4]:
            metrics = {
                "train": segment.get("train", {}),
                "validation": segment.get("validation", {}),
                "test": segment.get("test", {}),
                "post_match_features_allowed": False,
                "leak_risk": "faible",
                "features_used": ["favorite_report", group.get("label", "")],
            }
            name = f"Favoris H2H - {group.get('label', '')} - {segment.get('label', '')}"
            entries.append(_registry_entry(name, "segment", metrics, notes=segment.get("status", "")))
    return entries


def _stability_entries(stability_report: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for strategy in stability_report.get("strategies") or []:
        metrics = {
            "train": strategy.get("train", {}),
            "validation": strategy.get("validation", {}),
            "test": strategy.get("test", {}),
            "annual": strategy.get("annual", {}),
            "post_match_features_allowed": False,
            "leak_risk": "faible",
            "features_used": ["stability_annual", strategy.get("key", "")],
        }
        entries.append(_registry_entry(
            f"Stabilite annuelle - {strategy.get('label', strategy.get('key', 'strategie'))}",
            "segment",
            metrics,
            notes=strategy.get("stability_note", ""),
        ))
    return entries


def _pricing_entries(pricing_report: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for name, key in (("Pricing marge faible", "low_margin"), ("Pricing marge elevee", "high_margin")):
        stat = pricing_report.get(key) or {}
        metrics = {
            "test": stat,
            "post_match_features_allowed": False,
            "leak_risk": "faible",
            "features_used": ["market_margin", "no_vig_probability"],
        }
        entries.append(_registry_entry(name, "market", metrics, notes="Analyse pricing globale; ne remplace pas un split test dedie."))
    return entries


def _ml_entries(training_report: Dict[str, Any], market_label: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    if training_report.get("error"):
        return entries
    for model in training_report.get("models") or []:
        selected_validation = model.get("selected_validation") or {}
        selected_test = model.get("selected_test") or {}
        model_test = (model.get("model_metrics") or {}).get("test") or {}
        market_test = (model.get("market_metrics") or {}).get("test") or {}
        validation_roi = _safe_float(selected_validation.get("roi"))
        test_roi = _safe_float(selected_test.get("roi"))
        metrics = {
            "validation": selected_validation,
            "test": selected_test,
            "probability_metrics": {
                "brier_test": model_test.get("brier"),
                "market_brier_test": market_test.get("brier"),
                "log_loss_test": model_test.get("log_loss"),
                "market_log_loss_test": market_test.get("log_loss"),
            },
            "edge_positive_validation_only": validation_roi is not None and validation_roi > 0 and test_roi is not None and test_roi < 0,
            "post_match_features_allowed": bool(training_report.get("allow_post_match_features")),
            "leak_risk": "eleve" if training_report.get("allow_post_match_features") else "faible",
            "features_used": [model.get("feature_set", ""), market_label, "model_probability", "no_vig_probability"],
        }
        name = f"ML {market_label} - {model.get('feature_set')} - {model.get('name')}"
        notes = f"Seuil validation: {model.get('selected_threshold')}; {model.get('threshold_reason')}; {model.get('conclusion')}"
        entries.append(_registry_entry(name, "ml", metrics, notes=notes))
    return entries


def _external_lab_entry() -> Dict[str, Any]:
    metrics = {
        "test": {"picks": 0, "roi": None},
        "post_match_features_allowed": False,
        "leak_risk": "moyen",
        "features_used": ["external_xg_lab", "join_plan_preview"],
        "test_period": "non teste",
    }
    return _registry_entry("External xG Lab - non teste", "external_lab", metrics, notes="Aucun dataset xG reel fourni; laboratoire seulement.")


def _build_sections(features_path: str, db: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    if db is None:
        db = _load_db()
    from backtest_evaluator import build_favorite_report, build_pricing_report, build_stability_report, evaluate_backtest

    sections = [
        _section("Backtest modern", lambda: evaluate_backtest(db, preset="modern")),
        _section("Favorite report", lambda: build_favorite_report(db)),
        _section("Stability report", lambda: build_stability_report(db)),
        _section("Pricing report", lambda: build_pricing_report(db)),
    ]

    feature_file = Path(features_path)
    if feature_file.exists():
        from model_trainer import build_training_report

        sections.extend([
            _section("ML global", lambda: build_training_report(str(feature_file))),
            _section("ML H2H", lambda: build_training_report(str(feature_file), market="h2h")),
            _section("ML total", lambda: build_training_report(str(feature_file), market="total")),
        ])
    else:
        message = f"Feature matrix absente: {features_path}"
        sections.extend([
            {"name": "ML global", "ok": False, "error": message, "data": None},
            {"name": "ML H2H", "ok": False, "error": message, "data": None},
            {"name": "ML total", "ok": False, "error": message, "data": None},
        ])
    return sections


def collect_registry_entries(sections: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for section in sections:
        if not section.get("ok"):
            continue
        name = section["name"]
        data = section.get("data") or {}
        if name == "Backtest modern":
            entries.extend(_backtest_entries(data))
        elif name == "Favorite report":
            entries.extend(_favorite_entries(data))
        elif name == "Stability report":
            entries.extend(_stability_entries(data))
        elif name == "Pricing report":
            entries.extend(_pricing_entries(data))
        elif name == "ML global":
            entries.extend(_ml_entries(data, "global"))
        elif name == "ML H2H":
            entries.extend(_ml_entries(data, "h2h"))
        elif name == "ML total":
            entries.extend(_ml_entries(data, "total"))
    entries.append(_external_lab_entry())
    return sorted(entries, key=lambda item: (item.get("robustness_score", 0), item.get("name", "")), reverse=True)


def build_benchmark(features_path: str = DEFAULT_FEATURES, db: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    sections = _build_sections(features_path, db=db)
    entries = collect_registry_entries(sections)
    available = sum(1 for section in sections if section.get("ok"))
    failed = [section for section in sections if not section.get("ok")]
    best_score = max((entry.get("robustness_score", 0) for entry in entries), default=0)
    robust = [entry for entry in entries if entry.get("robustness_score", 0) >= 80 and entry.get("test_metrics", {}).get("roi", 0) and entry["test_metrics"]["roi"] > 0]
    summary = {
        "generated_at": now_iso(),
        "version": GOVERNANCE_VERSION,
        "features_path": features_path,
        "sections_available": available,
        "sections_failed": [{"name": section["name"], "error": section.get("error", "")} for section in failed],
        "models_tested": len(entries),
        "best_robustness_score": best_score,
        "robust_candidates": len(robust),
        "conclusion": "Aucune strategie robuste positive ne doit etre activee automatiquement." if not robust else "Candidats robustes observes, validation humaine requise avant tout affichage decisionnel.",
    }
    return {"summary": summary, "sections": sections, "registry": entries}


def write_registry(entries: List[Dict[str, Any]], path: str = DEFAULT_REGISTRY) -> Path:
    target = Path(path)
    target.write_text(json.dumps({
        "registry_version": GOVERNANCE_VERSION,
        "generated_at": now_iso(),
        "models": entries,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_summary(benchmark: Dict[str, Any], path: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(benchmark["summary"])
    payload["top_models"] = [
        {
            "name": entry["name"],
            "type": entry["type"],
            "robustness_score": entry["robustness_score"],
            "status": entry["status"],
            "decision": entry["decision"],
            "reason": entry["reason"],
        }
        for entry in benchmark["registry"][:12]
    ]
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(benchmark: Dict[str, Any], path: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for entry in benchmark["registry"][:40]:
        rows.append(
            "<tr>"
            f"<td>{html.escape(entry['name'])}</td>"
            f"<td>{html.escape(entry['type'])}</td>"
            f"<td>{entry['robustness_score']}</td>"
            f"<td>{html.escape(entry['status'])}</td>"
            f"<td>{html.escape(entry['decision'])}</td>"
            f"<td>{html.escape(entry['reason'])}</td>"
            "</tr>"
        )
    failed = benchmark["summary"].get("sections_failed") or []
    failed_html = "".join(f"<li>{html.escape(item['name'])}: {html.escape(item.get('error', ''))}</li>" for item in failed) or "<li>Aucune section indisponible.</li>"
    target.write_text("\n".join([
        "<!doctype html>",
        "<html lang='fr'><head><meta charset='utf-8'>",
        "<title>Benchmark gouvernance Oracle Bot</title>",
        "<style>body{font-family:Arial,sans-serif;margin:32px;color:#1f2933}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px;text-align:left}th{background:#f3f4f6}.warn{background:#fff7ed;border:1px solid #fed7aa;padding:12px;border-radius:6px}</style>",
        "</head><body>",
        "<h1>Scientific Benchmark & Model Governance</h1>",
        f"<p>Genere le {html.escape(benchmark['summary']['generated_at'])}. Rapport local descriptif: aucun pick automatique.</p>",
        f"<p><strong>Conclusion:</strong> {html.escape(benchmark['summary']['conclusion'])}</p>",
        "<section class='warn'><h2>Sections indisponibles</h2><ul>",
        failed_html,
        "</ul></section>",
        "<h2>Gouvernance des modeles</h2>",
        "<table><thead><tr><th>Modele/strategie</th><th>Type</th><th>Score</th><th>Statut</th><th>Decision</th><th>Raison principale</th></tr></thead><tbody>",
        *rows,
        "</tbody></table>",
        "<p>Regle: meme un statut production_allowed ne signifierait pas pari automatique; seulement un signal explicable d'aide a la decision.</p>",
        "</body></html>",
    ]), encoding="utf-8")
    return target


def print_report(benchmark: Dict[str, Any]) -> None:
    summary = benchmark["summary"]
    print("Scientific Benchmark & Model Governance Oracle Bot")
    print(f"- Version: {summary['version']}")
    print(f"- Features: {summary['features_path']}")
    print(f"- Sections disponibles: {summary['sections_available']}")
    print(f"- Sections indisponibles: {len(summary['sections_failed'])}")
    for failed in summary["sections_failed"]:
        print(f"  - {failed['name']}: {failed['error']}")
    print(f"- Modeles/strategies evalues: {summary['models_tested']}")
    print(f"- Meilleur score robustesse: {summary['best_robustness_score']}/100")
    print(f"- Candidats robustes: {summary['robust_candidates']}")
    print("- Top gouvernance:")
    for entry in benchmark["registry"][:12]:
        print(f"  - {entry['name']}: score={entry['robustness_score']}, statut={entry['status']}, decision={entry['decision']}, raison={entry['reason']}")
    print(f"- Conclusion: {summary['conclusion']}")
    print("- Rappel: aucune strategie n'est branchee aux picks Telegram ou Railway.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Benchmark scientifique et gouvernance modele Oracle Bot, local et descriptif.")
    parser.add_argument("--features", default=DEFAULT_FEATURES, help="CSV de features local")
    parser.add_argument("--summary-json", default="", help="Chemin du resume JSON")
    parser.add_argument("--html", default="", help="Chemin du rapport HTML")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY, help="Chemin du model registry versionne")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    benchmark = build_benchmark(args.features)
    registry_path = write_registry(benchmark["registry"], args.registry)
    if args.summary_json:
        summary_path = write_summary(benchmark, args.summary_json)
        print(f"- Resume JSON ecrit: {summary_path}")
    if args.html:
        html_path = write_html(benchmark, args.html)
        print(f"- Rapport HTML ecrit: {html_path}")
    print(f"- Model registry ecrit: {registry_path}")
    print_report(benchmark)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
