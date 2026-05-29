import argparse
import html
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from decision_policy import classify_strategy, robustness_score


GOVERNANCE_VERSION = "V8.0"
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


def _nested(metrics: Dict[str, Any], *names: str) -> Dict[str, Any]:
    for name in names:
        value = metrics.get(name)
        if isinstance(value, dict):
            return value
    return {}


def _metric(metrics: Dict[str, Any], key: str, *containers: str) -> Optional[float]:
    value = metrics.get(key)
    if value is not None:
        return _safe_float(value)
    for container in containers:
        data = metrics.get(container)
        if isinstance(data, dict) and data.get(key) is not None:
            return _safe_float(data.get(key))
    return None


def _registry_metric_warnings(entry: Dict[str, Any]) -> List[str]:
    warnings = []
    if entry.get("clv_mean") is None:
        warnings.append("CLV indisponible: candidat robuste bloque.")
    if entry.get("ece") is None or entry.get("brier") is None:
        warnings.append("Calibration indisponible ou incomplete.")
    if entry.get("bootstrap_roi_p05") is None or entry.get("p_value_adjusted") is None:
        warnings.append("Validation statistique indisponible ou incomplete.")
    return warnings


def _section(name: str, builder: Callable[[], Any]) -> Dict[str, Any]:
    try:
        data = builder()
        return {"name": name, "ok": True, "error": "", "data": data}
    except Exception as exc:
        return {"name": name, "ok": False, "error": str(exc), "data": None}


def _read_json_file(path: str) -> Dict[str, Any]:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"rapport absent: {path}")
    return json.loads(target.read_text(encoding="utf-8"))


def _optional_report_section(name: str, path: str) -> Dict[str, Any]:
    if not path:
        return {"name": name, "ok": False, "error": "rapport non fourni", "data": None}
    return _section(name, lambda: _read_json_file(path))


def _update_entry_decision(entry: Dict[str, Any]) -> None:
    existing_reasons = list(entry.get("rejection_reasons") or [])
    metrics = {
        "test": {
            "picks": entry.get("sample_test"),
            "roi": entry.get("roi_test"),
            "max_drawdown": entry.get("drawdown"),
        },
        "clv": {
            "clv_mean": entry.get("clv_mean"),
            "clv_positive_rate": entry.get("clv_positive_rate"),
        },
        "calibration": {
            "brier": entry.get("brier"),
            "log_loss": entry.get("log_loss"),
            "ece": entry.get("ece"),
            "mce": entry.get("mce"),
        },
        "statistics": {
            "bootstrap_roi_p05": entry.get("bootstrap_roi_p05"),
            "bootstrap_roi_median": entry.get("bootstrap_roi_median"),
            "bootstrap_roi_p95": entry.get("bootstrap_roi_p95"),
            "p_value": entry.get("p_value"),
            "p_value_adjusted": entry.get("p_value_adjusted"),
        },
        "multiple_testing_passed": entry.get("multiple_testing_passed"),
        "post_match_features_allowed": entry.get("post_match_features_allowed"),
        "leak_risk": entry.get("leak_risk"),
        "governance_note": entry.get("notes", ""),
    }
    decision = classify_strategy(metrics)
    entry["robustness_score"] = decision["score"]
    entry["governance_status"] = decision.get("governance_status", decision["status"])
    entry["status"] = decision["status"]
    entry["decision"] = decision["decision"]
    entry["reason"] = decision["reason"]
    entry["rejection_reasons"] = list(dict.fromkeys(existing_reasons + list(decision.get("rejection_reasons", []))))
    entry["warnings"] = _registry_metric_warnings(entry)


