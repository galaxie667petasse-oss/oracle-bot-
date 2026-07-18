from __future__ import annotations

from dataclasses import dataclass

from .dataset import DatasetRow
from .metrics import multiclass_brier, multiclass_log_loss
from .training import predict_with_models


@dataclass(frozen=True)
class WalkForwardConfig:
    train_size: int = 80
    test_size: int = 20
    step_size: int = 20


def walk_forward_backtest(rows: list[DatasetRow], config: WalkForwardConfig | None = None) -> dict:
    config = config or WalkForwardConfig()
    ordered = sorted(rows, key=lambda row: row.match.event_time)
    predictions = []
    labels = []
    windows = []
    start = 0
    while start + config.train_size + config.test_size <= len(ordered):
        train = ordered[start : start + config.train_size]
        test = ordered[start + config.train_size : start + config.train_size + config.test_size]
        for row in test:
            pred = predict_with_models([item.match for item in train], row.match)
            predictions.append(pred["ensemble"])
            labels.append(str(row.labels["result"]))
        windows.append(
            {
                "train_start": train[0].match.event_time.date().isoformat(),
                "train_end": train[-1].match.event_time.date().isoformat(),
                "test_start": test[0].match.event_time.date().isoformat(),
                "test_end": test[-1].match.event_time.date().isoformat(),
                "test_count": len(test),
            }
        )
        start += config.step_size
    return {
        "windows": windows,
        "prediction_count": len(predictions),
        "metrics": {
            "log_loss": multiclass_log_loss(predictions, labels) if predictions else None,
            "brier": multiclass_brier(predictions, labels) if predictions else None,
        },
        "markets": ["match_winner", "double_chance", "draw_no_bet", "over_under_1_5", "over_under_2_5", "over_under_3_5", "both_teams_to_score"],
        "lab_only": True,
        "can_influence_picks": False,
    }


def walk_forward_from_csv(path: str = "data/MATCHES.csv", start: str | None = None, end: str | None = None, limit: int | None = 240) -> dict:
    from .training import build_dataset_from_csv

    rows, report = build_dataset_from_csv(path, start=start, end=end, limit=limit)
    result = walk_forward_backtest(rows)
    result["dataset"] = report
    return result
