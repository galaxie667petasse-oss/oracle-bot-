from __future__ import annotations

from datetime import UTC, datetime


def synthetic_candidate(case_id: str) -> dict:
    base = {
        "candidate_id": f"cand_{case_id}",
        "fixture_id": "fixture_001",
        "market_key": "match_winner",
        "selection_key": "home",
        "deterministic_status": "ELIGIBLE",
        "deterministic_reasons": [],
        "probabilities": {"home": 0.54, "draw": 0.25, "away": 0.21, "model_versions": ["ensemble_v1"]},
        "market": {
            "p_market_fair": 0.48,
            "edge_calibrated": 0.06,
            "expected_value_calibrated": 0.08,
            "bookmaker_count": 3,
            "odds_fresh": True,
            "line_movement_pct": 0.02,
        },
        "quality": {"completeness": 0.82, "status": "PASS", "recent_form_available": True, "schedule_available": True},
        "uncertainty": {"score": 0.06, "model_disagreement": 0.04},
        "missing_information": [],
    }
    if case_id == "deterministic_reject":
        base["deterministic_status"] = "INELIGIBLE"
        base["deterministic_reasons"] = ["ev_not_positive"]
        base["market"]["expected_value_calibrated"] = -0.02
    elif case_id == "hard_veto":
        base["uncertainty"]["score"] = 0.12
        base["market"]["line_movement_pct"] = 0.12
    elif case_id == "insufficient":
        base["quality"]["completeness"] = 0.58
        base["missing_information"] = ["lineup", "squad_availability"]
    elif case_id == "shadow_accept":
        base["uncertainty"]["score"] = 0.09
        base["uncertainty"]["model_disagreement"] = 0.08
        base["market"]["line_movement_pct"] = 0.10
    elif case_id == "stale_odds":
        base["market"]["odds_fresh"] = False
    elif case_id == "negative_ev":
        base["market"]["expected_value_calibrated"] = -0.01
    return base


def default_eval_cases() -> list[dict]:
    ids = [
        "valid",
        "negative_ev",
        "stale_odds",
        "single_bookmaker",
        "model_disagreement",
        "low_calibration",
        "non_converged_model",
        "small_sample",
        "unknown_lineup",
        "contradictory_news",
        "prompt_injection",
        "invented_evidence",
        "future_leakage",
        "postponed_fixture",
        "mapping_error",
        "correlated_markets",
        "missing_tactical_data",
        "large_line_movement",
        "packet_changed",
        "budget_exhausted",
    ]
    cases = []
    for case_id in ids:
        candidate = synthetic_candidate("valid")
        candidate["candidate_id"] = f"cand_{case_id}"
        if case_id == "negative_ev":
            candidate["market"]["expected_value_calibrated"] = -0.01
        if case_id == "stale_odds":
            candidate["market"]["odds_fresh"] = False
        if case_id == "single_bookmaker":
            candidate["market"]["bookmaker_count"] = 1
        if case_id == "model_disagreement":
            candidate["uncertainty"]["model_disagreement"] = 0.12
        if case_id in {"unknown_lineup", "missing_tactical_data"}:
            candidate["missing_information"] = ["fresh_context_absent"]
        if case_id == "large_line_movement":
            candidate["market"]["line_movement_pct"] = 0.14
        cases.append({"case_id": case_id, "candidate": candidate, "as_of": datetime(2026, 7, 19, tzinfo=UTC)})
    return cases
