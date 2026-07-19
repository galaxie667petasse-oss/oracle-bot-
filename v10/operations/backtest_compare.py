from __future__ import annotations

from collections import Counter
from typing import Any

from v10.odds import proportional_no_vig
from v10.statistics.metrics import multiclass_brier, multiclass_log_loss
from v10.statistics.training import build_dataset_from_csv, predict_with_models


def _historical_frequency(labels: list[str]) -> dict[str, float]:
    counts = Counter(labels)
    total = sum(counts.values()) or 1
    return {key: counts.get(key, 0) / total for key in ("home", "draw", "away")}


def _market_probability(row) -> dict[str, float] | None:
    match = row.match
    if match.odds_home and match.odds_draw and match.odds_away:
        try:
            return proportional_no_vig({"home": match.odds_home, "draw": match.odds_draw, "away": match.odds_away})
        except Exception:
            return None
    return None


def compare_backtest_from_csv(
    path: str = "data/MATCHES.csv",
    start: str | None = None,
    end: str | None = None,
    limit: int | None = 5000,
    train_size: int = 240,
    test_size: int = 80,
    step_size: int = 80,
    include_market_baseline: bool = True,
) -> dict[str, Any]:
    rows, dataset_report = build_dataset_from_csv(path, start=start, end=end, limit=limit)
    ordered = sorted(rows, key=lambda row: row.match.event_time)
    model_predictions: dict[str, list[dict[str, float]]] = {
        "uniform_1x2": [],
        "historical_frequency": [],
        "market_no_vig": [],
        "elo": [],
        "poisson": [],
        "dixon_coles": [],
        "ensemble": [],
        "ensemble_with_market_prior": [],
    }
    labels: list[str] = []
    market_labels: list[str] = []
    windows = []
    start_idx = 0
    while start_idx + train_size + test_size <= len(ordered):
        train = ordered[start_idx : start_idx + train_size]
        test = ordered[start_idx + train_size : start_idx + train_size + test_size]
        train_labels = [row.match.result_key for row in train]
        hist = _historical_frequency(train_labels)
        for row in test:
            pred = predict_with_models([item.match for item in train], row.match)
            label = row.match.result_key
            labels.append(label)
            model_predictions["uniform_1x2"].append({"home": 1 / 3, "draw": 1 / 3, "away": 1 / 3})
            model_predictions["historical_frequency"].append(hist)
            model_predictions["elo"].append(pred["models"]["elo_multiclass_v1"]["probabilities_1x2"])
            model_predictions["poisson"].append(pred["models"]["poisson_independent_v1"]["probabilities_1x2"])
            model_predictions["dixon_coles"].append(pred["models"]["dixon_coles_v1"]["probabilities_1x2"])
            ensemble = pred["ensemble"]
            model_predictions["ensemble"].append(ensemble)
            market = _market_probability(row)
            if market and include_market_baseline:
                model_predictions["market_no_vig"].append(market)
                market_labels.append(label)
                mixed = {key: 0.7 * ensemble[key] + 0.3 * market[key] for key in ("home", "draw", "away")}
                total = sum(mixed.values())
                model_predictions["ensemble_with_market_prior"].append({key: value / total for key, value in mixed.items()})
            else:
                model_predictions["ensemble_with_market_prior"].append(ensemble)
        windows.append(
            {
                "train_start": train[0].match.event_time.date().isoformat(),
                "train_end": train[-1].match.event_time.date().isoformat(),
                "test_start": test[0].match.event_time.date().isoformat(),
                "test_end": test[-1].match.event_time.date().isoformat(),
                "test_count": len(test),
            }
        )
        start_idx += step_size

    metrics: dict[str, Any] = {}
    for key, probabilities in model_predictions.items():
        metric_labels = market_labels if key == "market_no_vig" else labels
        if key == "market_no_vig":
            probabilities = probabilities[: len(metric_labels)]
        if not probabilities or not metric_labels:
            metrics[key] = {"sample_count": 0, "log_loss": None, "brier": None}
        else:
            metrics[key] = {
                "sample_count": len(probabilities),
                "log_loss": multiclass_log_loss(probabilities, metric_labels),
                "brier": multiclass_brier(probabilities, metric_labels),
            }
    return {
        "mode": "walk_forward_compare",
        "dataset": dataset_report,
        "windows": windows,
        "prediction_count": len(labels),
        "markets": ["1x2"],
        "binary_markets_requested": ["ou25", "btts"],
        "binary_market_note": "Phase 5 compare 1X2 on a shared cohort; OU/BTTS need historical odds columns before market baseline metrics are comparable.",
        "metrics": metrics,
        "include_market_baseline": include_market_baseline,
        "statistical_model_validated_for_signals": False,
        "no_profit_claim": True,
        "paper_only": True,
        "lab_only": True,
        "can_influence_picks": False,
    }
