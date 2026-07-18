from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from v10 import VERSION
from v10.time import utc_now

from .models import ModelDefinition, ModelVersion


MODEL_FAMILIES = {
    "elo_multiclass_v1": "elo",
    "poisson_independent_v1": "poisson",
    "dixon_coles_v1": "dixon_coles",
    "ensemble_v1": "ensemble",
    "market_baseline_v1": "market",
}


class ModelRegistryRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_or_create_definition(self, model_key: str, feature_schema_version: str = "football_features_v1") -> tuple[ModelDefinition, bool]:
        existing = self.session.scalar(select(ModelDefinition).where(ModelDefinition.model_key == model_key))
        if existing:
            return existing, False
        row = ModelDefinition(
            model_key=model_key,
            model_family=MODEL_FAMILIES.get(model_key, "unknown"),
            display_name=model_key,
            description="Deterministic Oracle V10 statistical model.",
            code_version=VERSION,
            feature_schema_version=feature_schema_version,
            hyperparameter_schema_version="v1",
            is_active=True,
        )
        self.session.add(row)
        self.session.flush()
        return row, True

    def create_version(
        self,
        model_key: str,
        dataset_fingerprint: str,
        match_count: int,
        training_metrics: Mapping[str, Any] | None,
        validation_metrics: Mapping[str, Any] | None,
        artifact: Mapping[str, Any] | None,
        training_start: datetime | None = None,
        training_end: datetime | None = None,
        competitions: list[str] | None = None,
        markets: list[str] | None = None,
        status: str = "DRAFT",
    ) -> ModelVersion:
        definition, _ = self.get_or_create_definition(model_key)
        version = f"{utc_now().strftime('%Y%m%d%H%M%S')}_{dataset_fingerprint[:8]}"
        row = ModelVersion(
            model_definition_id=definition.id,
            version=version,
            training_start=training_start,
            training_end=training_end,
            competitions_json=competitions or [],
            markets_json=markets or ["match_winner", "double_chance", "draw_no_bet", "total_goals", "both_teams_to_score"],
            hyperparameters_json=(artifact or {}).get("config", {}) if isinstance(artifact, Mapping) else {},
            feature_schema_version=definition.feature_schema_version,
            dataset_fingerprint=dataset_fingerprint,
            match_count=match_count,
            training_metrics_json=dict(training_metrics or {}),
            validation_metrics_json=dict(validation_metrics or {}),
            artifact_json=dict(artifact or {}),
            status=status,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def activate(self, model_version_id: str) -> ModelVersion:
        row = self.session.get(ModelVersion, model_version_id)
        if row is None:
            raise ValueError("model version not found")
        if row.status not in {"DRAFT", "VALIDATED", "ACTIVE"}:
            raise ValueError("model version status cannot be activated")
        if row.match_count < 30:
            raise ValueError("sample too small to activate model version")
        definition_id = row.model_definition_id
        for active in self.session.scalars(
            select(ModelVersion).where(ModelVersion.model_definition_id == definition_id, ModelVersion.status == "ACTIVE")
        ):
            active.status = "RETIRED"
        row.status = "ACTIVE"
        row.activated_at = utc_now()
        self.session.flush()
        return row
