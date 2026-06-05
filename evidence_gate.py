import argparse
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def ensure_reports_path(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le rapport evidence gate ne doit pas etre ecrit dans data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def read_json(path: str) -> Dict[str, Any]:
    if not path or not Path(path).exists():
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def build_evidence_gate(
    shadow_report_path: str = "",
    quality_audit_path: str = "",
    big5_summary_path: str = "",
    clv_readiness_path: str = "",
    benchmark_summary_path: str = "",
    statistical_validation_path: str = "",
    calibration_report_path: str = "",
    real_guard_path: str = "",
    matchday_status_path: str = "",
    lifecycle_path: str = "",
    historical_clv_path: str = "",
    proof_dashboard_path: str = "",
    next_days_path: str = "",
    near_close_window_path: str = "",
    post_match_results_path: str = "",
    football_data_import_path: str = "",
    subscription_evaluator_path: str = "",
) -> Dict[str, Any]:
    shadow = read_json(shadow_report_path)
    quality = read_json(quality_audit_path)
    big5 = read_json(big5_summary_path)
    clv = read_json(clv_readiness_path)
    benchmark = read_json(benchmark_summary_path)
    stats = read_json(statistical_validation_path)
    calibration = read_json(calibration_report_path)
    real_guard = read_json(real_guard_path)
    matchday_status = read_json(matchday_status_path)
    lifecycle = read_json(lifecycle_path)
    historical_clv = read_json(historical_clv_path)
    proof_dashboard = read_json(proof_dashboard_path)
    next_days = read_json(next_days_path)
    near_close_window = read_json(near_close_window_path)
    post_match_results = read_json(post_match_results_path)
    football_data_import = read_json(football_data_import_path)
    subscription = read_json(subscription_evaluator_path)
    blockers: List[str] = []
    warnings: List[str] = []
    strengths: List[str] = []
    next_steps: List[str] = []
    if not any([shadow, quality, big5, clv, benchmark, stats, calibration, real_guard, matchday_status, lifecycle, historical_clv, proof_dashboard, next_days, near_close_window, post_match_results, football_data_import, subscription]):
        blockers.append("Aucun rapport de preuve disponible")
        next_steps.append("Generer shadow_clv_report.py et shadow_quality_audit.py")
        status = "not_started"
    else:
        status = "collecting_evidence"
    sample = int(_num(shadow.get("sample_size") or shadow.get("signals_total"), 0))
    clv_coverage = _num(shadow.get("clv_coverage"), 0.0)
    clv_mean = shadow.get("clv_mean")
    roi = shadow.get("roi")
    if shadow:
        strengths.append("Shadow workflow pret")
        if sample < 1000:
            blockers.append("sample shadow < 1000")
            next_steps.append(f"Collecter encore {1000 - sample} observations shadow minimum")
        if clv_coverage < 80.0:
            blockers.append("CLV coverage < 80%")
            next_steps.append("Renseigner les closing odds manuelles manquantes")
        if clv_mean is None:
            blockers.append("CLV absente")
            next_steps.append("Importer des closing odds decimales reelles")
        elif _num(clv_mean) <= 0:
            blockers.append("CLV moyenne <= 0")
        else:
            strengths.append("CLV shadow moyenne positive")
        if roi is None:
            blockers.append("ROI shadow indisponible")
            next_steps.append("Importer les resultats manuels")
        elif _num(roi) <= 0:
            blockers.append("ROI shadow <= 0")
        else:
            strengths.append("ROI shadow positif, a lire avec prudence")
        if shadow.get("verdict") in {"not_validated", "clv_negative"}:
            blockers.append(f"verdict shadow: {shadow.get('verdict')}")
    if quality:
        verdict = quality.get("verdict")
        if verdict == "invalid":
            blockers.append("ledger quality invalid")
        elif verdict in {"poor_quality", "usable_with_warnings"}:
            blockers.append(f"ledger quality: {verdict}")
        elif verdict == "clean":
            strengths.append("Ledger shadow clean")
        if quality.get("missing_closing"):
            blockers.append("closing missing dans le ledger")
        if quality.get("missing_results"):
            blockers.append("results missing dans le ledger")
    if big5:
        global_data = big5.get("global") or {}
        if global_data.get("ready_for_big5_conclusion"):
            strengths.append("Big5 complete")
        if (global_data.get("leagues_xg_improves_brier") or 0) or (global_data.get("leagues_xg_improves_log_loss") or 0):
            strengths.append("xG ameliore Brier/log loss sur certaines ligues")
        if (global_data.get("leagues_sample_ge_1000") or 0) == 0:
            blockers.append("Big5 sample edge insuffisant")
        if (global_data.get("leagues_clv_available") or 0) == 0:
            blockers.append("Big5 sans CLV disponible")
    if clv:
        if not clv.get("clv_calculable") and not clv.get("clv_calculable_now"):
            blockers.append("CLV readiness: CLV non calculable maintenant")
        if clv.get("clv_scope") not in {None, "", "full", "complete_h2h"}:
            blockers.append(f"CLV scope partiel: {clv.get('clv_scope')}")
    if benchmark:
        if benchmark.get("robust_candidates", 0) == 0:
            blockers.append("benchmark: aucun candidat robuste")
        else:
            strengths.append("benchmark: candidats a revue detectes")
    if stats:
        summary = stats.get("summary") or {}
        if (summary.get("p_value_adjusted") is None) and not (stats.get("by_strategy") or {}):
            blockers.append("multiple testing non confirme")
    if calibration:
        if calibration.get("ece") is not None:
            strengths.append("calibration disponible")
    if real_guard:
        verdict = real_guard.get("verdict")
        guard_phase = real_guard.get("phase") or "full_day"
        if verdict == "clean_real_collection":
            strengths.append("guard reel clean")
        elif verdict == "empty":
            blockers.append("guard reel: collecte vide")
        elif verdict in {"mixed_test_and_real", "invalid"}:
            blockers.append(f"guard reel: {verdict}")
        elif verdict == "needs_review":
            blockers.append("guard reel: verification humaine requise")
        if real_guard.get("near_close_without_taken_count", 0):
            blockers.append("near-close sans taken")
        if real_guard.get("taken_without_near_close_count", 0) and guard_phase in {"near_close", "post_match", "full_day"}:
            blockers.append("taken sans near-close")
    if matchday_status:
        detected = matchday_status.get("phase_detected")
        taken = matchday_status.get("taken") or {}
        near = matchday_status.get("near_close") or {}
        results = matchday_status.get("results") or {}
        if detected:
            if detected == "invalid":
                blockers.append("matchday invalid")
            elif detected == "empty":
                blockers.append("matchday vide")
                next_steps.append("Renseigner les taken odds reelles du pack matchday")
            elif detected in {"pre_match_ready", "waiting_near_close"}:
                strengths.append("matchday pre_match pret")
                next_steps.append("Collecter la near-close reelle plus tard")
            elif detected in {"near_close_ready", "waiting_results"}:
                strengths.append("matchday near_close pret")
                next_steps.append("Collecter le resultat manuel apres match")
            elif detected in {"post_match_ready", "complete"}:
                strengths.append("matchday post_match pret")
            for item in matchday_status.get("blockers") or []:
                blockers.append(f"matchday: {item}")
        else:
            if not matchday_status.get("ready_for_dry_run"):
                blockers.append("matchday incomplet")
            if (taken.get("filled") or 0) == 0:
                blockers.append("matchday sans taken odds")
            if (near.get("filled") or 0) == 0:
                blockers.append("matchday sans near-close")
            if (results.get("filled") or 0) == 0:
                blockers.append("resultats manquants")
    if lifecycle:
        counts = lifecycle.get("status_counts") or {}
        pending_closing = int(_num(lifecycle.get("pending_closing"), 0))
        completed = int(_num(lifecycle.get("completed"), 0))
        near_overdue = int(_num(counts.get("near_close_overdue"), 0))
        result_overdue = int(_num(counts.get("result_overdue"), 0))
        due_soon = int(_num(counts.get("near_close_due_soon"), 0))
        if near_overdue:
            blockers.append("near-close overdue")
            next_steps.append("Rattraper ou documenter les near-close manquees")
        if result_overdue:
            blockers.append("resultats overdue")
            next_steps.append("Importer les resultats manuels dus")
        if due_soon:
            warnings.append("near-close due soon")
            next_steps.append("Capturer les near-close proches du kickoff")
        if pending_closing and near_overdue == 0:
            warnings.append("pending closing futur normal en pre_match")
        if pending_closing > max(completed * 3, 3):
            warnings.append("pending closing eleve vs observations completes")
        if completed < 30:
            warnings.append("observations completes < 30")
        if completed < 1000:
            warnings.append("observations completes < 1000")
    historical_summary = historical_clv.get("summary") or {}
    historical_sample = int(_num(historical_summary.get("sample"), 0))
    historical_clv_mean = historical_summary.get("clv_mean")
    historical_roi = historical_summary.get("roi_unit")
    if historical_clv:
        strengths.append("Preuve historique CLV disponible")
        if historical_sample < 1000:
            blockers.append("sample historique CLV < 1000")
        if historical_clv_mean is None:
            blockers.append("CLV historique absente")
        elif _num(historical_clv_mean) <= 0:
            blockers.append("CLV historique moyenne <= 0")
        else:
            strengths.append("CLV historique moyenne positive")
        if historical_roi is None:
            blockers.append("ROI historique indisponible")
        elif _num(historical_roi) <= 0:
            blockers.append("ROI historique <= 0")
        for blocker in historical_clv.get("blockers") or []:
            blockers.append(f"historique: {blocker}")
        warnings.append("preuve historique seule: live shadow toujours requis")
    if proof_dashboard:
        if proof_dashboard.get("global_status"):
            strengths.append(f"proof dashboard: {proof_dashboard.get('global_status')}")
        for blocker in proof_dashboard.get("blockers") or []:
            blockers.append(f"proof dashboard: {blocker}")
    completed_shadow_count = int(_num((shadow.get("settled_count") or shadow.get("completed") or 0), 0))
    pending_closing_count = int(_num((quality.get("missing_closing") or lifecycle.get("pending_closing") or near_close_window.get("due_now_count") or 0), 0))
    pending_results_count = int(_num((quality.get("missing_results") or lifecycle.get("pending_results") or post_match_results.get("unmatched") or 0), 0))
    historical_data_available = bool(historical_clv)
    free_historical_data_available = bool(football_data_import.get("has_odds"))
    quota_status = subscription.get("quota_status")
    subscription_recommendation = subscription.get("recommendation") or subscription.get("subscription_recommendation")
    if next_days:
        if int(_num(next_days.get("selected_total"), 0)) > 0:
            strengths.append("next-days: observations futures detectees")
        else:
            warnings.append("next-days: aucune selection future")
    if near_close_window:
        due = int(_num(near_close_window.get("due_now_count"), 0))
        overdue = int(_num(near_close_window.get("overdue_count"), 0))
        if due:
            warnings.append("near-close due now")
        if overdue:
            blockers.append("near-close window overdue")
    if post_match_results:
        if int(_num(post_match_results.get("matched"), 0)):
            strengths.append("resultats post-match matchables")
        if int(_num(post_match_results.get("unmatched"), 0)):
            blockers.append("resultats post-match non matches")
    if football_data_import:
        if football_data_import.get("has_odds"):
            strengths.append("donnees Football-Data gratuites disponibles")
        if football_data_import.get("has_odds") and not football_data_import.get("has_true_closing_odds"):
            blockers.append("Football-Data gratuit: closing vraie non confirmee")
    if subscription_recommendation:
        warnings.append(f"subscription recommendation: {subscription_recommendation}")
    if real_guard and real_guard.get("verdict") in {"mixed_test_and_real", "invalid"}:
        status = "blocked"
    elif quality.get("verdict") == "invalid" or any("CLV moyenne <= 0" == item for item in blockers):
        status = "blocked"
    elif sample >= 1000 and clv_coverage >= 80.0 and clv_mean is not None and _num(clv_mean) > 0 and roi is not None and _num(roi) > 0 and quality.get("verdict") in {"clean", "usable_with_warnings"}:
        status = "ready_for_deep_review"
    elif sample > 0 and (clv_mean is not None and _num(clv_mean) > 0):
        status = "promising_but_unvalidated"
    elif historical_clv and not shadow and historical_sample:
        status = "historical_evidence_only"
    elif sample > 0 or shadow or quality:
        status = "insufficient_evidence"
    if status == "ready_for_deep_review":
        next_steps.append("Effectuer une revue humaine complete avant toute decision")
    next_steps.append("Telegram read-only possible uniquement comme lecture laboratoire")
    next_steps.append("Ne pas activer Telegram live agressif")
    next_steps.append("Ne pas creer de mise automatique")
    seen_blockers = []
    for item in blockers:
        if item not in seen_blockers:
            seen_blockers.append(item)
    seen_steps = []
    for item in next_steps:
        if item not in seen_steps:
            seen_steps.append(item)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "global_status": status,
        "not_validated": status != "ready_for_deep_review",
        "shadow_sample": sample,
        "shadow_clv_coverage": clv_coverage,
        "shadow_clv_mean": clv_mean,
        "shadow_roi": roi,
        "completed_shadow_count": completed_shadow_count,
        "pending_closing_count": pending_closing_count,
        "pending_results_count": pending_results_count,
        "historical_data_available": historical_data_available,
        "free_historical_data_available": free_historical_data_available,
        "quota_status": quota_status,
        "subscription_recommendation": subscription_recommendation,
        "blockers": seen_blockers,
        "warnings": sorted(set(warnings)),
        "strengths": sorted(set(strengths)),
        "required_next_steps": seen_steps,
        "telegram_read_only_allowed": True,
        "telegram_live_pick_allowed": False,
        "telegram_policy": {
            "requires_observation_shadow_wording": True,
            "no_staking": True,
            "no_auto_pick": True,
            "can_influence_picks": False,
            "lab_only": True,
        },
        "source_reports": {
            "shadow_report": shadow_report_path or None,
            "quality_audit": quality_audit_path or None,
            "big5_summary": big5_summary_path or None,
            "clv_readiness": clv_readiness_path or None,
            "benchmark_summary": benchmark_summary_path or None,
            "statistical_validation": statistical_validation_path or None,
            "calibration_report": calibration_report_path or None,
            "real_guard": real_guard_path or None,
            "matchday_status": matchday_status_path or None,
            "lifecycle": lifecycle_path or None,
            "historical_clv": historical_clv_path or None,
            "proof_dashboard": proof_dashboard_path or None,
            "next_days": next_days_path or None,
            "near_close_window": near_close_window_path or None,
            "post_match_results": post_match_results_path or None,
            "football_data_import": football_data_import_path or None,
            "subscription_evaluator": subscription_evaluator_path or None,
        },
        "lab_only": True,
        "can_influence_picks": False,
        "message": "Evidence gate local: observation seulement, aucune mise conseillee.",
    }


