from typing import Any, Dict, List, Optional


LEVELS = [
    "rejected",
    "watchlist",
    "observation",
    "candidate",
    "active_shadow_only",
    "active_decision_support",
    "production_allowed",
]


def _num(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except Exception:
        return None
    return number


def _split(metrics: Dict[str, Any], name: str) -> Dict[str, Any]:
    value = metrics.get(name) or {}
    return value if isinstance(value, dict) else {}


def _roi(metrics: Dict[str, Any], split: str) -> Optional[float]:
    return _num(_split(metrics, split).get("roi"))


def _picks(metrics: Dict[str, Any], split: str = "test") -> int:
    value = _split(metrics, split).get("picks")
    if value is None:
        value = _split(metrics, split).get("n")
    if value is None:
        value = metrics.get("sample_test") if split == "test" else None
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def _drawdown(metrics: Dict[str, Any]) -> Optional[float]:
    return _num(_split(metrics, "test").get("max_drawdown") or _split(metrics, "test").get("drawdown") or metrics.get("drawdown"))


def _nested(metrics: Dict[str, Any], *names: str) -> Dict[str, Any]:
    for name in names:
        value = metrics.get(name)
        if isinstance(value, dict):
            return value
    return {}


def _metric(metrics: Dict[str, Any], key: str, *containers: str) -> Optional[float]:
    value = metrics.get(key)
    if value is not None:
        return _num(value)
    for container in containers:
        data = metrics.get(container)
        if isinstance(data, dict) and data.get(key) is not None:
            return _num(data.get(key))
    return None


def _uses_post_match_leak(metrics: Dict[str, Any]) -> bool:
    leak = str(metrics.get("leak_risk") or "").lower()
    explicit = bool(metrics.get("data_leakage") or metrics.get("leak_detected"))
    return explicit or (bool(metrics.get("post_match_features_allowed")) and leak in {"eleve", "high", "post_match"})


def _probabilistic_better(metrics: Dict[str, Any]) -> bool:
    model = metrics.get("probability_metrics") or metrics.get("model_metrics") or {}
    if not isinstance(model, dict):
        return False
    brier = _num(model.get("brier_test") or model.get("brier"))
    market_brier = _num(model.get("market_brier_test") or model.get("market_brier"))
    log_loss = _num(model.get("log_loss_test") or model.get("log_loss"))
    market_log_loss = _num(model.get("market_log_loss_test") or model.get("market_log_loss"))
    brier_ok = brier is not None and market_brier is not None and brier < market_brier
    log_ok = log_loss is not None and market_log_loss is not None and log_loss <= market_log_loss
    return bool(brier_ok and log_ok)


def _annual_positive_count(metrics: Dict[str, Any]) -> int:
    annual = metrics.get("annual") or metrics.get("annual_metrics") or {}
    if not isinstance(annual, dict):
        return 0
    return sum(1 for stat in annual.values() if isinstance(stat, dict) and (_num(stat.get("roi")) or 0.0) > 0 and _picks({"test": stat}) >= 100)


def _negative_2025(metrics: Dict[str, Any]) -> bool:
    annual = metrics.get("annual") or metrics.get("annual_metrics") or {}
    if isinstance(annual, dict):
        stat = annual.get("2025") or {}
        roi = _num(stat.get("roi")) if isinstance(stat, dict) else None
        if roi is not None and roi < 0:
            return True
    return bool(metrics.get("degradation_2025") or metrics.get("recent_2025_degradation"))


def _governance_note(metrics: Dict[str, Any]) -> str:
    return str(metrics.get("governance_note") or metrics.get("notes") or "").lower()


def _has_stability_or_probability_context(metrics: Dict[str, Any]) -> bool:
    annual = metrics.get("annual") or metrics.get("annual_metrics")
    probability = metrics.get("probability_metrics") or metrics.get("model_metrics") or metrics.get("calibration")
    has_annual = isinstance(annual, dict) and bool(annual)
    has_probability = isinstance(probability, dict) and bool(probability)
    return has_annual or has_probability


def can_pass_clv_gate(metrics: Dict[str, Any]) -> bool:
    clv = _nested(metrics, "clv", "clv_metrics")
    clv_mean = _metric(metrics, "clv_mean", "clv", "clv_metrics")
    if clv_mean is None:
        clv_mean = _metric(metrics, "mean", "clv", "clv_metrics")
    positive_rate = _metric(metrics, "clv_positive_rate", "clv", "clv_metrics")
    status = str(clv.get("status") or metrics.get("clv_status") or "").lower()
    if "indisponible" in status or "unavailable" in status:
        return False
    if clv_mean is None:
        return False
    if clv_mean <= 0:
        return False
    if positive_rate is not None and positive_rate < 50.0:
        return False
    return True


def can_pass_calibration_gate(metrics: Dict[str, Any]) -> bool:
    calibration = _nested(metrics, "calibration", "calibration_metrics", "probability_metrics", "model_metrics")
    if not calibration:
        return False
    brier = _metric(metrics, "brier", "calibration", "calibration_metrics", "probability_metrics", "model_metrics")
    market_brier = _metric(metrics, "market_brier", "calibration", "calibration_metrics", "probability_metrics", "model_metrics")
    if market_brier is None:
        market_brier = _metric(metrics, "market_brier_test", "probability_metrics", "model_metrics")
    log_loss = _metric(metrics, "log_loss", "calibration", "calibration_metrics", "probability_metrics", "model_metrics")
    market_log_loss = _metric(metrics, "market_log_loss", "calibration", "calibration_metrics", "probability_metrics", "model_metrics")
    if market_log_loss is None:
        market_log_loss = _metric(metrics, "market_log_loss_test", "probability_metrics", "model_metrics")
    if brier is not None and market_brier is not None and brier > market_brier:
        return False
    if log_loss is not None and market_log_loss is not None and log_loss > market_log_loss:
        return False
    ece = _metric(metrics, "ece", "calibration", "calibration_metrics", "probability_metrics", "model_metrics")
    mce = _metric(metrics, "mce", "calibration", "calibration_metrics", "probability_metrics", "model_metrics")
    if ece is None:
        return False
    if ece > 0.05:
        return False
    if mce is not None and mce > 0.15:
        return False
    return True


def can_pass_statistical_gate(metrics: Dict[str, Any]) -> bool:
    test_roi = _roi(metrics, "test")
    if test_roi is None:
        test_roi = _metric(metrics, "roi_test")
    test_n = _picks(metrics, "test")
    if test_n <= 0:
        sample_test = _metric(metrics, "sample_test")
        test_n = int(sample_test or 0)
    if test_roi is None or test_roi <= 0:
        return False
    if test_n < 1000:
        return False
    ci_low = _metric(metrics, "roi_ci_low", "statistics", "statistical_validation")
    if ci_low is None:
        ci_low = _metric(metrics, "ci_low", "statistics", "statistical_validation")
    if ci_low is not None and ci_low <= 0:
        return False
    bootstrap_p05 = _metric(metrics, "bootstrap_roi_p05", "statistics", "statistical_validation")
    if bootstrap_p05 is None:
        bootstrap = _nested(metrics, "bootstrap_roi", "bootstrap")
        bootstrap_p05 = _num(bootstrap.get("p05"))
    if bootstrap_p05 is None or bootstrap_p05 <= 0:
        return False
    if _negative_2025(metrics):
        return False
    if bool(metrics.get("threshold_chosen_on_test") or metrics.get("test_threshold_selected")):
        return False
    return True


def can_pass_multiple_testing_gate(metrics: Dict[str, Any]) -> bool:
    explicit = metrics.get("multiple_testing_passed")
    if explicit is not None:
        return bool(explicit)
    p_adjusted = _metric(metrics, "p_value_adjusted", "statistics", "statistical_validation")
    if p_adjusted is None:
        return False
    return p_adjusted < 0.05


def explain_rejection(metrics: Dict[str, Any]) -> List[str]:
    reasons: List[str] = []
    test_roi = _roi(metrics, "test")
    if test_roi is None:
        test_roi = _metric(metrics, "roi_test")
    validation_roi = _roi(metrics, "validation")
    test_n = _picks(metrics, "test")
    if test_n <= 0:
        sample_test = _metric(metrics, "sample_test")
        test_n = int(sample_test or 0)
    if _uses_post_match_leak(metrics):
        reasons.append("fuite de donnees ou features post-match")
    if test_roi is None:
        reasons.append("test 2024+ absent ou non lisible")
    elif test_roi <= 0:
        reasons.append("ROI test 2024+ non positif")
    if validation_roi is not None and test_roi is not None and validation_roi > 0 and test_roi < 0:
        reasons.append("validation positive mais test 2024+ negatif")
    if test_n and test_n < 300:
        reasons.append("sample test inferieur a 300")
    elif test_n and test_n < 1000:
        reasons.append("sample test inferieur a 1000")
    if not can_pass_clv_gate(metrics):
        clv_mean = _metric(metrics, "clv_mean", "clv", "clv_metrics")
        reasons.append("CLV absente ou non positive" if clv_mean is None else "CLV negative ou trop faible")
    if not can_pass_calibration_gate(metrics):
        reasons.append("calibration absente ou insuffisante")
    if not can_pass_statistical_gate(metrics):
        reasons.append("preuve statistique insuffisante")
    if not can_pass_multiple_testing_gate(metrics):
        reasons.append("correction de multiple testing non validee")
    if _negative_2025(metrics):
        reasons.append("degradation recente 2025")
    if bool(metrics.get("threshold_chosen_on_test") or metrics.get("test_threshold_selected")):
        reasons.append("seuil choisi sur test")
    if bool(metrics.get("edge_positive_validation_only")):
        reasons.append("edge positif seulement en validation")
    note = _governance_note(metrics)
    if "degradation" in note and "degradation recente 2025" not in reasons:
        reasons.append("degradation mentionnee dans la gouvernance")
    return list(dict.fromkeys(reasons))


def robustness_score(metrics: Dict[str, Any]) -> int:
    """Score prudent sur 100, base sur train/validation/test et preuves V7."""
    if _uses_post_match_leak(metrics):
        return 0

    score = 10
    train_roi = _roi(metrics, "train")
    validation_roi = _roi(metrics, "validation")
    test_roi = _roi(metrics, "test")
    if test_roi is None:
        test_roi = _metric(metrics, "roi_test")
    test_n = _picks(metrics, "test")
    if test_n <= 0:
        sample_test = _metric(metrics, "sample_test")
        test_n = int(sample_test or 0)

    if test_roi is None or test_n <= 0:
        score -= 10
    elif test_roi > 0:
        score += 32
        if test_roi >= 3:
            score += 10
    else:
        score -= 35

    if validation_roi is not None:
        score += 16 if validation_roi >= 0 else -12
    if train_roi is not None:
        score += 8 if train_roi > 0 else -4

    if validation_roi is not None and test_roi is not None and validation_roi > 0 and test_roi < 0:
        score -= 35
    if train_roi is not None and validation_roi is not None and test_roi is not None and train_roi > 0 and validation_roi < 0 and test_roi < 0:
        score -= 22

    if _probabilistic_better(metrics):
        score += 10
    if can_pass_clv_gate(metrics):
        score += 12
    if can_pass_calibration_gate(metrics):
        score += 10
    if can_pass_statistical_gate(metrics):
        score += 12
    if can_pass_multiple_testing_gate(metrics):
        score += 8

    positive_years = _annual_positive_count(metrics)
    score += min(8, positive_years * 3)

    if test_n >= 3000:
        score += 12
    elif test_n >= 1000:
        score += 8
    elif test_n >= 300:
        score += 3
    else:
        score -= 16

    drawdown = _drawdown(metrics)
    if drawdown is not None and test_n > 0:
        drawdown_per_pick = drawdown / max(1, test_n)
        if drawdown_per_pick <= 0.08:
            score += 5
        elif drawdown_per_pick >= 0.25:
            score -= 10

    if _negative_2025(metrics):
        score -= 18
    if bool(metrics.get("edge_positive_validation_only")):
        score -= 28
    if bool(metrics.get("threshold_chosen_on_test") or metrics.get("test_threshold_selected")):
        score -= 25

    note = _governance_note(metrics)
    if "degradation" in note:
        score -= 20
    if any(token in note for token in ("observation seulement", "non confirme", "fragile", "invalide")):
        score -= 12

    score = max(0, min(100, score))

    if test_roi is not None and test_roi <= 0:
        score = min(score, 39 if can_pass_clv_gate(metrics) else 19)
    if test_roi is not None and 0 < test_roi < 1.0:
        score = min(score, 59)
    if validation_roi is not None and validation_roi < 1.0:
        score = min(score, 79)
    if not _has_stability_or_probability_context(metrics):
        score = min(score, 79)
    if test_roi is None or test_n <= 0:
        score = min(score, 39)
    if test_n and test_n < 300:
        score = min(score, 29)
    elif test_n and test_n < 1000:
        score = min(score, 59)
    if not can_pass_clv_gate(metrics):
        score = min(score, 59 if _metric(metrics, "clv_mean", "clv", "clv_metrics") is None else 39)
    if not can_pass_calibration_gate(metrics):
        score = min(score, 59)
    if not can_pass_statistical_gate(metrics):
        score = min(score, 59)
    if not can_pass_multiple_testing_gate(metrics):
        score = min(score, 59)
    return int(round(score))


def _all_candidate_gates(metrics: Dict[str, Any]) -> bool:
    return (
        can_pass_clv_gate(metrics)
        and can_pass_calibration_gate(metrics)
        and can_pass_statistical_gate(metrics)
        and can_pass_multiple_testing_gate(metrics)
        and not _uses_post_match_leak(metrics)
    )


def classify_strategy(metrics: Dict[str, Any]) -> Dict[str, Any]:
    score = robustness_score(metrics)
    reasons = explain_rejection(metrics)
    test_roi = _roi(metrics, "test")
    if test_roi is None:
        test_roi = _metric(metrics, "roi_test")
    validation_roi = _roi(metrics, "validation")
    test_n = _picks(metrics, "test")
    if test_n <= 0:
        sample_test = _metric(metrics, "sample_test")
        test_n = int(sample_test or 0)

    if _uses_post_match_leak(metrics):
        status = "rejected"
        reason = "fuite de donnees ou features post-match"
    elif test_roi is None or test_n <= 0:
        status = "observation"
        reason = "test 2024+ absent ou non lisible"
    elif test_n < 300:
        status = "observation"
        reason = "sample test inferieur a 300"
    elif validation_roi is not None and validation_roi > 0 and test_roi < 0:
        status = "rejected"
        reason = "validation positive mais test 2024+ negatif"
    elif test_roi <= 0:
        status = "observation" if can_pass_clv_gate(metrics) else "rejected"
        reason = "ROI test 2024+ non positif"
    elif not _all_candidate_gates(metrics):
        severe_tokens = (
            "CLV negative",
            "calibration absente",
            "preuve statistique insuffisante",
            "correction de multiple testing non validee",
            "degradation",
            "seuil choisi sur test",
        )
        severe = any(any(token in reason_item for token in severe_tokens) for reason_item in reasons)
        status = "rejected" if severe and score < 40 else ("watchlist" if score >= 40 else "observation")
        reason = reasons[0] if reasons else "gates V7 incomplets"
    else:
        requested = str(metrics.get("promotion_level") or metrics.get("requested_status") or "").strip()
        human_review = bool(metrics.get("human_review_passed") or metrics.get("governance_review_passed"))
        if requested == "production_allowed" and human_review:
            status = "production_allowed"
        elif requested == "active_decision_support" and human_review:
            status = "active_decision_support"
        elif requested == "active_shadow_only":
            status = "active_shadow_only"
        else:
            status = "candidate"
        reason = "tous les gates V7 passent; validation humaine encore requise"

    return {
        "score": score,
        "status": status,
        "governance_status": status,
        "decision": status,
        "reason": reason,
        "rejection_reasons": reasons,
    }


def can_promote_to_watchlist(metrics: Dict[str, Any]) -> bool:
    decision = classify_strategy(metrics)
    return decision["score"] >= 40 and decision["status"] in {"watchlist", "observation", "candidate", "active_shadow_only", "active_decision_support", "production_allowed"}


def can_promote_to_candidate(metrics: Dict[str, Any]) -> bool:
    decision = classify_strategy(metrics)
    return decision["status"] in {"candidate", "active_shadow_only", "active_decision_support", "production_allowed"} and decision["score"] >= 80 and _all_candidate_gates(metrics)


def can_use_in_shadow(metrics: Dict[str, Any]) -> bool:
    decision = classify_strategy(metrics)
    return decision["status"] in {"candidate", "active_shadow_only", "active_decision_support", "production_allowed"} and not _uses_post_match_leak(metrics)


def can_use_in_telegram(metrics: Dict[str, Any]) -> bool:
    decision = classify_strategy(metrics)
    return bool(
        metrics.get("telegram_decision_support_allowed")
        and decision["status"] in {"active_decision_support", "production_allowed"}
        and _all_candidate_gates(metrics)
        and not metrics.get("automatic_bet")
    )
