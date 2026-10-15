from typing import Any, Mapping, Sequence


def deterministic_final_judge(candidate: Mapping[str, Any], findings: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    vetoes = [item for item in findings if item.get("veto")]
    blockers = list(candidate.get("blockers") or [])
    if vetoes:
        decision = "NO_BET"
        reason = "Critical veto from specialist agent."
    elif blockers:
        decision = "INSUFFICIENT_DATA"
        reason = "Deterministic filters found blockers."
    else:
        decision = "WATCH"
        reason = "Candidate passed deterministic demo filters, but no live LLM review or historical proof is attached."
    return {
        "schema_version": "1.0",
        "decision": decision,
        "fixture_id": candidate.get("fixture_id"),
        "market_key": candidate.get("market_key"),
        "selection_key": candidate.get("selection_key"),
        "decimal_odds": candidate.get("decimal_odds"),
        "odds_observed_at": candidate.get("odds_observed_at", ""),
        "p_model": candidate.get("p_model"),
        "p_market_fair": candidate.get("p_market_fair"),
        "edge_probability_points": candidate.get("edge_probability_points"),
        "expected_value_per_unit": candidate.get("expected_value_per_unit"),
        "uncertainty_low": candidate.get("uncertainty_low"),
        "uncertainty_high": candidate.get("uncertainty_high"),
        "data_quality_status": candidate.get("data_quality_status"),
        "confidence_tier": "not_validated",
        "vetoes": [item.get("veto_reason") or item.get("agent_id") for item in vetoes],
        "key_supporting_factors": ["Python-calculated EV and edge were positive."] if not blockers else [],
        "key_counterarguments": ["Synthetic demo is not evidence of profitability."],
        "missing_information": ["production provider replay", "walk-forward validation", "real specialist review"],
        "material_change_triggers": ["odds stale", "lineup conflict", "provider result conflict"],
        "stake_recommendation": {
            "mode": "paper",
            "bankroll_fraction": 0.0,
            "method": "paper_only_no_real_stake",
        },
        "final_reason": reason,
        "lab_only": True,
        "can_influence_picks": False,
    }