def write_json(report: Dict[str, Any], path: str) -> Path:
    target = ensure_reports_path(path)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], path: str) -> Path:
    target = ensure_reports_path(path)
    blockers = "".join(f"<li>{html.escape(str(item))}</li>" for item in report.get("blockers") or [])
    warnings = "".join(f"<li>{html.escape(str(item))}</li>" for item in report.get("warnings") or [])
    strengths = "".join(f"<li>{html.escape(str(item))}</li>" for item in report.get("strengths") or [])
    steps = "".join(f"<li>{html.escape(str(item))}</li>" for item in report.get("required_next_steps") or [])
    target.write_text("\n".join([
        "<!doctype html>",
        "<html lang='fr'><head><meta charset='utf-8'><title>Evidence Gate</title>",
        "<style>body{font-family:Arial,sans-serif;margin:32px;color:#1f2933}.warn{background:#fff7ed;border:1px solid #fed7aa;padding:12px;border-radius:6px}</style>",
        "</head><body><h1>Evidence Gate Oracle Bot</h1>",
        f"<p><strong>Statut global:</strong> {html.escape(str(report.get('global_status')))}</p>",
        f"<p>{html.escape(str(report.get('message')))}</p>",
        f"<section class='warn'><h2>Blockers</h2><ul>{blockers or '<li>Aucun</li>'}</ul></section>",
        f"<section><h2>Warnings</h2><ul>{warnings or '<li>Aucun</li>'}</ul></section>",
        f"<section><h2>Forces</h2><ul>{strengths or '<li>Aucune</li>'}</ul></section>",
        f"<section><h2>Prochaines actions</h2><ul>{steps}</ul></section>",
        "</body></html>",
    ]), encoding="utf-8")
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Evidence Gate Oracle Bot")
    print(f"- Statut global: {report.get('global_status')}")
    print(f"- Sample shadow: {report.get('shadow_sample')}")
    print(f"- CLV coverage: {report.get('shadow_clv_coverage')}%")
    for blocker in report.get("blockers") or []:
        print(f"- Bloquant: {blocker}")
    for warning in report.get("warnings") or []:
        print(f"- Warning: {warning}")
    for step in report.get("required_next_steps") or []:
        print(f"- Action requise: {step}")
    print("- Observation seulement, aucune mise conseillee.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Centralise le gate de preuve Oracle Bot.")
    parser.add_argument("--shadow-report", default="")
    parser.add_argument("--quality-audit", default="")
    parser.add_argument("--big5-summary", default="")
    parser.add_argument("--clv-readiness", default="")
    parser.add_argument("--benchmark-summary", default="")
    parser.add_argument("--statistical-validation", default="")
    parser.add_argument("--calibration-report", default="")
    parser.add_argument("--real-guard", default="")
    parser.add_argument("--matchday-status", default="")
    parser.add_argument("--lifecycle", default="")
    parser.add_argument("--historical-clv", default="")
    parser.add_argument("--proof-dashboard", default="")
    parser.add_argument("--next-days", default="")
    parser.add_argument("--near-close-window", default="")
    parser.add_argument("--post-match-results", default="")
    parser.add_argument("--football-data-import", default="")
    parser.add_argument("--subscription-evaluator", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = build_evidence_gate(
            shadow_report_path=args.shadow_report,
            quality_audit_path=args.quality_audit,
            big5_summary_path=args.big5_summary,
            clv_readiness_path=args.clv_readiness,
            benchmark_summary_path=args.benchmark_summary,
            statistical_validation_path=args.statistical_validation,
            calibration_report_path=args.calibration_report,
            real_guard_path=args.real_guard,
            matchday_status_path=args.matchday_status,
            lifecycle_path=args.lifecycle,
            historical_clv_path=args.historical_clv,
            proof_dashboard_path=args.proof_dashboard,
            next_days_path=args.next_days,
            near_close_window_path=args.near_close_window,
            post_match_results_path=args.post_match_results,
            football_data_import_path=args.football_data_import,
            subscription_evaluator_path=args.subscription_evaluator,
        )
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
