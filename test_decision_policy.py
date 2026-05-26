from pathlib import Path

from decision_policy import (
    can_pass_calibration_gate,
    can_pass_clv_gate,
    can_pass_multiple_testing_gate,
    can_pass_statistical_gate,
    can_promote_to_candidate,
    can_promote_to_watchlist,
    can_use_in_shadow,
    can_use_in_telegram,
    classify_strategy,
    explain_rejection,
    robustness_score,
)


def robust_metrics():
    return {
        "train": {"picks": 5000, "roi": 2.5},
        "validation": {"picks": 1300, "roi": 1.5},
        "test": {"picks": 3000, "roi": 4.0, "max_drawdown": 70},
        "annual": {
            "2023": {"picks": 1200, "roi": 2.0},
            "2024": {"picks": 1600, "roi": 4.5},
            "2025": {"picks": 1400, "roi": 1.2},
        },
        "clv": {"clv_mean": 0.012, "clv_positive_rate": 58.0},
        "calibration": {
            "brier": 0.20,
            "market_brier": 0.22,
            "log_loss": 0.58,
            "market_log_loss": 0.60,
            "ece": 0.02,
            "mce": 0.08,
        },
        "statistics": {
            "roi_ci_low": 1.0,
            "bootstrap_roi_p05": 0.8,
            "p_value_adjusted": 0.01,
        },
        "multiple_testing_passed": True,
    }


def main():
    negative_test = {
        "validation": {"picks": 800, "roi": 4.0},
        "test": {"picks": 900, "roi": -3.0, "max_drawdown": 120},
        "clv": {"clv_mean": -0.01, "clv_positive_rate": 40.0},
    }
    assert robustness_score(negative_test) < 40
    assert classify_strategy(negative_test)["status"] == "rejected"

    invalidated = {
        "train": {"picks": 2000, "roi": 2.0},
        "validation": {"picks": 700, "roi": 5.0},
        "test": {"picks": 800, "roi": -1.0},
        "clv": {"clv_mean": 0.01, "clv_positive_rate": 55.0},
    }
    decision = classify_strategy(invalidated)
    assert decision["decision"] == "rejected"
    assert "validation positive" in decision["reason"]

    weak_sample = {
        "validation": {"picks": 400, "roi": 4.0},
        "test": {"picks": 120, "roi": 12.0},
        "clv": {"clv_mean": 0.02, "clv_positive_rate": 60.0},
    }
    weak_decision = classify_strategy(weak_sample)
    assert weak_decision["status"] == "observation"
    assert weak_decision["score"] <= 29

    leak = {
        "validation": {"picks": 500, "roi": 10.0},
        "test": {"picks": 500, "roi": 10.0},
        "post_match_features_allowed": True,
        "leak_risk": "eleve",
    }
    leak_decision = classify_strategy(leak)
    assert leak_decision["score"] == 0
    assert leak_decision["status"] == "rejected"

    roi_positive_clv_negative = robust_metrics()
    roi_positive_clv_negative["clv"] = {"clv_mean": -0.01, "clv_positive_rate": 35.0}
    assert not can_pass_clv_gate(roi_positive_clv_negative)
    assert classify_strategy(roi_positive_clv_negative)["status"] in {"rejected", "watchlist"}
    assert not can_promote_to_candidate(roi_positive_clv_negative)

    roi_negative_clv_positive = robust_metrics()
    roi_negative_clv_positive["test"]["roi"] = -0.2
    roi_negative_clv_positive["validation"]["roi"] = -0.1
    decision = classify_strategy(roi_negative_clv_positive)
    assert decision["status"] in {"observation", "rejected"}
    assert not can_use_in_shadow(roi_negative_clv_positive)

    bootstrap_bad = robust_metrics()
    bootstrap_bad["statistics"]["bootstrap_roi_p05"] = -0.1
    assert not can_pass_statistical_gate(bootstrap_bad)
    assert classify_strategy(bootstrap_bad)["status"] in {"rejected", "watchlist"}
    assert not can_promote_to_candidate(bootstrap_bad)

    ece_bad = robust_metrics()
    ece_bad["calibration"]["ece"] = 0.12
    assert not can_pass_calibration_gate(ece_bad)
    assert classify_strategy(ece_bad)["status"] in {"rejected", "watchlist"}

    multiple_bad = robust_metrics()
    multiple_bad["multiple_testing_passed"] = False
    multiple_bad["statistics"]["p_value_adjusted"] = 0.20
    assert not can_pass_multiple_testing_gate(multiple_bad)
    assert classify_strategy(multiple_bad)["status"] in {"rejected", "watchlist"}

    no_test = {"validation": {"picks": 500, "roi": 8.0}}
    assert not can_promote_to_candidate(no_test)
    assert classify_strategy(no_test)["status"] == "observation"

    stable_positive = robust_metrics()
    assert robustness_score(stable_positive) >= 80
    assert classify_strategy(stable_positive)["status"] == "candidate"
    assert can_promote_to_watchlist(stable_positive)
    assert can_promote_to_candidate(stable_positive)
    assert can_use_in_shadow(stable_positive)
    assert not can_use_in_telegram(stable_positive)

    production_missing_gate = robust_metrics()
    production_missing_gate["promotion_level"] = "production_allowed"
    production_missing_gate["human_review_passed"] = True
    production_missing_gate["statistics"]["p_value_adjusted"] = 0.20
    production_missing_gate["multiple_testing_passed"] = False
    assert classify_strategy(production_missing_gate)["status"] != "production_allowed"

    production_ready = robust_metrics()
    production_ready["promotion_level"] = "production_allowed"
    production_ready["human_review_passed"] = True
    assert classify_strategy(production_ready)["status"] == "production_allowed"
    assert "CLV" in " ".join(explain_rejection({"test": {"picks": 1000, "roi": 2.0}}))

    source = Path("decision_policy.py").read_text(encoding="utf-8").lower()
    assert "import telegram" not in source
    assert "bot_app" not in source
    print("test_decision_policy ok")


if __name__ == "__main__":
    main()
