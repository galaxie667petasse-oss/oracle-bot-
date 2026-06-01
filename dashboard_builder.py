import argparse
import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


REPORT_FILES = {
    "backtest_modern": "backtest_modern.txt",
    "backtest_recent": "backtest_recent.txt",
    "period": "period_report.txt",
    "favorite": "favorite_report.txt",
    "stability": "stability_report.txt",
    "pricing": "pricing_report.txt",
    "ml_global": "ml_global.txt",
    "ml_h2h": "ml_h2h.txt",
    "ml_total": "ml_total.txt",
    "external_profile": "external_profile.txt",
    "external_recommend": "external_recommend.txt",
    "benchmark_governance": "benchmark_governance.txt",
    "xg_model_lab": "xg_model_lab.txt",
    "clv": "clv_report.txt",
    "clv_partial": "clv_partial_report.txt",
    "calibration": "calibration_report.txt",
    "statistical_validation": "statistical_validation.txt",
    "understat_xg_pipeline": "understat_xg_pipeline.txt",
    "big5_xg": "big5_xg_summary.txt",
    "clv_readiness": "clv_readiness.txt",
    "closing_odds_probe": "closing_odds_probe.txt",
    "shadow_clv": "shadow_clv_report.txt",
    "ops_health": "oracle_ops_health.txt",
    "shadow_quality": "shadow_quality_audit.txt",
    "evidence_gate": "evidence_gate.txt",
    "sample_size_plan": "sample_size_plan.txt",
    "shadow_message_preview": "shadow_messages_preview.txt",
    "odds_source_config": "odds_source_config.txt",
    "odds_snapshot_summary": "odds_snapshot_store.txt",
    "odds_source_quality": "odds_source_quality.txt",
    "odds_to_shadow": "odds_to_shadow.txt",
    "odds_closing_matcher": "odds_closing_matcher.txt",
    "odds_intake_audit": "odds_intake_audit.txt",
    "architecture_map": "architecture_map.txt",
    "pipeline_contracts": "pipeline_contracts.txt",
    "llm_analyst_contract": "llm_analyst_contract.txt",
    "restitution_schema": "restitution_schema.txt",
    "progress_loop": "progress_loop.txt",
    "project_scorecard": "project_scorecard.txt",
    "agent_orchestrator_dryrun": "agent_orchestrator_dryrun.txt",
}


def latest_report_dir(root: str = "reports") -> Optional[Path]:
    base = Path(root)
    if not base.exists():
        return None
    dirs = [path for path in base.iterdir() if path.is_dir()]
    if not dirs:
        return None
    return max(dirs, key=lambda path: path.stat().st_mtime)


def read_text(report_dir: Path, filename: str) -> str:
    path = report_dir / filename
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(report_dir: Path, filename: str) -> Dict[str, Any]:
    path = report_dir / filename
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def read_json_candidates(report_dir: Path, filenames: List[str]) -> Dict[str, Any]:
    candidates = []
    for filename in filenames:
        candidates.append(report_dir / filename)
        candidates.append(Path("reports") / filename)
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict):
            return data
    return {}


def _first(pattern: str, text: str, flags: int = re.MULTILINE) -> Optional[str]:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def _first_float(pattern: str, text: str) -> Optional[float]:
    value = _first(pattern, text)
    if value is None:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def _section(text: str, title: str, max_chars: int = 1800) -> str:
    if not text:
        return "Rapport indisponible."
    idx = text.find(title)
    if idx < 0:
        return text[:max_chars]
    return text[idx: idx + max_chars]


def _lines_matching(text: str, patterns: List[str], limit: int = 12) -> List[str]:
    lines = []
    for line in text.splitlines():
        lowered = line.lower()
        if any(pattern.lower() in lowered for pattern in patterns):
            lines.append(line)
        if len(lines) >= limit:
            break
    return lines


