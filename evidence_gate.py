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
    blockers: List[str] = []
    strengths: List[str] = []
    next_steps: List[str] = []
    if not any([shadow, quality, big5, clv, benchmark, stats, calibration, real_guard, matchday_status]):
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
        if real_guard.get("taken_without_near_close_count", 0):
            blockers.append("taken sans near-close")
    if matchday_status:
        taken = matchday_status.get("taken") or {}
        near = matchday_status.get("near_close") or {}
        results = matchday_status.get("results") or {}
        if not matchday_status.get("ready_for_dry_run"):
            blockers.append("matchday incomplet")
        if (taken.get("filled") or 0) == 0:
            blockers.append("matchday sans taken odds")
        if (near.get("filled") or 0) == 0:
            blockers.append("matchday sans near-close")
        if (results.get("filled") or 0) == 0:
            blockers.append("resultats manquants")
    if real_guard and real_guard.get("verdict") in {"mixed_test_and_real", "invalid"}:
        status = "blocked"
    elif quality.get("verdict") == "invalid" or any("CLV moyenne <= 0" == item for item in blockers):
        status = "blocked"
    elif sample >= 1000 and clv_coverage >= 80.0 and clv_mean is not None and _num(clv_mean) > 0 and roi is not None and _num(roi) > 0 and quality.get("verdict") in {"clean", "usable_with_warnings"}:
        status = "ready_for_deep_review"
    elif sample > 0 and (clv_mean is not None and _num(clv_mean) > 0):
        status = "promising_but_unvalidated"
    elif sample > 0 or shadow or quality:
        status = "insufficient_evidence"
    if status == "ready_for_deep_review":
        next_steps.append("Effectuer une revue humaine complete avant toute decision")
    next_steps.append("Ne pas activer Telegram")
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
        "blockers": seen_blockers,
        "strengths": sorted(set(strengths)),
        "required_next_steps": seen_steps,
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
