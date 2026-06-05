import argparse
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


def _read_json(path: str) -> Dict[str, Any]:
    if not path or not Path(path).exists():
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le proof dashboard doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def build_dashboard(
    shadow_path: str = "",
    evidence_path: str = "",
    big5_path: str = "",
    historical_clv_path: str = "",
    quality_path: str = "",
    intake_path: str = "",
    same_day_path: str = "",
    near_close_today_path: str = "",
    next_days_path: str = "",
    near_close_window_path: str = "",
    post_match_results_path: str = "",
    football_data_import_path: str = "",
    subscription_evaluator_path: str = "",
) -> Dict[str, Any]:
    shadow = _read_json(shadow_path)
    evidence = _read_json(evidence_path)
    big5 = _read_json(big5_path)
    historical = _read_json(historical_clv_path)
    quality = _read_json(quality_path)
    intake = _read_json(intake_path)
    same_day = _read_json(same_day_path)
    near_close_today = _read_json(near_close_today_path)
    next_days = _read_json(next_days_path)
    near_close_window = _read_json(near_close_window_path)
    post_match_results = _read_json(post_match_results_path)
    football_data_import = _read_json(football_data_import_path)
    subscription = _read_json(subscription_evaluator_path)
    blockers = []
    if evidence.get("blockers"):
        blockers.extend(evidence.get("blockers") or [])
    if historical:
        blockers.extend(historical.get("blockers") or [])
    if (shadow.get("sample_size") or shadow.get("signals_total") or 0) < 1000:
        blockers.append("sample shadow < 1000")
    if not shadow.get("clv_mean"):
        blockers.append("CLV shadow absente")
    global_big5 = big5.get("global") or {}
    sections = {
        "shadow": {
            "available": bool(shadow),
            "sample": shadow.get("sample_size") or shadow.get("signals_total"),
            "clv_mean": shadow.get("clv_mean"),
            "clv_coverage": shadow.get("clv_coverage"),
            "roi": shadow.get("roi"),
            "verdict": shadow.get("verdict"),
        },
        "evidence_gate": {
            "available": bool(evidence),
            "global_status": evidence.get("global_status"),
            "blockers": evidence.get("blockers") or [],
            "strengths": evidence.get("strengths") or [],
        },
        "big5": {
            "available": bool(big5),
            "complete": global_big5.get("ready_for_big5_conclusion"),
            "leagues_available": global_big5.get("total_leagues_available") or global_big5.get("leagues_available"),
            "robust_candidates": global_big5.get("big5_candidate_count") or global_big5.get("leagues_candidates") or 0,
            "clv_blocker": global_big5.get("clv_blocker"),
        },
        "historical_clv": {
            "available": bool(historical),
            "sample": (historical.get("summary") or {}).get("sample"),
            "clv_mean": (historical.get("summary") or {}).get("clv_mean"),
            "roi_unit": (historical.get("summary") or {}).get("roi_unit"),
            "verdict": historical.get("verdict"),
        },
        "quality": {"available": bool(quality), "verdict": quality.get("verdict")},
        "intake": {"available": bool(intake), "verdict": intake.get("verdict")},
        "same_day_intake": {
            "available": bool(same_day or near_close_today),
            "fixtures_today": same_day.get("fixtures"),
            "valid_api_football_odds": same_day.get("odds_valid"),
            "same_day_shadow_candidates": same_day.get("selection_rows"),
            "would_add_or_added": same_day.get("would_add_or_added"),
            "near_close_pending_today": near_close_today.get("pending_today"),
            "manual_fallback": near_close_today.get("manual_fallback"),
            "commands": (near_close_today.get("commands") or [])[:10],
        },
        "future_intake": {
            "available": bool(next_days),
            "dates_scanned": next_days.get("dates_scanned"),
            "selected_total": next_days.get("selected_total"),
            "h2h_valid_not_finished_total": next_days.get("h2h_valid_not_finished_total"),
            "would_add_or_added_total": next_days.get("would_add_or_added_total"),
        },
        "near_close_window": {
            "available": bool(near_close_window),
            "due_now": near_close_window.get("due_now_count"),
            "overdue": near_close_window.get("overdue_count"),
            "status_counts": near_close_window.get("status_counts") or {},
        },
        "post_match_results": {
            "available": bool(post_match_results),
            "dates_checked": len(post_match_results.get("dates_checked") or []),
            "matched": post_match_results.get("matched"),
            "updated": post_match_results.get("updated"),
            "unmatched": post_match_results.get("unmatched"),
            "ambiguous": post_match_results.get("ambiguous"),
        },
        "free_historical_data": {
            "available": bool(football_data_import),
            "has_odds": football_data_import.get("has_odds"),
            "has_true_closing_odds": football_data_import.get("has_true_closing_odds"),
            "can_compute_roi": football_data_import.get("can_compute_roi"),
            "can_compute_clv": football_data_import.get("can_compute_clv"),
        },
        "subscription": {
            "available": bool(subscription),
            "quota_status": subscription.get("quota_status"),
            "recommendation": subscription.get("recommendation") or subscription.get("subscription_recommendation"),
            "message": subscription.get("message"),
        },
    }
    if next_days and not next_days.get("selected_total"):
        blockers.append("next-days sans selection")
    if near_close_window and (near_close_window.get("overdue_count") or 0):
        blockers.append("near-close overdue")
    if football_data_import and football_data_import.get("has_odds") and not football_data_import.get("has_true_closing_odds"):
        blockers.append("Football-Data gratuit sans closing vraie confirmee")
    if historical and not shadow:
        global_status = "historical_evidence_only"
    else:
        global_status = evidence.get("global_status") or ("collecting_evidence" if shadow or historical else "not_started")
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "global_status": global_status,
        "sections": sections,
        "blockers": sorted(set(blockers)),
        "next_actions": [
            "continuer la collecte shadow",
            "renseigner les closing odds reelles",
            "renseigner les resultats",
            "relancer evidence_gate.py",
        ],
        "lab_only": True,
        "can_influence_picks": False,
        "message": "Proof dashboard local: preuve insuffisante tant que CLV/sample live restent faibles.",
    }


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    sections = report.get("sections") or {}
    cards = "".join(
        f"<section><h2>{html.escape(str(name))}</h2><pre>{html.escape(json.dumps(data, ensure_ascii=False, indent=2))}</pre></section>"
        for name, data in sections.items()
    )
    blockers = "".join(f"<li>{html.escape(str(item))}</li>" for item in report.get("blockers") or [])
    target.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>Oracle Proof Dashboard</h1>"
        f"<p>Statut: {html.escape(str(report.get('global_status')))}</p>"
        f"<h2>Blockers</h2><ul>{blockers or '<li>Aucun</li>'}</ul>"
        + cards
        + "<p>Observation seulement, aucune mise.</p></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Oracle Proof Dashboard")
    print(f"- Statut global: {report.get('global_status')}")
    for blocker in report.get("blockers") or []:
        print(f"- Bloquant: {blocker}")
    print("- Dashboard laboratoire, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Dashboard de preuve Oracle.")
    parser.add_argument("--shadow", default="")
    parser.add_argument("--evidence", default="")
    parser.add_argument("--big5", default="")
    parser.add_argument("--historical-clv", default="")
    parser.add_argument("--quality", default="")
    parser.add_argument("--intake", default="")
    parser.add_argument("--same-day", default="")
    parser.add_argument("--near-close-today", default="")
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
        report = build_dashboard(
            args.shadow,
            args.evidence,
            args.big5,
            args.historical_clv,
            args.quality,
            args.intake,
            args.same_day,
            args.near_close_today,
            args.next_days,
            args.near_close_window,
            args.post_match_results,
            args.football_data_import,
            args.subscription_evaluator,
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
