from pathlib import Path

from decision_policy import (
    can_promote_to_candidate,
    can_promote_to_watchlist,
    can_use_in_shadow,
    can_use_in_telegram,
    classify_strategy,
    robustness_score,
)


def main():
    negative_test = {
        "validation": {"picks": 800, "roi": 4.0},
        "test": {"picks": 900, "roi": -3.0, "max_drawdown": 120},
    }
    assert robustness_score(negative_test) < 80
    assert "robuste" not in classify_strategy(negative_test)["status"]

    invalidated = {
        "train": {"picks": 2000, "roi": 2.0},
        "validation": {"picks": 700, "roi": 5.0},
        "test": {"picks": 800, "roi": -1.0},
    }
    decision = classify_strategy(invalidated)
    assert decision["decision"] == "a bloquer"
    assert "validation positive" in decision["reason"]

    weak_sample = {
        "validation": {"picks": 400, "roi": 4.0},
        "test": {"picks": 120, "roi": 12.0},
    }
    weak_decision = classify_strategy(weak_sample)
    assert weak_decision["status"] == "echantillon faible"
    assert weak_decision["score"] <= 39

    leak = {
        "validation": {"picks": 500, "roi": 10.0},
        "test": {"picks": 500, "roi": 10.0},
        "post_match_features_allowed": True,
        "leak_risk": "eleve",
    }
    leak_decision = classify_strategy(leak)
    assert leak_decision["score"] == 0
    assert leak_decision["status"] == "invalide fuite de donnees"

    no_test = {"validation": {"picks": 500, "roi": 8.0}}
    assert not can_promote_to_candidate(no_test)
    assert classify_strategy(no_test)["status"] == "fragile / test absent"

    stable_positive = {
        "train": {"picks": 5000, "roi": 2.5},
        "validation": {"picks": 1300, "roi": 1.5},
        "test": {"picks": 1500, "roi": 4.0, "max_drawdown": 70},
        "annual": {
            "2023": {"picks": 1200, "roi": 2.0},
            "2024": {"picks": 900, "roi": 4.5},
            "2025": {"picks": 600, "roi": 1.2},
        },
        "probability_metrics": {
            "brier_test": 0.20,
            "market_brier_test": 0.22,
            "log_loss_test": 0.58,
            "market_log_loss_test": 0.60,
        },
    }
    assert robustness_score(stable_positive) >= 80
    assert classify_strategy(stable_positive)["status"].startswith("candidat robuste")
    assert can_promote_to_watchlist(stable_positive)
    assert can_promote_to_candidate(stable_positive)
    assert can_use_in_shadow(stable_positive)
    assert not can_use_in_telegram(stable_positive)

    source = Path("decision_policy.py").read_text(encoding="utf-8").lower()
    assert "import telegram" not in source
    assert "bot_app" not in source
    print("test_decision_policy ok")


if __name__ == "__main__":
    main()