def enrich_registry_entries(entries: List[Dict[str, Any]], report_sections: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    reports = {section.get("name"): section.get("data") for section in report_sections if section.get("ok") and isinstance(section.get("data"), dict)}
    clv_report = reports.get("CLV report") or {}
    clv_readiness = reports.get("CLV readiness") or {}
    calibration = reports.get("Calibration report") or {}
    statistical = reports.get("Statistical validation") or {}
    clv_by_strategy = ((clv_report.get("groups") or {}).get("by_strategy") or {}) if isinstance(clv_report, dict) else {}
    stat_by_strategy = statistical.get("by_strategy") or {} if isinstance(statistical, dict) else {}
    clv_scope = clv_report.get("clv_scope") or clv_readiness.get("clv_scope") or "none"
    clv_coverage = clv_report.get("coverage_global") or ((clv_readiness.get("preview") or {}).get("coverage"))
    partial_warning = "CLV partielle: ne valide pas draw, total, BTTS ni strategie globale." if clv_scope not in {"full", "none"} else ""
    for entry in entries:
        name = entry.get("name", "")
        entry["clv_scope"] = clv_scope
        entry["clv_coverage"] = clv_coverage
        entry["partial_clv_warning"] = partial_warning
        entry["clv_blocks_promotion_reason"] = ""
        if name in clv_by_strategy:
            stat = clv_by_strategy[name]
            entry["clv_mean"] = stat.get("clv_mean")
            entry["clv_positive_rate"] = stat.get("clv_positive_rate")
        if clv_scope not in {"full", "none"}:
            lowered = f"{entry.get('name', '')} {entry.get('type', '')}".lower()
            if "total" in lowered or "draw" in lowered or "nul" in lowered or "baseline_all" in lowered or "global" in lowered:
                entry["clv_mean"] = None
                entry["clv_positive_rate"] = None
                entry["clv_blocks_promotion_reason"] = "CLV partielle non applicable a ce marche/segment"
            elif not entry.get("clv_mean"):
                entry["clv_blocks_promotion_reason"] = "CLV partielle disponible seulement si le segment est couvert et sample suffisant"
        if name in stat_by_strategy:
            stat = stat_by_strategy[name]
            boot = stat.get("bootstrap_roi") or {}
            entry["bootstrap_roi_p05"] = boot.get("p05")
            entry["bootstrap_roi_median"] = boot.get("p50")
            entry["bootstrap_roi_p95"] = boot.get("p95")
            entry["p_value"] = stat.get("p_value")
            entry["p_value_adjusted"] = stat.get("p_value_adjusted")
            entry["multiple_testing_passed"] = stat.get("p_value_adjusted") is not None and stat.get("p_value_adjusted") < 0.05
        if calibration.get("status") == "disponible" and entry.get("type") in {"ml", "market"}:
            entry["brier"] = calibration.get("brier")
            entry["log_loss"] = calibration.get("log_loss")
            entry["ece"] = calibration.get("ece")
            entry["mce"] = calibration.get("mce")
        _update_entry_decision(entry)
        if entry.get("clv_blocks_promotion_reason"):
            entry["rejection_reasons"] = list(dict.fromkeys(list(entry.get("rejection_reasons") or []) + [entry["clv_blocks_promotion_reason"]]))
    return entries


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
    test_metrics = _short_metrics(metrics.get("test") or {})
    probability = _nested(metrics, "calibration", "calibration_metrics", "probability_metrics", "model_metrics")
    statistics = _nested(metrics, "statistics", "statistical_validation")
    clv = _nested(metrics, "clv", "clv_metrics")
    entry = {
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
        "test_metrics": test_metrics,
        "roi_test": _metric(metrics, "roi_test") if _metric(metrics, "roi_test") is not None else test_metrics.get("roi"),
        "clv_mean": _metric(metrics, "clv_mean", "clv", "clv_metrics"),
        "clv_positive_rate": _metric(metrics, "clv_positive_rate", "clv", "clv_metrics"),
        "brier": _metric(metrics, "brier", "calibration", "calibration_metrics", "probability_metrics", "model_metrics"),
        "log_loss": _metric(metrics, "log_loss", "calibration", "calibration_metrics", "probability_metrics", "model_metrics"),
        "ece": _metric(metrics, "ece", "calibration", "calibration_metrics", "probability_metrics", "model_metrics"),
        "mce": _metric(metrics, "mce", "calibration", "calibration_metrics", "probability_metrics", "model_metrics"),
        "bootstrap_roi_p05": _metric(metrics, "bootstrap_roi_p05", "statistics", "statistical_validation"),
        "bootstrap_roi_median": _metric(metrics, "bootstrap_roi_median", "statistics", "statistical_validation"),
        "bootstrap_roi_p95": _metric(metrics, "bootstrap_roi_p95", "statistics", "statistical_validation"),
        "p_value": _metric(metrics, "p_value", "statistics", "statistical_validation"),
        "p_value_adjusted": _metric(metrics, "p_value_adjusted", "statistics", "statistical_validation"),
        "multiple_testing_passed": metrics.get("multiple_testing_passed"),
        "sample_test": metrics.get("sample_test") if metrics.get("sample_test") is not None else test_metrics.get("picks"),
        "drawdown": _metric(metrics, "drawdown") if _metric(metrics, "drawdown") is not None else test_metrics.get("max_drawdown"),
        "robustness_score": decision["score"],
        "governance_status": decision.get("governance_status", decision["status"]),
        "status": decision["status"],
        "decision": decision["decision"],
        "reason": decision["reason"],
        "rejection_reasons": decision.get("rejection_reasons", []),
        "created_at": now_iso(),
        "notes": notes,
    }
    if probability:
        entry.setdefault("probability_context", probability)
    if statistics:
        entry.setdefault("statistical_context", statistics)
    if clv:
        entry.setdefault("clv_context", clv)
    entry["warnings"] = _registry_metric_warnings(entry)
    return entry


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


def _xg_rolling_lab_entry(report: Dict[str, Any]) -> Dict[str, Any]:
    metrics = dict(report.get("governance_metrics") or {})
    metrics.setdefault("test", {"picks": 0, "roi": None})
    metrics.setdefault("validation", {"picks": 0, "roi": None})
    metrics["post_match_features_allowed"] = False
    metrics["leak_risk"] = "controlled_rolling"
    metrics["features_used"] = ["external_xg_rolling_avg3_avg5", "market_no_vig"]
    metrics["test_period"] = "2025-01-01 -> 2025-05-25"
    notes = (
        f"lignes rolling={report.get('rows_with_rolling_xg', 0)}, "
        f"matchs uniques={report.get('unique_matches_with_rolling_xg', 0)}, "
        f"{report.get('conclusion') or report.get('error') or 'observation seulement'}"
    )
    return _registry_entry(
        "epl_fbref_2024_2025_rolling_xg_lab",
        "external_lab",
        metrics,
        notes=notes,
    )


def _xg_quality_model_entry(quality: Dict[str, Any], model: Dict[str, Any]) -> Dict[str, Any]:
    verdict = model.get("verdict") or {}
    comparison = model.get("comparison") or {}
    join_context = model.get("join_quality_context") or quality.get("join_quality_context") or {}
    selected_test = verdict.get("selected_test") or {}
    with_xg = comparison.get("with_xg") or {}
    market = comparison.get("market") or ((model.get("market_baseline") or {}).get("test") or {})
    join_rate = _safe_float(join_context.get("join_rate") if join_context.get("join_rate") is not None else join_context.get("join_rate_after_alias"))
    join_quality = join_context.get("join_quality")
    join_blocks = bool(join_context.get("join_blocks_promotion"))
    if join_rate is not None and join_rate < 50:
        join_blocks = True
        join_quality = join_quality or "insuffisant"
    metrics = {
        "validation": (((model.get("models") or [{}, {}])[-1] if model.get("models") else {}).get("selected_validation") or {}),
        "test": selected_test,
        "probability_metrics": {
            "brier": with_xg.get("brier"),
            "log_loss": with_xg.get("log_loss"),
            "brier_test": with_xg.get("brier"),
            "market_brier_test": market.get("brier"),
            "log_loss_test": with_xg.get("log_loss"),
            "market_log_loss_test": market.get("log_loss"),
        },
        "post_match_features_allowed": False,
        "leak_risk": "controlled_rolling",
        "features_used": ["understat_rolling_xg", "market_no_vig"],
        "test_period": (model.get("split_config") or {}).get("test_from", "2024-01-01") + " -> fin",
        "sample_test": selected_test.get("picks"),
    }
    quality_verdict = quality.get("verdict")
    promotion_allowed = bool(verdict.get("promotion_allowed"))
    quality_path = str(quality.get("external_path") or model.get("features_path") or "").lower()
    name = "understat_laliga_2020_2025_rolling_xg_lab" if "laliga" in quality_path or "la-liga" in quality_path else "understat_epl_2020_2025_rolling_xg_lab"
    notes = (
        f"quality={quality_verdict}; "
        f"join_quality={join_quality}; "
        f"xg_model={verdict.get('governance_note') or model.get('conclusion') or 'observation seulement'}; "
        "lab_only=true; can_influence_picks=false"
    )
    entry = _registry_entry(name, "external_xg_lab", metrics, notes=notes)
    rejection_reasons = list(entry.get("rejection_reasons") or [])
    if quality_verdict != "exploitable_rolling_xg":
        rejection_reasons.append("quality gate xG non exploitable")
    if not promotion_allowed:
        rejection_reasons.append("xG model promotion_allowed=false")
    if join_blocks:
        rejection_reasons.append("jointure externe insuffisante")
    if verdict.get("rejection_reasons"):
        rejection_reasons.extend(verdict.get("rejection_reasons") or [])
    entry.update({
        "lab_only": True,
        "can_influence_picks": False,
        "quality_verdict": quality_verdict,
        "xg_model_verdict": verdict.get("governance_note"),
        "xg_model_promotion_allowed": promotion_allowed,
        "promotion_allowed": False,
        "join_rate": join_rate,
        "join_quality": join_quality,
        "alias_applied": join_context.get("alias_applied"),
        "unmatched_count": join_context.get("unmatched_count"),
        "join_blocks_promotion": join_blocks,
        "rejection_reasons": list(dict.fromkeys(rejection_reasons)),
        "quality_context": {
            "rows": quality.get("rows"),
            "xg_coverage": quality.get("xg_coverage"),
            "missing_seasons": quality.get("missing_seasons"),
            "total_expected_matches": quality.get("total_expected_matches"),
            "total_actual_matches": quality.get("total_actual_matches"),
        },
        "xg_model_context": {
            "xg_improves_brier": verdict.get("xg_improves_brier"),
            "xg_improves_log_loss": verdict.get("xg_improves_log_loss"),
            "edge_test_positive": verdict.get("edge_test_positive"),
            "sample_test_sufficient": verdict.get("sample_test_sufficient"),
            "delta_brier_xg_vs_market": comparison.get("delta_brier_xg_vs_market"),
            "delta_log_loss_xg_vs_market": comparison.get("delta_log_loss_xg_vs_market"),
            "join_quality_context": join_context,
        },
    })
    if quality_verdict != "exploitable_rolling_xg" or not promotion_allowed or join_blocks:
        entry["robustness_score"] = min(entry.get("robustness_score", 0), 59)
        entry["governance_status"] = "observation" if entry["robustness_score"] < 40 else "watchlist"
        entry["status"] = entry["governance_status"]
        entry["decision"] = entry["governance_status"]
        entry["reason"] = entry["rejection_reasons"][0] if entry["rejection_reasons"] else "xG lab observation seulement"
    return entry


def _build_sections(
    features_path: str,
    db: Optional[Dict[str, Any]] = None,
    xg_lab_path: str = "",
    clv_report_path: str = "",
    calibration_report_path: str = "",
    statistical_report_path: str = "",
    xg_quality_path: str = "",
    xg_model_path: str = "",
    big5_xg_summary_path: str = "",
    clv_readiness_path: str = "",
    closing_probe_path: str = "",
    shadow_report_path: str = "",
) -> List[Dict[str, Any]]:
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
    if xg_lab_path:
        xg_file = Path(xg_lab_path)
        if xg_file.exists():
            from xg_model_lab import build_xg_model_report

            sections.append(_section("External xG rolling lab", lambda: build_xg_model_report(str(xg_file))))
        else:
            sections.append({"name": "External xG rolling lab", "ok": False, "error": f"Fichier xG lab absent: {xg_lab_path}", "data": None})
    sections.extend([
        _optional_report_section("CLV report", clv_report_path),
        _optional_report_section("Calibration report", calibration_report_path),
        _optional_report_section("Statistical validation", statistical_report_path),
        _optional_report_section("XG quality report", xg_quality_path),
        _optional_report_section("XG model report", xg_model_path),
        _optional_report_section("Big 5 xG summary", big5_xg_summary_path),
        _optional_report_section("CLV readiness", clv_readiness_path),
        _optional_report_section("Closing odds probe", closing_probe_path),
        _optional_report_section("Shadow CLV report", shadow_report_path),
    ])
    return sections


def collect_registry_entries(sections: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    section_data: Dict[str, Dict[str, Any]] = {}
    for section in sections:
        if not section.get("ok"):
            continue
        name = section["name"]
        data = section.get("data") or {}
        if isinstance(data, dict):
            section_data[name] = data
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
        elif name == "External xG rolling lab":
            entries.append(_xg_rolling_lab_entry(data))
    if section_data.get("XG quality report") or section_data.get("XG model report"):
        entries.append(_xg_quality_model_entry(
            section_data.get("XG quality report") or {},
            section_data.get("XG model report") or {},
        ))
    entries.append(_external_lab_entry())
    return sorted(entries, key=lambda item: (item.get("robustness_score", 0), item.get("name", "")), reverse=True)


def build_benchmark(
    features_path: str = DEFAULT_FEATURES,
    db: Optional[Dict[str, Any]] = None,
    xg_lab_path: str = "",
    clv_report_path: str = "",
    calibration_report_path: str = "",
    statistical_report_path: str = "",
    xg_quality_path: str = "",
    xg_model_path: str = "",
    big5_xg_summary_path: str = "",
    clv_readiness_path: str = "",
    closing_probe_path: str = "",
    shadow_report_path: str = "",
) -> Dict[str, Any]:
    sections = _build_sections(
        features_path,
        db=db,
        xg_lab_path=xg_lab_path,
        clv_report_path=clv_report_path,
        calibration_report_path=calibration_report_path,
        statistical_report_path=statistical_report_path,
        xg_quality_path=xg_quality_path,
        xg_model_path=xg_model_path,
        big5_xg_summary_path=big5_xg_summary_path,
        clv_readiness_path=clv_readiness_path,
        closing_probe_path=closing_probe_path,
        shadow_report_path=shadow_report_path,
    )
    entries = collect_registry_entries(sections)
    entries = enrich_registry_entries(entries, sections)
    available = sum(1 for section in sections if section.get("ok"))
    failed = [section for section in sections if not section.get("ok")]
    best_score = max((entry.get("robustness_score", 0) for entry in entries), default=0)
    report_data = {section.get("name"): section.get("data") for section in sections if section.get("ok") and isinstance(section.get("data"), dict)}
    big5_data = report_data.get("Big 5 xG summary") or {}
    big5_global = big5_data.get("global") or {}
    clv_readiness = report_data.get("CLV readiness") or {}
    closing_probe = report_data.get("Closing odds probe") or {}
    clv_report_data = report_data.get("CLV report") or {}
    shadow_report = report_data.get("Shadow CLV report") or {}
    shadow_sample = shadow_report.get("sample_size") or shadow_report.get("signals_total") or 0
    shadow_roi = shadow_report.get("roi")
    shadow_drawdown = shadow_report.get("drawdown")
    clv_calculable = bool(clv_readiness.get("clv_calculable")) if clv_readiness else False
    clv_calculable_now = bool(clv_readiness.get("clv_calculable_now", clv_calculable)) if clv_readiness else False
    clv_calculable_after_enrichment = bool(clv_readiness.get("clv_calculable_after_enrichment")) if clv_readiness else False
    source_has_closing = bool(
        clv_readiness.get("source_has_closing")
        or closing_probe.get("closing_available")
    )
    clv_scope = clv_readiness.get("clv_scope") or clv_report_data.get("clv_scope") or "none"
    clv_is_partial = clv_scope not in {"full", "none"}
    clv_report_summary = clv_report_data.get("summary") or {}
    clv_report_sample = clv_report_summary.get("n") or clv_report_data.get("rows_with_closing") or 0
    robust = [
        entry for entry in entries
        if entry.get("robustness_score", 0) >= 80
        and entry.get("governance_status") in {"candidate", "active_shadow_only", "active_decision_support", "production_allowed"}
        and entry.get("clv_mean") is not None
        and entry.get("clv_mean") > 0
    ]
    if clv_readiness and not clv_calculable:
        robust = []
    if shadow_report:
        shadow_blocks = []
        if shadow_sample < 1000:
            shadow_blocks.append("sample shadow inferieur a 1000")
        if shadow_report.get("clv_mean") is None:
            shadow_blocks.append("CLV shadow absente")
        elif shadow_report.get("clv_mean") <= 0:
            shadow_blocks.append("CLV shadow non positive")
        if shadow_roi is None:
            shadow_blocks.append("ROI shadow indisponible")
        elif shadow_roi <= 0:
            shadow_blocks.append("ROI shadow non positif")
        if shadow_drawdown is not None and shadow_drawdown <= -10:
            shadow_blocks.append("drawdown shadow eleve")
        shadow_blocks.append("validation historique incomplete")
        for entry in entries:
            entry["shadow_available"] = True
            entry["shadow_sample"] = shadow_sample
            entry["shadow_verdict"] = shadow_report.get("verdict")
            entry["shadow_blocks_promotion"] = True
            if not isinstance(entry.get("rejection_reasons"), list):
                entry["rejection_reasons"] = []
            for reason in shadow_blocks:
                if reason not in entry["rejection_reasons"]:
                    entry["rejection_reasons"].append(reason)
    statistical_data = report_data.get("Statistical validation") or {}
    statistical_groups = statistical_data.get("by_strategy") or {}
    statistically_interesting = sum(
        1 for stat in statistical_groups.values()
        if isinstance(stat, dict) and (stat.get("p_value") is not None and stat.get("p_value") < 0.05)
    )
    surviving_correction = sum(
        1 for stat in statistical_groups.values()
        if isinstance(stat, dict) and (stat.get("p_value_adjusted") is not None and stat.get("p_value_adjusted") < 0.05)
    )
    promotion_blockers: List[str] = []
    if clv_readiness and not clv_calculable:
        promotion_blockers.append("CLV non calculable depuis la feature matrix actuelle")
    if clv_is_partial:
        promotion_blockers.append("CLV partielle: ne valide pas draw, total, BTTS ni strategie globale")
    if clv_report_data and clv_report_sample < 1000:
        promotion_blockers.append("Sample CLV inferieur a 1000")
    if clv_report_summary.get("clv_mean") is not None and clv_report_summary.get("clv_mean") <= 0:
        promotion_blockers.append("CLV moyenne non positive")
    if clv_calculable_after_enrichment and not clv_calculable_now:
        promotion_blockers.append("Enrichissement closing requis avant analyse CLV")
    if closing_probe and not source_has_closing:
        promotion_blockers.append("Source MATCHES sans closing odds fiable detectee")
    if big5_data and (big5_global.get("robust_candidates") or 0) == 0:
        promotion_blockers.append("Big 5 xG sans candidat robuste")
    if big5_data and (big5_global.get("leagues_clv_available") or 0) == 0:
        promotion_blockers.append("Big 5 xG bloque par CLV absente")
    if big5_data and not big5_global.get("ready_for_big5_conclusion", True):
        missing = ", ".join(big5_global.get("missing_leagues") or [])
        promotion_blockers.append(f"Big 5 incomplet: {missing or 'ligues manquantes'}")
    if big5_data and (big5_global.get("leagues_sample_ge_1000") or 0) == 0:
        promotion_blockers.append("Sample edge test Big 5 insuffisant")
    blocked_join = [
        item.get("league")
        for item in (big5_data.get("leagues") or [])
        if item.get("dataset_present") and item.get("join_quality") == "insuffisant"
    ]
    if blocked_join:
        promotion_blockers.append("Jointure externe insuffisante: " + ", ".join(str(item) for item in blocked_join))
    if big5_data and (big5_global.get("leagues_roi_edge_positive") or 0) == 0:
        promotion_blockers.append("ROI edge test non positif sur les ligues disponibles")
    if big5_data and (big5_global.get("leagues_xg_improves_brier") or 0) == 0 and (big5_global.get("leagues_xg_improves_log_loss") or 0) == 0:
        promotion_blockers.append("xG ne bat pas le marche sur les metriques probabilistes disponibles")
    if statistical_groups and surviving_correction == 0:
        promotion_blockers.append("Multiple testing: aucune strategie ne survit la correction")
    if shadow_report:
        if shadow_sample < 1000:
            promotion_blockers.append("Shadow mode: sample inferieur a 1000")
        if shadow_report.get("clv_mean") is None:
            promotion_blockers.append("Shadow mode: CLV manuelle absente")
        elif shadow_report.get("clv_mean") <= 0:
            promotion_blockers.append("Shadow mode: CLV moyenne non positive")
        if shadow_roi is None:
            promotion_blockers.append("Shadow mode: ROI indisponible")
        elif shadow_roi <= 0:
            promotion_blockers.append("Shadow mode: ROI non positif")
        if shadow_drawdown is not None and shadow_drawdown <= -10:
            promotion_blockers.append("Shadow mode: drawdown eleve")
        promotion_blockers.append("Shadow mode: validation historique et revue humaine requises")
    if not promotion_blockers:
        promotion_blockers.append("Gouvernance complete requise avant tout affichage decisionnel")

    summary = {
        "generated_at": now_iso(),
        "version": GOVERNANCE_VERSION,
        "features_path": features_path,
        "xg_lab_path": xg_lab_path or None,
        "xg_quality_path": xg_quality_path or None,
        "xg_model_path": xg_model_path or None,
        "big5_xg_summary_path": big5_xg_summary_path or None,
        "clv_readiness_path": clv_readiness_path or None,
        "closing_probe_path": closing_probe_path or None,
        "shadow_report_path": shadow_report_path or None,
        "xg_lab_available": any(section.get("name") == "External xG rolling lab" and section.get("ok") for section in sections),
        "xg_quality_available": any(section.get("name") == "XG quality report" and section.get("ok") for section in sections),
        "xg_model_available": any(section.get("name") == "XG model report" and section.get("ok") for section in sections),
        "big5_xg_available": bool(big5_data),
        "clv_readiness_available": bool(clv_readiness),
        "closing_probe_available": bool(closing_probe),
        "shadow_report_available": bool(shadow_report),
        "shadow_signals": shadow_report.get("signals_total"),
        "shadow_clv_coverage": shadow_report.get("clv_coverage"),
        "shadow_clv_mean": shadow_report.get("clv_mean"),
        "shadow_clv_positive_rate": shadow_report.get("clv_positive_rate"),
        "shadow_roi": shadow_roi,
        "shadow_profit": shadow_report.get("profit"),
        "shadow_max_drawdown": shadow_drawdown,
        "shadow_sample": shadow_report.get("sample_size") or shadow_report.get("signals_total"),
        "shadow_verdict": shadow_report.get("verdict"),
        "clv_calculable": clv_calculable,
        "clv_calculable_now": clv_calculable_now,
        "clv_calculable_after_enrichment": clv_calculable_after_enrichment,
        "clv_scope": clv_scope,
        "clv_partial": clv_is_partial,
        "clv_coverage": clv_report_data.get("coverage_global") or ((clv_readiness.get("preview") or {}).get("coverage")),
        "clv_sample": clv_report_sample,
        "clv_mean": clv_report_summary.get("clv_mean"),
        "clv_positive_rate": clv_report_summary.get("clv_positive_rate"),
        "source_has_closing": source_has_closing,
        "recommended_next_command": clv_readiness.get("recommended_next_command") if clv_readiness else None,
        "clv_missing_columns": clv_readiness.get("missing_columns") if clv_readiness else [],
        "clv_markets_covered": clv_readiness.get("markets") if clv_readiness else {},
        "closing_probe_detected_columns": ((closing_probe.get("detected_columns") or {}).get("all_closing") or []) if closing_probe else [],
        "big5_total_leagues_expected": big5_global.get("total_leagues_expected"),
        "big5_total_leagues_available": big5_global.get("total_leagues_available"),
        "big5_missing_leagues": big5_global.get("missing_leagues") or [],
        "big5_ready_for_conclusion": big5_global.get("ready_for_big5_conclusion"),
        "big5_clv_blocker": big5_global.get("clv_blocker"),
        "big5_leagues_exploitable": big5_global.get("leagues_exploitable"),
        "big5_observation_count": (big5_global.get("observations") or 0) + (big5_global.get("watchlist") or 0),
        "big5_candidate_count": big5_global.get("robust_candidates", 0),
        "big5_blocked_by_clv": bool(big5_data and (big5_global.get("leagues_clv_available") or 0) == 0),
        "promotion_blockers": promotion_blockers,
        "clv_report_available": bool((report_data.get("CLV report") or {}).get("status") in {"disponible", "partiel"}),
        "calibration_report_available": bool((report_data.get("Calibration report") or {}).get("status") == "disponible"),
        "statistical_report_available": bool((report_data.get("Statistical validation") or {}).get("status") == "disponible"),
        "sections_available": available,
        "sections_failed": [{"name": section["name"], "error": section.get("error", "")} for section in failed],
        "models_tested": len(entries),
        "strategies_with_clv_available": sum(1 for entry in entries if entry.get("clv_mean") is not None),
        "strategies_with_calibration_available": sum(1 for entry in entries if entry.get("ece") is not None or entry.get("brier") is not None),
        "strategies_statistically_interesting_before_correction": statistically_interesting,
        "strategies_surviving_multiple_testing": surviving_correction,
        "best_robustness_score": best_score,
        "robust_candidates": len(robust),
        "warnings": [
            f"{section['name']}: {section.get('error', '')}"
            for section in failed
            if section.get("name") in {"CLV report", "Calibration report", "Statistical validation", "XG quality report", "XG model report", "Big 5 xG summary", "CLV readiness", "Closing odds probe"}
        ],
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
            "governance_status": entry.get("governance_status"),
            "clv_mean": entry.get("clv_mean"),
            "clv_scope": entry.get("clv_scope"),
            "clv_coverage": entry.get("clv_coverage"),
            "ece": entry.get("ece"),
            "bootstrap_roi_p05": entry.get("bootstrap_roi_p05"),
            "p_value_adjusted": entry.get("p_value_adjusted"),
            "quality_verdict": entry.get("quality_verdict"),
            "xg_model_verdict": entry.get("xg_model_verdict"),
            "join_rate": entry.get("join_rate"),
            "join_quality": entry.get("join_quality"),
            "alias_applied": entry.get("alias_applied"),
            "unmatched_count": entry.get("unmatched_count"),
            "join_blocks_promotion": entry.get("join_blocks_promotion"),
            "clv_blocks_promotion_reason": entry.get("clv_blocks_promotion_reason"),
            "partial_clv_warning": entry.get("partial_clv_warning"),
            "lab_only": entry.get("lab_only"),
            "promotion_allowed": entry.get("promotion_allowed"),
            "status": entry["status"],
            "decision": entry["decision"],
            "reason": entry["reason"],
            "rejection_reasons": entry.get("rejection_reasons", []),
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
            f"<td>{html.escape(str(entry.get('clv_mean')))}</td>"
            f"<td>{html.escape(str(entry.get('ece')))}</td>"
            f"<td>{html.escape(str(entry.get('bootstrap_roi_p05')))}</td>"
            f"<td>{html.escape(str(entry.get('p_value_adjusted')))}</td>"
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
        "<ul>",
        f"<li>Strategies avec CLV disponible: {benchmark['summary'].get('strategies_with_clv_available')}</li>",
        f"<li>Strategies avec calibration disponible: {benchmark['summary'].get('strategies_with_calibration_available')}</li>",
        f"<li>Strategies interessantes avant correction: {benchmark['summary'].get('strategies_statistically_interesting_before_correction')}</li>",
        f"<li>Strategies survivant correction: {benchmark['summary'].get('strategies_surviving_multiple_testing')}</li>",
        f"<li>Quality gate xG disponible: {benchmark['summary'].get('xg_quality_available')}</li>",
        f"<li>Modele xG disponible: {benchmark['summary'].get('xg_model_available')}</li>",
        f"<li>Big 5 xG summary disponible: {benchmark['summary'].get('big5_xg_available')}</li>",
        f"<li>CLV readiness disponible: {benchmark['summary'].get('clv_readiness_available')}</li>",
        f"<li>Closing odds probe disponible: {benchmark['summary'].get('closing_probe_available')}</li>",
        f"<li>Shadow report disponible: {benchmark['summary'].get('shadow_report_available')}</li>",
        f"<li>Shadow signals: {benchmark['summary'].get('shadow_signals')}</li>",
        f"<li>Shadow CLV coverage: {benchmark['summary'].get('shadow_clv_coverage')}</li>",
        f"<li>Shadow CLV moyenne: {benchmark['summary'].get('shadow_clv_mean')}</li>",
        f"<li>Shadow ROI: {benchmark['summary'].get('shadow_roi')}</li>",
        f"<li>Shadow max drawdown: {benchmark['summary'].get('shadow_max_drawdown')}</li>",
        f"<li>Shadow verdict: {html.escape(str(benchmark['summary'].get('shadow_verdict')))}</li>",
        f"<li>CLV calculable: {benchmark['summary'].get('clv_calculable')}</li>",
        f"<li>Scope CLV: {html.escape(str(benchmark['summary'].get('clv_scope')))}</li>",
        f"<li>Coverage CLV: {benchmark['summary'].get('clv_coverage')}</li>",
        f"<li>CLV partielle: {benchmark['summary'].get('clv_partial')}</li>",
        f"<li>CLV calculable apres enrichissement: {benchmark['summary'].get('clv_calculable_after_enrichment')}</li>",
        f"<li>Source avec closing: {benchmark['summary'].get('source_has_closing')}</li>",
        f"<li>Big 5 complet: {benchmark['summary'].get('big5_ready_for_conclusion')}</li>",
        f"<li>Ligues Big 5 manquantes: {html.escape(', '.join(benchmark['summary'].get('big5_missing_leagues') or []) or 'aucune')}</li>",
        f"<li>Ligues Big 5 exploitables: {benchmark['summary'].get('big5_leagues_exploitable')}</li>",
        f"<li>Observations Big 5: {benchmark['summary'].get('big5_observation_count')}</li>",
        f"<li>Candidats Big 5: {benchmark['summary'].get('big5_candidate_count')}</li>",
        "</ul>",
        "<section class='warn'><h2>Promotion blockers</h2><ul>",
        *[f"<li>{html.escape(str(item))}</li>" for item in benchmark["summary"].get("promotion_blockers") or []],
        "</ul></section>",
        "<section class='warn'><h2>Sections indisponibles</h2><ul>",
        failed_html,
        "</ul></section>",
        "<h2>Gouvernance des modeles</h2>",
        "<table><thead><tr><th>Modele/strategie</th><th>Type</th><th>Score</th><th>CLV</th><th>ECE</th><th>Bootstrap p05</th><th>p ajustee</th><th>Statut</th><th>Decision</th><th>Raison principale</th></tr></thead><tbody>",
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
    print(f"- Strategies avec CLV disponible: {summary.get('strategies_with_clv_available')}")
    print(f"- Strategies avec calibration disponible: {summary.get('strategies_with_calibration_available')}")
    print(f"- Strategies interessantes avant correction: {summary.get('strategies_statistically_interesting_before_correction')}")
    print(f"- Strategies survivant correction multiple testing: {summary.get('strategies_surviving_multiple_testing')}")
    print(f"- Quality gate xG disponible: {summary.get('xg_quality_available')}")
    print(f"- Modele xG disponible: {summary.get('xg_model_available')}")
    print(f"- Big 5 xG summary disponible: {summary.get('big5_xg_available')}")
    print(f"- CLV readiness disponible: {summary.get('clv_readiness_available')}")
    print(f"- Closing odds probe disponible: {summary.get('closing_probe_available')}")
    print(f"- Shadow report disponible: {summary.get('shadow_report_available')}")
    print(f"- Shadow signals: {summary.get('shadow_signals')}")
    print(f"- Shadow CLV coverage: {summary.get('shadow_clv_coverage')}")
    print(f"- Shadow CLV moyenne: {summary.get('shadow_clv_mean')}")
    print(f"- Shadow ROI: {summary.get('shadow_roi')}")
    print(f"- Shadow max drawdown: {summary.get('shadow_max_drawdown')}")
    print(f"- Shadow verdict: {summary.get('shadow_verdict')}")
    print(f"- CLV calculable: {summary.get('clv_calculable')}")
    print(f"- Scope CLV: {summary.get('clv_scope')}")
    print(f"- Coverage CLV: {summary.get('clv_coverage')}")
    print(f"- CLV partielle: {summary.get('clv_partial')}")
    print(f"- CLV calculable apres enrichissement: {summary.get('clv_calculable_after_enrichment')}")
    print(f"- Source avec closing: {summary.get('source_has_closing')}")
    print(f"- Big 5 complet: {summary.get('big5_ready_for_conclusion')}")
    print(f"- Ligues Big 5 manquantes: {', '.join(summary.get('big5_missing_leagues') or []) or 'aucune'}")
    print(f"- Observations Big 5: {summary.get('big5_observation_count')}")
    print(f"- Candidats Big 5: {summary.get('big5_candidate_count')}")
    for blocker in summary.get("promotion_blockers") or []:
        print(f"- Blocage promotion: {blocker}")
    print(f"- Meilleur score robustesse: {summary['best_robustness_score']}/100")
    print(f"- Candidats robustes: {summary['robust_candidates']}")
    print("- Top gouvernance:")
    for entry in benchmark["registry"][:12]:
        print(f"  - {entry['name']}: score={entry['robustness_score']}, statut={entry['status']}, decision={entry['decision']}, CLV={entry.get('clv_mean')}, ECE={entry.get('ece')}, raison={entry['reason']}")
    print(f"- Conclusion: {summary['conclusion']}")
    print("- Rappel: aucune strategie n'est branchee aux picks Telegram ou Railway.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Benchmark scientifique et gouvernance modele Oracle Bot, local et descriptif.")
    parser.add_argument("--features", default=DEFAULT_FEATURES, help="CSV de features local")
    parser.add_argument("--summary-json", default="", help="Chemin du resume JSON")
    parser.add_argument("--html", default="", help="Chemin du rapport HTML")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY, help="Chemin du model registry versionne")
    parser.add_argument("--xg-lab", default="", help="CSV rolling xG externe produit dans reports/")
    parser.add_argument("--clv-report", default="", help="JSON CLV deja genere")
    parser.add_argument("--calibration-report", default="", help="JSON calibration deja genere")
    parser.add_argument("--statistical-report", default="", help="JSON validation statistique deja genere")
    parser.add_argument("--xg-quality", default="", help="JSON quality gate xG Understat")
    parser.add_argument("--xg-model", default="", help="JSON modele xG Understat")
    parser.add_argument("--big5-xg-summary", default="", help="JSON agregateur Big 5 xG")
    parser.add_argument("--clv-readiness", default="", help="JSON readiness CLV")
    parser.add_argument("--closing-probe", default="", help="JSON closing_odds_probe optionnel")
    parser.add_argument("--shadow-report", default="", help="JSON shadow_clv_report optionnel")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    benchmark = build_benchmark(
        args.features,
        xg_lab_path=args.xg_lab,
        clv_report_path=args.clv_report,
        calibration_report_path=args.calibration_report,
        statistical_report_path=args.statistical_report,
        xg_quality_path=args.xg_quality,
        xg_model_path=args.xg_model,
        big5_xg_summary_path=args.big5_xg_summary,
        clv_readiness_path=args.clv_readiness,
        closing_probe_path=args.closing_probe,
        shadow_report_path=args.shadow_report,
    )
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
