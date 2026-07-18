from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from v10 import VERSION

from .calibration import TemperatureScaler, calibration_result_to_dict
from .dataset import TemporalDatasetBuilder, dataset_fingerprint, load_matches_csv
from .dixon_coles import DixonColesModel
from .elo import EloModel
from .ensemble import EnsembleWeights, combine_probabilities, learn_weights_grid
from .metrics import multiclass_brier, multiclass_log_loss
from .poisson import PoissonModel
from .types import DatasetRow, HistoricalMatch


SUPPORTED_MODELS = {"elo_multiclass_v1", "poisson_independent_v1", "dixon_coles_v1", "ensemble_v1"}


def parse_cli_date(value: str | None, fallback: datetime | None = None) -> datetime | None:
    if not value:
        return fallback
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def train_model(model_key: str, rows: list[DatasetRow]) -> dict[str, Any]:
    if model_key not in SUPPORTED_MODELS:
        raise ValueError(f"unsupported model: {model_key}")
    matches = [row.match for row in rows]
    split = temporal_train_validation_split(rows)
    train_matches = [row.match for row in split["train"]]
    validation_rows = split["validation"]
    if model_key == "elo_multiclass_v1":
        model = EloModel().fit(train_matches)
    elif model_key == "poisson_independent_v1":
        model = PoissonModel().fit(train_matches)
    elif model_key == "dixon_coles_v1":
        model = DixonColesModel().fit(train_matches)
    else:
        return train_ensemble(rows)
    validation_predictions = [model.predict(row.match.home_team, row.match.away_team).probabilities_1x2 for row in validation_rows]
    validation_labels = [str(row.labels["result"]) for row in validation_rows]
    metrics = {
        "validation_log_loss": multiclass_log_loss(validation_predictions, validation_labels) if validation_rows else None,
        "validation_brier": multiclass_brier(validation_predictions, validation_labels) if validation_rows else None,
        "validation_count": len(validation_rows),
    }
    calibration = TemperatureScaler().fit(validation_predictions, validation_labels, min_samples=30) if validation_rows else None
    return {
        "model_key": model_key,
        "code_version": VERSION,
        "match_count": len(matches),
        "training_count": len(train_matches),
        "validation_count": len(validation_rows),
        "metrics": metrics,
        "calibration": calibration_result_to_dict(calibration) if calibration else None,
        "artifact": model.artifact(),
        "status": "DRAFT",
        "lab_only": True,
        "can_influence_picks": False,
    }


def train_ensemble(rows: list[DatasetRow]) -> dict[str, Any]:
    split = temporal_train_validation_split(rows)
    train_matches = [row.match for row in split["train"]]
    validation_rows = split["validation"]
    models = {
        "elo_multiclass_v1": EloModel().fit(train_matches),
        "poisson_independent_v1": PoissonModel().fit(train_matches),
        "dixon_coles_v1": DixonColesModel().fit(train_matches),
    }
    per_row = []
    labels = []
    for row in validation_rows:
        per_row.append({key: model.predict(row.match.home_team, row.match.away_team).probabilities_1x2 for key, model in models.items()})
        labels.append(str(row.labels["result"]))
    if per_row:
        weights, metrics = learn_weights_grid(per_row, labels, list(models), step=0.25)
    else:
        weights, metrics = EnsembleWeights({key: 1.0 / len(models) for key in models}), {"validation_log_loss": None, "sample_count": 0}
    return {
        "model_key": "ensemble_v1",
        "code_version": VERSION,
        "match_count": len(rows),
        "training_count": len(train_matches),
        "validation_count": len(validation_rows),
        "metrics": metrics,
        "artifact": {"weights": weights.weights, "base_models": {key: model.artifact() for key, model in models.items()}},
        "status": "DRAFT",
        "lab_only": True,
        "can_influence_picks": False,
    }


def temporal_train_validation_split(rows: list[DatasetRow], validation_fraction: float = 0.25) -> dict[str, list[DatasetRow]]:
    ordered = sorted(rows, key=lambda row: row.match.event_time)
    if len(ordered) < 4:
        return {"train": ordered, "validation": []}
    split_idx = max(1, int(len(ordered) * (1.0 - validation_fraction)))
    return {"train": ordered[:split_idx], "validation": ordered[split_idx:]}


def build_dataset_from_csv(path: str, start: str | None = None, end: str | None = None, limit: int | None = None) -> tuple[list[DatasetRow], dict]:
    raw_limit = None if (start or end) else limit
    matches = load_matches_csv(path, limit=raw_limit)
    builder = TemporalDatasetBuilder()
    rows, report = builder.build(matches, start=parse_cli_date(start), end=parse_cli_date(end))
    if limit is not None and (start or end):
        rows = rows[:limit]
        report = report.__class__(
            rows_seen=report.rows_seen,
            rows_included=len(rows),
            rows_excluded=report.rows_excluded,
            competitions=sorted({row.match.competition for row in rows})[:100],
            min_date=min((row.match.event_time.date().isoformat() for row in rows), default=None),
            max_date=max((row.match.event_time.date().isoformat() for row in rows), default=None),
            dataset_fingerprint=dataset_fingerprint(rows),
            warnings=report.warnings,
            dry_run=report.dry_run,
        )
    return rows, report.to_dict()


def train_from_csv(model_key: str, path: str = "data/MATCHES.csv", start: str | None = None, end: str | None = None, limit: int | None = None) -> dict[str, Any]:
    rows, report = build_dataset_from_csv(path, start=start, end=end, limit=limit)
    result = train_model(model_key, rows)
    result["dataset"] = report
    return result


def predict_with_models(train_matches: list[HistoricalMatch], fixture: HistoricalMatch) -> dict[str, Any]:
    elo = EloModel().fit(train_matches)
    poisson = PoissonModel().fit(train_matches)
    dc = DixonColesModel().fit(train_matches)
    predictions = {
        "elo_multiclass_v1": elo.predict(fixture.home_team, fixture.away_team),
        "poisson_independent_v1": poisson.predict(fixture.home_team, fixture.away_team),
        "dixon_coles_v1": dc.predict(fixture.home_team, fixture.away_team),
    }
    weights = EnsembleWeights({key: 1 / len(predictions) for key in predictions}, status="DRAFT")
    ensemble = combine_probabilities({key: pred.probabilities_1x2 for key, pred in predictions.items()}, weights)
    return {
        "models": {key: pred.to_dict() for key, pred in predictions.items()},
        "ensemble": ensemble,
        "weights": weights.weights,
    }