def build_summary(report_dir: Path) -> Dict[str, Any]:
    texts = {key: read_text(report_dir, filename) for key, filename in REPORT_FILES.items()}
    pricing = texts["pricing"]
    modern = texts["backtest_modern"]
    favorite = texts["favorite"]
    ml_global = texts["ml_global"]
    registry = read_model_registry(report_dir)
    clv_json = read_json(report_dir, "clv_report.json")
    clv_partial_json = read_json_candidates(report_dir, ["clv_partial_report.json"])
    calibration_json = read_json(report_dir, "calibration_report.json")
    statistical_json = read_json(report_dir, "statistical_validation.json")
    benchmark_json = read_json(report_dir, "benchmark_summary.json")
    understat_quality = read_json_candidates(report_dir, ["understat_epl_2020_2025_quality.json"])
    understat_model = read_json_candidates(report_dir, ["understat_epl_2020_2025_xg_model.json"])
    understat_pipeline = read_json_candidates(report_dir, ["understat_epl_2020_2025_pipeline_summary.json"])
    big5_xg = read_json_candidates(report_dir, ["big5_xg_summary.json"])
    clv_readiness = read_json_candidates(report_dir, ["clv_readiness.json"])
    closing_probe = read_json_candidates(report_dir, ["closing_odds_probe.json"])
    shadow_clv = read_json_candidates(report_dir, ["shadow_clv_report.json"])
    shadow_quality = read_json_candidates(report_dir, ["shadow_quality_audit.json"])
    evidence_gate = read_json_candidates(report_dir, ["evidence_gate.json"])
    sample_plan = read_json_candidates(report_dir, ["sample_size_plan.json"])
    odds_quality = read_json_candidates(report_dir, ["odds_source_quality.json"])
    odds_summary = read_json_candidates(report_dir, ["odds_snapshot_summary.json"])
    odds_to_shadow = read_json_candidates(report_dir, ["odds_to_shadow_report.json"])
    odds_closing_matcher = read_json_candidates(report_dir, ["odds_closing_matcher_report.json"])
    odds_intake = read_json_candidates(report_dir, ["odds_intake_audit.json"])
    architecture_map = read_json_candidates(report_dir, ["architecture_map.json"])
    pipeline_contracts = read_json_candidates(report_dir, ["pipeline_contracts.json"])
    project_scorecard = read_json_candidates(report_dir, ["project_scorecard.json"])
    pipeline_final = understat_pipeline.get("final_status") or {}
    pipeline_model = pipeline_final.get("xg_model") or {}

    records_count = _first_float(r"- Records regles: ([0-9]+)", pricing)
    if records_count is None:
        records_count = _first_float(r"- Records test: ([0-9]+)", modern)
    date_min = _first(r"- Train: (\d{4}-\d{2}-\d{2}) ->", modern) or _first(r"- Records train: [0-9]+ \((\d{4}-\d{2}-\d{2}) ->", modern)
    date_max = _first(r"- Records test: [0-9]+ \([^)]* -> ([0-9-]+)\)", modern)
    baseline_roi = _first_float(r"Baseline march.*?\n(?:.*\n){0,5}- ROI: (-?[0-9.]+)%", modern)
    pricing_low_roi = _first_float(r"Marge faible .*?ROI=(-?[0-9.]+)%", pricing)
    pricing_high_roi = _first_float(r"Marge elevee .*?ROI=(-?[0-9.]+)%", pricing)
    ml_brier = _first_float(r"Test 2024\+:\n\s+- modele: n=\d+, Brier=([0-9.]+)", ml_global)
    ml_market_brier = _first_float(r"Test 2024\+:\n\s+- modele:.*\n\s+- marche no-vig: Brier=([0-9.]+)", ml_global)
    favorites_roi = _first_float(r"test n=\d+, ROI=(-?[0-9.]+)%", favorite)
    totals_roi = _first_float(r"Totals seulement.*?\n(?:.*\n){0,5}- ROI: (-?[0-9.]+)%", modern)

    warnings = []
    joined = "\n".join(texts.values()).lower()
    if "aucune strategie positive robuste" in joined or "aucune regle jouable" in joined:
        warnings.append("Aucune strategie robuste positive detectee.")
    if "signal invalide" in joined:
        warnings.append("Des signaux validation sont invalides sur test.")
    if "sklearn indisponible" in joined:
        warnings.append("sklearn indisponible: modeles RF/GB ignores.")

    conclusion = "Aucune strategie jouable robuste a ce stade; conserver une posture prudente et descriptive."
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "records_count": int(records_count) if records_count is not None else None,
        "date_min": date_min,
        "date_max": date_max,
        "baseline_roi_test": baseline_roi,
        "favorites_roi_test": favorites_roi,
        "totals_roi_test": totals_roi,
        "pricing_low_margin_roi": pricing_low_roi,
        "pricing_high_margin_roi": pricing_high_roi,
        "ml_global_brier_test": ml_brier,
        "ml_market_brier_test": ml_market_brier,
        "model_registry_count": len(registry),
        "best_robustness_score": max((entry.get("robustness_score", 0) for entry in registry), default=None),
        "clv_status": clv_json.get("status") or "indisponible",
        "clv_mean": (clv_partial_json.get("summary") or clv_json.get("summary") or {}).get("clv_mean"),
        "clv_positive_rate": (clv_partial_json.get("summary") or clv_json.get("summary") or {}).get("clv_positive_rate"),
        "clv_partial_scope": clv_partial_json.get("clv_scope") or clv_readiness.get("clv_scope"),
        "clv_partial_coverage": clv_partial_json.get("coverage_global") or ((clv_readiness.get("preview") or {}).get("coverage")),
        "clv_partial_rows": clv_partial_json.get("rows_with_closing") or ((clv_readiness.get("preview") or {}).get("rows_with_clv")),
        "clv_partial_market_sides": clv_partial_json.get("covered_market_sides") or ((clv_readiness.get("preview") or {}).get("covered_market_sides") or []),
        "clv_partial_excluded_sides": clv_partial_json.get("excluded_market_sides") or ((clv_readiness.get("preview") or {}).get("uncovered_market_sides") or []),
        "calibration_ece": calibration_json.get("ece"),
        "calibration_mce": calibration_json.get("mce"),
        "calibration_brier": calibration_json.get("brier"),
        "calibration_log_loss": calibration_json.get("log_loss"),
        "stat_roi_ci_low": (statistical_json.get("summary") or {}).get("roi_ci_low"),
        "stat_roi_ci_high": (statistical_json.get("summary") or {}).get("roi_ci_high"),
        "stat_bootstrap_p05": ((statistical_json.get("summary") or {}).get("bootstrap_roi") or {}).get("p05"),
        "stat_bootstrap_p50": ((statistical_json.get("summary") or {}).get("bootstrap_roi") or {}).get("p50"),
        "stat_bootstrap_p95": ((statistical_json.get("summary") or {}).get("bootstrap_roi") or {}).get("p95"),
        "stat_sample_size_needed": statistical_json.get("sample_size_needed") or {},
        "signals_rejected": sum(1 for entry in registry if entry.get("governance_status") == "rejected" or entry.get("status") == "rejected"),
        "main_rejection_reason": (registry[0].get("reason") if registry else None),
        "strategies_surviving_multiple_testing": benchmark_json.get("strategies_surviving_multiple_testing"),
        "understat_quality_verdict": understat_quality.get("verdict") or pipeline_final.get("quality_verdict"),
        "understat_seasons_detected": understat_quality.get("seasons_detected") or [],
        "understat_missing_seasons": understat_quality.get("missing_seasons") or [],
        "understat_total_expected_matches": understat_quality.get("total_expected_matches"),
        "understat_total_actual_matches": understat_quality.get("total_actual_matches"),
        "understat_xg_coverage": understat_quality.get("xg_coverage"),
        "understat_join_rate": pipeline_final.get("join_rate"),
        "understat_rolling_avg3": pipeline_final.get("rolling_avg3_rows"),
        "understat_rolling_avg5": pipeline_final.get("rolling_avg5_rows"),
        "understat_market_brier": pipeline_model.get("market_brier_test") or (((understat_model.get("market_baseline") or {}).get("test") or {}).get("brier")),
        "understat_market_log_loss": pipeline_model.get("market_log_loss_test") or (((understat_model.get("market_baseline") or {}).get("test") or {}).get("log_loss")),
        "understat_xg_brier": pipeline_model.get("xg_brier_test") or (((understat_model.get("comparison") or {}).get("with_xg") or {}).get("brier")),
        "understat_xg_log_loss": pipeline_model.get("xg_log_loss_test") or (((understat_model.get("comparison") or {}).get("with_xg") or {}).get("log_loss")),
        "understat_roi_edge_test": pipeline_model.get("roi_edge_test") or (((understat_model.get("verdict") or {}).get("selected_test") or {}).get("roi")),
        "understat_promotion_allowed": pipeline_model.get("promotion_allowed") if "promotion_allowed" in pipeline_model else (understat_model.get("verdict") or {}).get("promotion_allowed"),
        "understat_rejection_reasons": pipeline_model.get("rejection_reasons") or ((understat_model.get("verdict") or {}).get("rejection_reasons") or []),
        "big5_leagues_available": (big5_xg.get("global") or {}).get("leagues_available"),
        "big5_total_leagues_expected": (big5_xg.get("global") or {}).get("total_leagues_expected"),
        "big5_total_leagues_available": (big5_xg.get("global") or {}).get("total_leagues_available"),
        "big5_missing_leagues": (big5_xg.get("global") or {}).get("missing_leagues") or [],
        "big5_ready_for_conclusion": (big5_xg.get("global") or {}).get("ready_for_big5_conclusion"),
        "big5_clv_blocker": (big5_xg.get("global") or {}).get("clv_blocker"),
        "big5_leagues_exploitable": (big5_xg.get("global") or {}).get("leagues_exploitable"),
        "big5_roi_edge_positive": (big5_xg.get("global") or {}).get("leagues_roi_edge_positive"),
        "big5_sample_ge_1000": (big5_xg.get("global") or {}).get("leagues_sample_ge_1000"),
        "big5_clv_available": (big5_xg.get("global") or {}).get("leagues_clv_available"),
        "big5_candidates": (big5_xg.get("global") or {}).get("robust_candidates"),
        "big5_conclusion": (big5_xg.get("global") or {}).get("conclusion"),
        "clv_readiness_status": clv_readiness.get("status"),
        "clv_calculable": clv_readiness.get("clv_calculable"),
        "clv_calculable_now": clv_readiness.get("clv_calculable_now"),
        "clv_calculable_after_enrichment": clv_readiness.get("clv_calculable_after_enrichment"),
        "source_has_closing": clv_readiness.get("source_has_closing") if "source_has_closing" in clv_readiness else closing_probe.get("closing_available"),
        "closing_probe_available": bool(closing_probe),
        "closing_probe_h2h": closing_probe.get("h2h_closing_available"),
        "closing_probe_total": closing_probe.get("total_closing_available"),
        "closing_probe_btts": closing_probe.get("btts_closing_available"),
        "closing_probe_columns": ((closing_probe.get("detected_columns") or {}).get("all_closing") or []),
        "recommended_next_command": clv_readiness.get("recommended_next_command"),
        "shadow_report_available": bool(shadow_clv),
        "shadow_signals": shadow_clv.get("signals_total"),
        "shadow_pending_closing": shadow_clv.get("pending_closing"),
        "shadow_pending_results": shadow_clv.get("pending_results"),
        "shadow_clv_coverage": shadow_clv.get("clv_coverage"),
        "shadow_clv_mean": shadow_clv.get("clv_mean"),
        "shadow_clv_positive_rate": shadow_clv.get("clv_positive_rate"),
        "shadow_roi": shadow_clv.get("roi"),
        "shadow_profit": shadow_clv.get("profit"),
        "shadow_max_drawdown": shadow_clv.get("drawdown"),
        "shadow_sample": shadow_clv.get("sample_size"),
        "shadow_verdict": shadow_clv.get("verdict"),
        "shadow_warnings": shadow_clv.get("warnings") or [],
        "shadow_top_strategies": list((shadow_clv.get("clv_by_strategy") or {}).keys())[:5],
        "shadow_top_leagues": list((shadow_clv.get("clv_by_league") or {}).keys())[:5],
        "shadow_quality_available": bool(shadow_quality),
        "shadow_quality_verdict": shadow_quality.get("verdict"),
        "shadow_quality_errors": shadow_quality.get("blocking_errors") or [],
        "shadow_quality_warnings": shadow_quality.get("warnings") or [],
        "shadow_quality_clv_coverage": shadow_quality.get("clv_coverage"),
        "shadow_quality_result_coverage": shadow_quality.get("result_coverage"),
        "evidence_gate_available": bool(evidence_gate),
        "evidence_gate_status": evidence_gate.get("global_status"),
        "evidence_gate_blockers": evidence_gate.get("blockers") or [],
        "evidence_gate_strengths": evidence_gate.get("strengths") or [],
        "evidence_gate_next_steps": evidence_gate.get("required_next_steps") or [],
        "sample_plan_available": bool(sample_plan),
        "sample_plan_current": sample_plan.get("current_sample"),
        "sample_plan_target_required": sample_plan.get("target_edge_required_sample"),
        "sample_plan_edges": sample_plan.get("edge_sample_requirements") or {},
        "odds_quality_available": bool(odds_quality),
        "odds_sources": odds_quality.get("sources") or odds_summary.get("sources") or {},
        "odds_bookmakers": odds_quality.get("bookmakers") or odds_summary.get("bookmakers") or {},
        "odds_leagues": odds_quality.get("leagues") or odds_summary.get("leagues") or {},
        "odds_markets": odds_quality.get("markets") or odds_summary.get("markets") or {},
        "odds_rows_total": odds_quality.get("rows_total") if odds_quality else odds_summary.get("rows_total"),
        "odds_invalid_rows": odds_quality.get("invalid_rows") if odds_quality else odds_summary.get("invalid_rows"),
        "odds_near_close_rows": odds_quality.get("near_close_rows") if odds_quality else odds_summary.get("near_close_rows"),
        "odds_clv_capacity": odds_quality.get("clv_capacity"),
        "odds_recommendations": odds_quality.get("recommendations") or [],
        "odds_to_shadow_available": bool(odds_to_shadow),
        "odds_to_shadow_added": odds_to_shadow.get("rows_added"),
        "odds_to_shadow_dry_run": odds_to_shadow.get("dry_run"),
        "odds_closing_matcher_available": bool(odds_closing_matcher),
        "odds_closing_updates": odds_closing_matcher.get("closing_updated"),
        "odds_closing_matches": odds_closing_matcher.get("matches_found"),
        "odds_intake_available": bool(odds_intake),
        "odds_intake_verdict": odds_intake.get("verdict"),
        "odds_intake_taken": odds_intake.get("taken_snapshots"),
        "odds_intake_near_close": odds_intake.get("near_close_snapshots"),
        "odds_intake_valid": odds_intake.get("valid_odds"),
        "odds_intake_invalid": odds_intake.get("invalid_odds"),
        "odds_intake_linked": odds_intake.get("shadow_linked_to_snapshots"),
        "odds_intake_possible_coverage": odds_intake.get("closing_coverage_possible"),
        "odds_intake_real_coverage": odds_intake.get("closing_coverage_real"),
        "odds_intake_next": odds_intake.get("recommendations") or [],
        "architecture_blocks": len(architecture_map.get("blocks") or []),
        "pipeline_contracts_count": len((pipeline_contracts.get("contracts") or {})),
        "project_scorecard_global": project_scorecard.get("global_score"),
        "project_scorecard_real_proof": ((project_scorecard.get("scores") or {}).get("preuve betting reelle") or {}).get("score"),
        "clv_missing_columns": clv_readiness.get("missing_columns") or [],
        "clv_markets": clv_readiness.get("markets") or {},
        "final_status": "aucun pick automatique",
        "conclusion": conclusion,
        "warnings": warnings,
    }


