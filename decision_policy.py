from typing import Any, Dict, Optional


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
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def _drawdown(metrics: Dict[str, Any]) -> Optional[float]:
    return _num(_split(metrics, "test").get("max_drawdown") or _split(metrics, "test").get("drawdown"))


def _uses_post_match_leak(metrics: Dict[str, Any]) -> bool:
    leak = str(metrics.get("leak_risk") or "").lower()
    return bool(metrics.get("post_match_features_allowed")) and leak in {"eleve", "high", "post_match"}


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
    if not isinstance(annual, dict):
        return False
    stat = annual.get("2025") or {}
    roi = _num(stat.get("roi")) if isinstance(stat, dict) else None
    return roi is not None and roi < 0


def _governance_note(metrics: Dict[str, Any]) -> str:
    return str(metrics.get("governance_note") or metrics.get("notes") or "").lower()


def _has_stability_or_probability_context(metrics: Dict[str, Any]) -> bool:
    annual = metrics.get("annual") or metrics.get("annual_metrics")
    probability = metrics.get("probability_metrics") or metrics.get("model_metrics")
    has_annual = isinstance(annual, dict) and bool(annual)
    has_probability = isinstance(probability, dict) and bool(probability)
    return has_annual or has_probability


def robustness_score(metrics: Dict[str, Any]) -> int:
    """Score prudent sur 100, base sur train/validation/test et anti-fuite."""
    if _uses_post_match_leak(metrics):
        return 0

    score = 10
    train_roi = _roi(metrics, "train")
    validation_roi = _roi(metrics, "validation")
    test_roi = _roi(metrics, "test")
    test_n = _picks(metrics, "test")

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
        score += 18

    positive_years = _annual_positive_count(metrics)
    score += min(12, positive_years * 4)

    if test_n >= 1000:
        score += 12
    elif test_n >= 300:
        score += 5
    else:
        score -= 16

    drawdown = _drawdown(metrics)
    if drawdown is not None and test_n > 0:
        drawdown_per_pick = drawdown / max(1, test_n)
        if drawdown_per_pick <= 0.08:
            score += 6
        elif drawdown_per_pick >= 0.25:
            score -= 10

    if _negative_2025(metrics):
        score -= 14

    if bool(metrics.get("edge_positive_validation_only")):
        score -= 28

    note = _governance_note(metrics)
    if "degradation" in note:
        score -= 25
    if any(token in note for token in ("observation seulement", "non confirme", "fragile", "invalide")):
        score -= 18

    score = max(0, min(100, score))

    if test_roi is not None and test_roi <= 0:
        score = min(score, 59)
    if test_roi is not None and 0 < test_roi < 1.0:
        score = min(score, 59)
    if validation_roi is not None and validation_roi < 1.0:
        score = min(score, 79)
    if not _has_stability_or_probability_context(metrics):
        score = min(score, 79)
    if test_roi is None or test_n <= 0:
        score = min(score, 59)
    if test_n and test_n < 300:
        score = min(score, 39)
    return int(round(score))


def classify_strategy(metrics: Dict[str, Any]) -> Dict[str, Any]:
    if _uses_post_match_leak(metrics):
        return {
            "score": 0,
            "status": "invalide fuite de donnees",
            "decision": "a bloquer",
            "reason": "features post-match utilisees sans transformation rolling pre-match",
        }

    score = robustness_score(metrics)
    test_roi = _roi(metrics, "test")
    validation_roi = _roi(metrics, "validation")
    test_n = _picks(metrics, "test")

    if test_roi is None or test_n <= 0:
        return {
            "score": score,
            "status": "fragile / test absent",
            "decision": "observation seulement",
            "reason": "test 2024+ absent ou non lisible",
        }
    if test_n < 300:
        return {
            "score": score,
            "status": "echantillon faible",
            "decision": "observation seulement",
            "reason": "sample test inferieur a 300",
        }
    if validation_roi is not None and validation_roi > 0 and test_roi < 0:
        return {
            "score": score,
            "status": "invalide ou a eviter",
            "decision": "a bloquer",
            "reason": "validation positive mais test 2024+ negatif",
        }
    if test_roi <= 0:
        return {
            "score": score,
            "status": "invalide ou a eviter" if score < 20 else "faible / non confirme",
            "decision": "a bloquer" if score < 20 else "observation seulement",
            "reason": "ROI test 2024+ non positif",
        }
    if score >= 80:
        return {
            "score": score,
            "status": "candidat robuste, mais pas pick automatique",
            "decision": "candidate",
            "reason": "test positif avec volume et controles de robustesse satisfaisants",
        }
    if score >= 60:
        return {
            "score": score,
            "status": "observation forte a confirmer",
            "decision": "observation seulement",
            "reason": "signal positif mais pas encore assez gouverne pour activation",
        }
    if score >= 40:
        return {
            "score": score,
            "status": "fragile / surveillance",
            "decision": "watchlist",
            "reason": "signal fragile ou stabilite insuffisante",
        }
    if score >= 20:
        return {
            "score": score,
            "status": "faible / non confirme",
            "decision": "observation seulement",
            "reason": "signal insuffisant pour promotion",
        }
    return {
        "score": score,
        "status": "invalide ou a eviter",
        "decision": "a bloquer",
        "reason": "score de robustesse tres faible",
    }


def can_promote_to_watchlist(metrics: Dict[str, Any]) -> bool:
    decision = classify_strategy(metrics)
    return decision["score"] >= 40 and decision["status"] not in {"invalide fuite de donnees", "fragile / test absent", "echantillon faible"}


def can_promote_to_candidate(metrics: Dict[str, Any]) -> bool:
    decision = classify_strategy(metrics)
    return decision["score"] >= 80 and decision["status"].startswith("candidat robuste") and (_roi(metrics, "validation") or 0.0) >= 0 and _picks(metrics, "test") >= 300


def can_use_in_shadow(metrics: Dict[str, Any]) -> bool:
    decision = classify_strategy(metrics)
    return decision["score"] >= 60 and decision["decision"] in {"candidate", "observation seulement"} and not _uses_post_match_leak(metrics)


def can_use_in_telegram(metrics: Dict[str, Any]) -> bool:
    decision = classify_strategy(metrics)
    return bool(
        metrics.get("promotion_level") == "production_allowed"
        and decision["score"] >= 80
        and (_roi(metrics, "test") or 0.0) > 0
        and _picks(metrics, "test") >= 1000
        and not _uses_post_match_leak(metrics)
    )