def read_model_registry(report_dir: Path) -> List[Dict[str, Any]]:
    candidates = [report_dir / "model_registry.json", Path("model_registry.json")]
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        models = data.get("models") if isinstance(data, dict) else None
        if isinstance(models, list):
            return [item for item in models if isinstance(item, dict)]
    return []


def _card(title: str, body: str) -> str:
    return f"<section><h2>{html.escape(title)}</h2><pre>{html.escape(body.strip() or 'Information indisponible.')}</pre></section>"


def build_dashboard(report_dir: Path) -> Dict[str, Any]:
    texts = {key: read_text(report_dir, filename) for key, filename in REPORT_FILES.items()}
    summary = build_summary(report_dir)
    registry = read_model_registry(report_dir)
    big5_xg = read_json_candidates(report_dir, ["big5_xg_summary.json"])
    odds_summary = read_json_candidates(report_dir, ["odds_snapshot_summary.json"])
    odds_quality = read_json_candidates(report_dir, ["odds_source_quality.json"])
    parts = [
        "<!doctype html>",
        "<html lang='fr'><head><meta charset='utf-8'>",
        "<title>Rapport Oracle Bot</title>",
        "<style>body{font-family:Arial,sans-serif;margin:32px;line-height:1.45;color:#1f2933}section{border:1px solid #ddd;padding:16px;margin:16px 0;border-radius:6px}pre{white-space:pre-wrap;background:#f7f7f7;padding:12px;border-radius:4px}h1,h2{color:#111827}.warn{background:#fff7ed;border-color:#fed7aa}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.metric{background:#f3f4f6;padding:12px;border-radius:6px}</style>",
        "</head><body>",
        "<h1>Rapport central Oracle Football Bot</h1>",
        f"<p>Genere le {html.escape(summary['generated_at'])}. Rapport local descriptif: aucun pick automatique.</p>",
        "<div class='grid'>",
    ]
    for key, label in [
        ("records_count", "Records"),
        ("date_min", "Date min"),
        ("date_max", "Date max"),
        ("baseline_roi_test", "ROI baseline test"),
        ("pricing_low_margin_roi", "ROI marge faible"),
        ("ml_global_brier_test", "Brier ML global"),
        ("best_robustness_score", "Score robustesse max"),
        ("clv_status", "CLV"),
        ("calibration_ece", "ECE"),
        ("stat_bootstrap_p05", "Bootstrap p05"),
        ("understat_quality_verdict", "Quality xG Understat"),
        ("big5_leagues_available", "Ligues Big 5"),
        ("clv_calculable", "CLV calculable"),
        ("shadow_signals", "Signaux shadow"),
    ]:
        value = summary.get(key)
        parts.append(f"<div class='metric'><strong>{html.escape(label)}</strong><br>{html.escape(str(value) if value is not None else 'n/a')}</div>")
    parts.append("</div>")
    if summary["warnings"]:
        parts.append("<section class='warn'><h2>Alertes</h2><ul>")
        parts.extend(f"<li>{html.escape(warning)}</li>" for warning in summary["warnings"])
        parts.append("</ul></section>")

    memory = "\n".join([
        f"records_count: {summary.get('records_count')}",
        f"date_min: {summary.get('date_min')}",
        f"date_max: {summary.get('date_max')}",
        "split attendu: train 2015-2022, validation 2023, test 2024+",
    ])
    parts.append(_card("Resume memoire", memory))
    parts.append(_card("Backtest", "\n".join(_lines_matching(texts["backtest_modern"], ["Baseline", "Oracle", "Conclusion", "Aucune", "Records train", "Records test"], 20))))
    parts.append(_card("Pricing", "\n".join(_lines_matching(texts["pricing"], ["Marge moyenne", "Marge faible", "Marge elevee", "EV baseline", "trop elevee"], 20))))
    parts.append(_card("Favorite Report", "\n".join(_lines_matching(texts["favorite"], ["Favoris H2H", "1.60", "exterieur", "elo_diff", "Conclusion", "Aucun"], 24))))
    parts.append(_card("Stability", "\n".join(_lines_matching(texts["stability"], ["stable", "instable", "degradation", "negatif", "Conclusion", "Aucun"], 24))))
    ml_lines = []
    for key in ("ml_global", "ml_h2h", "ml_total"):
        if texts[key]:
            ml_lines.append(f"--- {key} ---")
            ml_lines.extend(_lines_matching(texts[key], ["Brier", "log loss", "edge >", "signal invalide", "Conclusion prudente", "Jeu de features"], 28))
    parts.append(_card("ML", "\n".join(ml_lines)))
    external_lines = _lines_matching(texts["external_profile"] + "\n" + texts["external_recommend"], ["Score utilite", "xg:", "odds:", "leak_risk", "verdict", "Recommandation"], 20)
    parts.append(_card("External Dataset Lab", "\n".join(external_lines)))
    xg_lines = []
    if texts["xg_model_lab"]:
        xg_lines.extend(_lines_matching(texts["xg_model_lab"], ["Lignes avec rolling", "Matchs uniques", "Split interne", "Marche no-vig", "Modele", "Edge test", "Conclusion", "Erreur non bloquante"], 30))
    summary_path = Path("reports") / "external_xg_features_summary.json"
    if summary_path.exists():
        try:
            xg_summary = json.loads(summary_path.read_text(encoding="utf-8"))
            xg_lines.append("--- external_xg_features_summary.json ---")
            xg_lines.append(f"taux de jointure={xg_summary.get('join_rate')}%, lignes enrichies={xg_summary.get('enriched_rows')}, avg5={xg_summary.get('avg5_rows')}")
        except Exception:
            pass
    parts.append(_card("External xG Rolling Lab", "\n".join(xg_lines) + "\nRappel: aucun signal xG n'est branche aux picks."))
    understat_lines = [
        f"quality verdict: {summary.get('understat_quality_verdict')}",
        f"saisons presentes: {', '.join(summary.get('understat_seasons_detected') or []) or 'n/a'}",
        f"saisons manquantes: {', '.join(summary.get('understat_missing_seasons') or []) or 'aucune'}",
        f"matchs attendus/reels: {summary.get('understat_total_expected_matches')} / {summary.get('understat_total_actual_matches')}",
        f"xG coverage: {summary.get('understat_xg_coverage')}%",
        f"join rate: {summary.get('understat_join_rate')}%",
        f"rolling avg3/avg5: {summary.get('understat_rolling_avg3')} / {summary.get('understat_rolling_avg5')}",
        f"Brier marche/xG: {summary.get('understat_market_brier')} / {summary.get('understat_xg_brier')}",
        f"Log loss marche/xG: {summary.get('understat_market_log_loss')} / {summary.get('understat_xg_log_loss')}",
        f"ROI edge test: {summary.get('understat_roi_edge_test')}",
        f"promotion_allowed: {summary.get('understat_promotion_allowed')}",
        f"raisons de rejet: {', '.join(summary.get('understat_rejection_reasons') or []) or 'n/a'}",
        "Rappel: aucun pick automatique.",
    ]
    if texts["understat_xg_pipeline"]:
        understat_lines.extend(_lines_matching(texts["understat_xg_pipeline"], ["Quality verdict", "Join rate", "Rolling", "Brier", "ROI edge", "Promotion", "Conclusion", "Erreur"], 24))
    parts.append(_card("Understat xG Multi-Season Lab", "\n".join(understat_lines)))
    big5_lines = [
        f"Big 5 complet: {summary.get('big5_ready_for_conclusion')}",
        f"ligues disponibles: {summary.get('big5_leagues_available')}",
        f"ligues attendues/disponibles: {summary.get('big5_total_leagues_expected')} / {summary.get('big5_total_leagues_available')}",
        f"ligues manquantes: {', '.join(summary.get('big5_missing_leagues') or []) or 'aucune'}",
        f"ligues exploitables: {summary.get('big5_leagues_exploitable')}",
        f"ligues ROI edge positif: {summary.get('big5_roi_edge_positive')}",
        f"ligues sample >= 1000: {summary.get('big5_sample_ge_1000')}",
        f"ligues avec CLV disponible: {summary.get('big5_clv_available')}",
        f"candidats robustes: {summary.get('big5_candidates')}",
        f"conclusion: {summary.get('big5_conclusion')}",
        "Rappel: aucun pick automatique.",
    ]
    if texts["big5_xg"]:
        big5_lines.extend(_lines_matching(texts["big5_xg"], ["Ligues", "Brier", "ROI", "sample", "CLV", "Candidats", "Conclusion"], 24))
    parts.append(_card("Big 5 xG Lab Summary", "\n".join(big5_lines)))

    big5_completion_lines = [
        f"attendues: {summary.get('big5_total_leagues_expected')}",
        f"disponibles: {summary.get('big5_total_leagues_available')}",
        f"manquantes: {', '.join(summary.get('big5_missing_leagues') or []) or 'aucune'}",
        f"pret pour conclusion Big 5: {summary.get('big5_ready_for_conclusion')}",
        f"bloqueur CLV: {summary.get('big5_clv_blocker')}",
        "statut final: laboratoire, aucun pick automatique.",
    ]
    parts.append(_card("Big 5 Completion Status", "\n".join(big5_completion_lines)))

    clv_readiness_lines = [
        f"statut: {summary.get('clv_readiness_status')}",
        f"CLV calculable: {summary.get('clv_calculable')}",
        f"CLV calculable maintenant: {summary.get('clv_calculable_now')}",
        f"CLV calculable apres enrichissement: {summary.get('clv_calculable_after_enrichment')}",
        f"source avec closing: {summary.get('source_has_closing')}",
        f"colonnes manquantes principales: {', '.join((summary.get('clv_missing_columns') or [])[:12]) or 'n/a'}",
        f"marches: {summary.get('clv_markets')}",
        f"commande suivante: {summary.get('recommended_next_command')}",
        "statut final: aucun pick automatique sans closing odds fiables.",
    ]
    if texts["clv_readiness"]:
        clv_readiness_lines.extend(_lines_matching(texts["clv_readiness"], ["Statut", "CLV calculable", "Colonnes", "H2H", "Over", "BTTS", "Checklist"], 24))
    parts.append(_card("CLV Readiness", "\n".join(clv_readiness_lines)))

    closing_recovery_lines = [
        f"probe disponible: {summary.get('closing_probe_available')}",
        f"source avec closing: {summary.get('source_has_closing')}",
        f"H2H closing: {summary.get('closing_probe_h2h')}",
        f"Over/Under closing: {summary.get('closing_probe_total')}",
        f"BTTS closing: {summary.get('closing_probe_btts')}",
        f"colonnes source: {', '.join(summary.get('closing_probe_columns') or []) or 'aucune'}",
        f"commande suivante: {summary.get('recommended_next_command')}",
        "Ce plan ne calcule pas la CLV et ne modifie pas data/features_modern.csv.",
    ]
    if texts["closing_odds_probe"]:
        closing_recovery_lines.extend(_lines_matching(texts["closing_odds_probe"], ["Closing", "H2H", "Total", "BTTS", "Colonnes", "Mapping", "Avertissement"], 24))
    parts.append(_card("Closing Odds Recovery Plan", "\n".join(closing_recovery_lines)))

    clv_partial_lines = [
        f"scope: {summary.get('clv_partial_scope')}",
        f"lignes avec CLV: {summary.get('clv_partial_rows')}",
        f"coverage: {summary.get('clv_partial_coverage')}%",
        f"CLV moyenne: {summary.get('clv_mean')}",
        f"CLV positive: {summary.get('clv_positive_rate')}%",
        f"marches couverts: {', '.join(summary.get('clv_partial_market_sides') or []) or 'aucun'}",
        f"marches exclus: {', '.join(summary.get('clv_partial_excluded_sides') or []) or 'n/a'}",
        "blocage: draw/total/BTTS non couverts par C_LTH/C_LTA.",
        "statut: diagnostic seulement, pas validation globale.",
    ]
    if texts["clv_partial"]:
        clv_partial_lines.extend(_lines_matching(texts["clv_partial"], ["Scope", "Coverage", "CLV moyenne", "CLV positive", "partielle", "Avertissement"], 24))
    parts.append(_card("CLV partielle / Closing odds", "\n".join(clv_partial_lines)))

    if summary.get("shadow_signals") in (None, 0):
        shadow_lines = [
            f"rapport disponible: {summary.get('shadow_report_available')}",
            "Aucun signal shadow enregistre.",
            "statut: shadow mode uniquement, aucune mise conseillee.",
        ]
    else:
        shadow_lines = [
            f"rapport disponible: {summary.get('shadow_report_available')}",
            f"signaux shadow: {summary.get('shadow_signals')}",
            f"pending closing: {summary.get('shadow_pending_closing')}",
            f"pending resultats: {summary.get('shadow_pending_results')}",
            f"coverage CLV: {summary.get('shadow_clv_coverage')}%",
            f"CLV moyenne: {summary.get('shadow_clv_mean')}",
            f"CLV positive: {summary.get('shadow_clv_positive_rate')}%",
            f"ROI resultats disponibles: {summary.get('shadow_roi')}",
            f"profit unite: {summary.get('shadow_profit')}",
            f"max drawdown: {summary.get('shadow_max_drawdown')}",
            f"sample: {summary.get('shadow_sample')}",
            f"verdict: {summary.get('shadow_verdict')}",
            f"top strategies: {', '.join(summary.get('shadow_top_strategies') or []) or 'n/a'}",
            f"top ligues: {', '.join(summary.get('shadow_top_leagues') or []) or 'n/a'}",
            f"blockers: {', '.join(summary.get('shadow_warnings') or []) or 'n/a'}",
            "statut: shadow mode uniquement, aucune mise conseillee.",
        ]
    if texts["shadow_clv"]:
        shadow_lines.extend(_lines_matching(texts["shadow_clv"], ["Signaux", "Coverage", "CLV moyenne", "CLV positive", "ROI", "Verdict", "Avertissement"], 24))
    parts.append(_card("Shadow Mode Evidence", "\n".join(shadow_lines)))

    ops_lines = [
        "statut health: voir sortie oracle_ops --health",
        "reports/ ignore et external_data/ ignore doivent rester vrais.",
        "aucun reseau, aucune mise, aucun Telegram.",
    ]
    if texts["ops_health"]:
        ops_lines.extend(_lines_matching(texts["ops_health"], ["Statut", "OK", "warning", "bloquant", "Telegram", "Railway"], 30))
    parts.append(_card("Operations Health", "\n".join(ops_lines)))

    quality_lines = [
        f"rapport disponible: {summary.get('shadow_quality_available')}",
        f"verdict: {summary.get('shadow_quality_verdict')}",
        f"coverage CLV: {summary.get('shadow_quality_clv_coverage')}%",
        f"coverage resultats: {summary.get('shadow_quality_result_coverage')}%",
        f"erreurs: {', '.join(summary.get('shadow_quality_errors') or []) or 'aucune'}",
        f"warnings: {', '.join(summary.get('shadow_quality_warnings') or []) or 'aucun'}",
    ]
    if texts["shadow_quality"]:
        quality_lines.extend(_lines_matching(texts["shadow_quality"], ["Verdict", "Coverage", "Bloquant", "Warning"], 24))
    parts.append(_card("Shadow Quality Audit", "\n".join(quality_lines)))

    evidence_lines = [
        f"rapport disponible: {summary.get('evidence_gate_available')}",
        f"statut global: {summary.get('evidence_gate_status')}",
        f"blockers: {', '.join(summary.get('evidence_gate_blockers') or []) or 'aucun'}",
        f"forces: {', '.join(summary.get('evidence_gate_strengths') or []) or 'aucune'}",
        f"next actions: {', '.join(summary.get('evidence_gate_next_steps') or []) or 'n/a'}",
        "statut final: analyse approfondie requise au maximum, aucune activation automatique.",
    ]
    if texts["evidence_gate"]:
        evidence_lines.extend(_lines_matching(texts["evidence_gate"], ["Statut global", "Bloquant", "Action requise"], 24))
    parts.append(_card("Evidence Gate", "\n".join(evidence_lines)))

    sample_lines = [
        f"rapport disponible: {summary.get('sample_plan_available')}",
        f"sample actuel: {summary.get('sample_plan_current')}",
        f"sample target edge: {summary.get('sample_plan_target_required')}",
        f"edge table: {summary.get('sample_plan_edges')}",
        "rappel: <100 bruit extreme, <500 insuffisant, <1000 non valide.",
    ]
    if texts["sample_size_plan"]:
        sample_lines.extend(_lines_matching(texts["sample_size_plan"], ["Sample", "Edge", "Warning"], 24))
    parts.append(_card("Sample Size Plan", "\n".join(sample_lines)))

    message_lines = [
        "preview texte seulement, aucun envoi Telegram.",
        "statut: observation seulement.",
    ]
    if texts["shadow_message_preview"]:
        message_lines.extend(texts["shadow_message_preview"].splitlines()[:24])
    parts.append(_card("Shadow Message Preview", "\n".join(message_lines)))

    workflow_lines = [
        "1. Verifier les observations shadow du jour.",
        "2. Generer les templates closing/resultats.",
        "3. Renseigner uniquement des closing odds reelles.",
        "4. Importer les resultats manuels.",
        "5. Relancer shadow_clv_report.py.",
        "6. Lire evidence_gate.py.",
        "7. Continuer la collecte tant que sample < 1000.",
        "Aucune mise conseillee.",
    ]
    parts.append(_card("Manual Workflow Checklist", "\n".join(workflow_lines)))

    odds_lab_lines = [
        f"rapport quality disponible: {summary.get('odds_quality_available')}",
        f"lignes snapshots: {summary.get('odds_rows_total')}",
        f"sources: {summary.get('odds_sources')}",
        f"bookmakers: {summary.get('odds_bookmakers')}",
        f"ligues: {summary.get('odds_leagues')}",
        f"marches: {summary.get('odds_markets')}",
        "statut: laboratoire local, aucun reseau automatique.",
    ]
    if texts["odds_source_config"]:
        odds_lab_lines.extend(_lines_matching(texts["odds_source_config"], ["Configuration", "Cle API", "Validation", "Warning", "Erreur"], 20))
    parts.append(_card("Odds Source Lab", "\n".join(odds_lab_lines)))

    snapshot_lines = [
        f"lignes totales: {summary.get('odds_rows_total')}",
        f"lignes invalides: {summary.get('odds_invalid_rows')}",
        f"doublons: {odds_summary.get('duplicates') if odds_summary else 'n/a'}",
        f"dates min/max: {odds_summary.get('date_min') if odds_summary else None} / {odds_summary.get('date_max') if odds_summary else None}",
    ]
    if texts["odds_snapshot_summary"]:
        snapshot_lines.extend(_lines_matching(texts["odds_snapshot_summary"], ["Lignes", "Sources", "Bookmakers", "Marches", "Doublons"], 20))
    parts.append(_card("Odds Snapshot Coverage", "\n".join(snapshot_lines)))

    near_close_lines = [
        f"snapshots near-close: {summary.get('odds_near_close_rows')}",
        f"capacite CLV: {summary.get('odds_clv_capacity')}",
        f"recommandations: {', '.join(summary.get('odds_recommendations') or []) or 'aucune'}",
        "un snapshot near-close n'est pas une preuve historique parfaite sans controle de source et timestamp.",
    ]
    if texts["odds_source_quality"]:
        near_close_lines.extend(_lines_matching(texts["odds_source_quality"], ["near-close", "Capacite", "Recommandations", "invalides"], 20))
    parts.append(_card("Near-Close Coverage", "\n".join(near_close_lines)))

    odds_shadow_lines = [
        f"rapport disponible: {summary.get('odds_to_shadow_available')}",
        f"observations ajoutees/simulees: {summary.get('odds_to_shadow_added')}",
        f"dry-run: {summary.get('odds_to_shadow_dry_run')}",
        "par defaut, l'intake cree seulement des observations shadow.",
    ]
    if texts["odds_to_shadow"]:
        odds_shadow_lines.extend(_lines_matching(texts["odds_to_shadow"], ["Observations", "Doublons", "Erreurs", "shadow"], 20))
    parts.append(_card("Odds to Shadow Intake", "\n".join(odds_shadow_lines)))

    closing_match_lines = [
        f"rapport disponible: {summary.get('odds_closing_matcher_available')}",
        f"correspondances trouvees: {summary.get('odds_closing_matches')}",
        f"closing mises a jour: {summary.get('odds_closing_updates')}",
        "aucune cote closing n'est inventee; les ambiguites restent ignorees.",
    ]
    if texts["odds_closing_matcher"]:
        closing_match_lines.extend(_lines_matching(texts["odds_closing_matcher"], ["Correspondances", "Closing", "Ambiguites", "Non matches"], 20))
    parts.append(_card("Closing Matcher Status", "\n".join(closing_match_lines)))

    source_quality_lines = [
        f"lignes valides: {odds_quality.get('valid_rows') if odds_quality else 'n/a'}",
        f"lignes invalides: {summary.get('odds_invalid_rows')}",
        f"marches couverts: {odds_quality.get('markets_covered') if odds_quality else 'n/a'}",
        f"capacite CLV: {summary.get('odds_clv_capacity')}",
        f"recommandations: {', '.join(summary.get('odds_recommendations') or []) or 'aucune'}",
    ]
    parts.append(_card("Source Quality", "\n".join(source_quality_lines)))

    intake_lines = [
        f"rapport disponible: {summary.get('odds_intake_available')}",
        f"taken snapshots: {summary.get('odds_intake_taken')}",
        f"near-close snapshots: {summary.get('odds_intake_near_close')}",
        f"valid odds: {summary.get('odds_intake_valid')}",
        f"invalid odds: {summary.get('odds_intake_invalid')}",
        f"observations shadow liees: {summary.get('odds_intake_linked')}",
        f"closing match coverage possible: {summary.get('odds_intake_possible_coverage')}%",
        f"closing coverage reelle: {summary.get('odds_intake_real_coverage')}%",
        f"verdict intake: {summary.get('odds_intake_verdict')}",
        f"next actions: {', '.join(summary.get('odds_intake_next') or []) or 'n/a'}",
    ]
    if texts["odds_intake_audit"]:
        intake_lines.extend(_lines_matching(texts["odds_intake_audit"], ["Snapshots", "Coverage", "Verdict", "Action"], 20))
    parts.append(_card("Odds Intake Workflow", "\n".join(intake_lines)))

    architecture_lines = [
        f"blocs detectes: {summary.get('architecture_blocks')}",
        "regle: les donnees alimentent, les modules mesurent, l'agent orchestre, le LLM explique.",
        "statut: architecture locale de laboratoire, aucune activation automatique.",
    ]
    if texts["architecture_map"]:
        architecture_lines.extend(_lines_matching(texts["architecture_map"], ["Sources", "Collecte", "Moteur", "LLM", "Restitution", "Boucle"], 20))
    parts.append(_card("Architecture canonique", "\n".join(architecture_lines)))

    contract_lines = [
        f"contrats disponibles: {summary.get('pipeline_contracts_count')}",
        "contrats: match_source, odds_snapshot, feature_row, shadow_ledger, closing_import, result_import, signal_evaluation, llm_analyst_input, restitution_output, evidence_gate.",
        "validation: les fichiers sont lus seulement, jamais modifies.",
    ]
    if texts["pipeline_contracts"]:
        contract_lines.extend(_lines_matching(texts["pipeline_contracts"], ["Contrats", "odds_snapshot", "shadow_ledger", "evidence_gate"], 20))
    parts.append(_card("Pipeline contracts", "\n".join(contract_lines)))

    llm_lines = [
        "Le LLM analyste explique seulement les mesures fournies.",
        "Il ne calcule pas l'edge, ne cree aucune cote et ne depasse pas evidence_gate.",
        "Sortie maximale: analyse approfondie requise.",
    ]
    if texts["llm_analyst_contract"]:
        llm_lines.extend(_lines_matching(texts["llm_analyst_contract"], ["LLM", "source", "Labels", "evidence"], 20))
    parts.append(_card("LLM analyst contract", "\n".join(llm_lines)))

    restitution_lines = [
        "format: evenement, analyse, observation, confiance, risques, limites, decision, prochaine action.",
        "actions autorisees limitees: collecter closing, attendre resultat, relancer evidence gate, observation seulement, refuser.",
    ]
    if texts["restitution_schema"]:
        restitution_lines.extend(_lines_matching(texts["restitution_schema"], ["Restitution", "Decision", "Actions"], 20))
    parts.append(_card("Restitution schema", "\n".join(restitution_lines)))

    progress_lines = [
        "boucle: collecter -> tester -> mesurer -> corriger -> documenter.",
        "journal local dans reports/progress_loop.csv si initialise.",
    ]
    if texts["progress_loop"]:
        progress_lines.extend(_lines_matching(texts["progress_loop"], ["Resume", "entries", "collecter", "corriger"], 20))
    parts.append(_card("Progress loop", "\n".join(progress_lines)))

    scorecard_lines = [
        f"score global: {summary.get('project_scorecard_global')}",
        f"preuve betting reelle: {summary.get('project_scorecard_real_proof')}",
        "candidats robustes: 0 tant que CLV/sample restent insuffisants.",
    ]
    if texts["project_scorecard"]:
        scorecard_lines.extend(_lines_matching(texts["project_scorecard"], ["Score", "Preuve", "Statut"], 20))
    parts.append(_card("Project scorecard", "\n".join(scorecard_lines)))

    agent_lines = [
        "dry-run uniquement: verification health, snapshots, ledger, templates, audits, evidence gate, restitution.",
        "aucun reseau, aucun Telegram, aucune mise.",
    ]
    if texts["agent_orchestrator_dryrun"]:
        agent_lines.extend(_lines_matching(texts["agent_orchestrator_dryrun"], ["Dry-run", "Verifier", "evidence", "Telegram"], 24))
    parts.append(_card("Agent dry-run", "\n".join(agent_lines)))

    parts.append(_card("Next actions", "\n".join([
        "1. Continuer la collecte shadow.",
        "2. Renseigner near-close reelles.",
        "3. Relancer evidence gate.",
        "4. Journaliser la boucle de progression.",
        "5. Ne pas conclure avant sample significatif.",
    ])))

    league_rows = []
    for item in (big5_xg.get("leagues") or []):
        if not item.get("dataset_present"):
            continue
        league_rows.append(
            f"{item.get('league')}: Brier marche/xG={item.get('market_brier')}/{item.get('xg_brier')}, "
            f"log loss marche/xG={item.get('market_log_loss')}/{item.get('xg_log_loss')}, "
            f"ROI={item.get('roi_edge_test')}, sample={item.get('sample_edge_test')}, statut={item.get('status')}"
        )
    parts.append(_card("League-by-league xG comparison", "\n".join(league_rows) or "Aucun rapport de ligue disponible."))

    readiness_rows = []
    for item in (big5_xg.get("leagues") or []):
        readiness_rows.append(
            f"{item.get('league')}: present={item.get('dataset_present')}, quality={item.get('quality_verdict')}, "
            f"join={item.get('join_rate')} ({item.get('join_quality')}), sample={item.get('sample_edge_test')}, "
            f"CLV={item.get('clv_available')}, promotion={item.get('promotion_allowed')}"
        )
    parts.append(_card("League readiness table", "\n".join(readiness_rows) or "Aucune table Big 5 disponible."))

    blockers = []
    if summary.get("clv_calculable") is False:
        blockers.append("CLV non calculable depuis la feature matrix actuelle.")
    if summary.get("big5_candidates") in (0, None):
        blockers.append("Aucun candidat robuste Big 5.")
    if summary.get("big5_sample_ge_1000") in (0, None):
        blockers.append("Sample edge test insuffisant sur les observations disponibles.")
    blockers.append("Telegram/Railway restent en attente.")
    parts.append(_card("Promotion blockers", "\n".join(blockers)))
    clv_lines = [
        f"statut: {summary.get('clv_status')}",
        f"CLV moyenne: {summary.get('clv_mean')}",
        f"CLV positive: {summary.get('clv_positive_rate')}%",
        "verdict: aucune promotion possible sans CLV positive et source fiable",
    ]
    if texts["clv"]:
        clv_lines.extend(_lines_matching(texts["clv"], ["Statut", "Message", "CLV moyenne", "CLV positive", "Verdict", "Avertissement"], 18))
    parts.append(_card("CLV / Closing Line Value", "\n".join(clv_lines)))

    calibration_lines = [
        f"Brier: {summary.get('calibration_brier')}",
        f"Log loss: {summary.get('calibration_log_loss')}",
        f"ECE: {summary.get('calibration_ece')}",
        f"MCE: {summary.get('calibration_mce')}",
    ]
    if texts["calibration"]:
        calibration_lines.extend(_lines_matching(texts["calibration"], ["Brier", "Log loss", "ECE", "MCE", "Verdict"], 18))
    parts.append(_card("Calibration probabiliste", "\n".join(calibration_lines)))

    stat_lines = [
        f"IC ROI: {summary.get('stat_roi_ci_low')} -> {summary.get('stat_roi_ci_high')}",
        f"Bootstrap ROI p05/p50/p95: {summary.get('stat_bootstrap_p05')} / {summary.get('stat_bootstrap_p50')} / {summary.get('stat_bootstrap_p95')}",
        f"Sample size approx: {summary.get('stat_sample_size_needed')}",
    ]
    if texts["statistical_validation"]:
        stat_lines.extend(_lines_matching(texts["statistical_validation"], ["Picks", "ROI observe", "IC ROI", "Bootstrap", "p-value", "Verdict"], 24))
    parts.append(_card("Validation statistique", "\n".join(stat_lines)))

    multiple_lines = [
        f"Strategie survivant correction: {summary.get('strategies_surviving_multiple_testing')}",
        "Correction: Benjamini-Hochberg quand plusieurs strategies sont presentes.",
        "Tout signal positif non corrige reste fragile.",
    ]
    parts.append(_card("Multiple testing", "\n".join(multiple_lines)))

    governance_lines = []
    if texts["benchmark_governance"]:
        governance_lines.extend(_lines_matching(texts["benchmark_governance"], ["Top gouvernance", "score=", "Conclusion", "Sections indisponibles", "Modeles/strategies"], 24))
    if registry:
        governance_lines.append("--- model_registry.json ---")
        for entry in registry[:12]:
            governance_lines.append(
                f"{entry.get('name')}: score={entry.get('robustness_score')}, statut={entry.get('status')}, "
                f"decision={entry.get('decision')}, raison={entry.get('reason', '')}"
            )
    governance_lines.append(f"signaux rejetes: {summary.get('signals_rejected')}")
    governance_lines.append(f"raison principale: {summary.get('main_rejection_reason')}")
    governance_lines.append(f"statut final: {summary.get('final_status')}")
    parts.append(_card("Gouvernance finale", "\n".join(governance_lines)))
    conclusion = "\n".join([
        summary["conclusion"],
        "Observations seulement: aucune sortie de ce rapport ne modifie Telegram, Railway ou la DB.",
        "Prochaines etapes: verifier le quality gate Understat xG, puis lire rolling/model/gouvernance sans activer de pick.",
    ])
    parts.append(_card("Conclusion prudente", conclusion))
    parts.append("</body></html>")

    (report_dir / "index.html").write_text("\n".join(parts), encoding="utf-8")
    (report_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Construit un dashboard HTML local depuis les sorties de report_runner.")
    parser.add_argument("--latest", action="store_true", help="Utilise le dernier dossier reports/")
    parser.add_argument("--input", default="", help="Dossier de rapport a lire")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    report_dir = latest_report_dir() if args.latest or not args.input else Path(args.input)
    if report_dir is None:
        raise SystemExit("Aucun dossier de rapport trouve.")
    summary = build_dashboard(report_dir)
    print("Dashboard central Oracle Bot")
    print(f"- Dossier: {report_dir}")
    print(f"- HTML: {report_dir / 'index.html'}")
    print(f"- JSON: {report_dir / 'summary.json'}")
    print(f"- Conclusion: {summary.get('conclusion')}")


if __name__ == "__main__":
    main()
