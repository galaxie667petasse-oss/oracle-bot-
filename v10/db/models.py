import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from v10.db.base import Base
from v10.db.types import JSONB_TYPE, UTCDateTime
from v10.time import utc_now


def new_uuid() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False)


class Provider(TimestampMixin, Base):
    __tablename__ = "v10_providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(40), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Competition(TimestampMixin, Base):
    __tablename__ = "v10_competitions"
    __table_args__ = (UniqueConstraint("provider_id", "external_id", name="uq_v10_competition_provider_external"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    provider_id: Mapped[str] = mapped_column(ForeignKey("v10_providers.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str | None] = mapped_column(String(120))
    competition_type: Mapped[str | None] = mapped_column(String(60))
    level: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB_TYPE, default=dict, nullable=False)

    provider = relationship("Provider")


class Season(TimestampMixin, Base):
    __tablename__ = "v10_seasons"
    __table_args__ = (UniqueConstraint("competition_id", "external_id", name="uq_v10_season_competition_external"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    competition_id: Mapped[str] = mapped_column(ForeignKey("v10_competitions.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    start_year: Mapped[int | None] = mapped_column(Integer)
    end_year: Mapped[int | None] = mapped_column(Integer)
    name: Mapped[str | None] = mapped_column(String(160))
    starts_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    ends_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[str | None] = mapped_column(String(40))


class Team(TimestampMixin, Base):
    __tablename__ = "v10_teams"
    __table_args__ = (UniqueConstraint("provider_id", "external_id", name="uq_v10_team_provider_external"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    provider_id: Mapped[str] = mapped_column(ForeignKey("v10_providers.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str | None] = mapped_column(String(120))
    code: Mapped[str | None] = mapped_column(String(40))
    logo_url: Mapped[str | None] = mapped_column(String(700))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB_TYPE, default=dict, nullable=False)

    provider = relationship("Provider")


class Fixture(TimestampMixin, Base):
    __tablename__ = "v10_fixtures"
    __table_args__ = (
        UniqueConstraint("provider_id", "external_id", name="uq_v10_fixture_provider_external"),
        CheckConstraint("home_team_id <> away_team_id", name="ck_v10_fixture_distinct_teams"),
        Index("ix_v10_fixture_event_time", "event_time"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    provider_id: Mapped[str] = mapped_column(ForeignKey("v10_providers.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    competition_id: Mapped[str] = mapped_column(ForeignKey("v10_competitions.id"), nullable=False)
    season_id: Mapped[str | None] = mapped_column(ForeignKey("v10_seasons.id"))
    home_team_id: Mapped[str] = mapped_column(ForeignKey("v10_teams.id"), nullable=False)
    away_team_id: Mapped[str] = mapped_column(ForeignKey("v10_teams.id"), nullable=False)
    event_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    canonical_status: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_status: Mapped[str | None] = mapped_column(String(80))
    venue: Mapped[str | None] = mapped_column(String(240))
    round_name: Mapped[str | None] = mapped_column(String(160))
    initial_observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB_TYPE, default=dict, nullable=False)

    provider = relationship("Provider")
    competition = relationship("Competition")
    home_team = relationship("Team", foreign_keys=[home_team_id])
    away_team = relationship("Team", foreign_keys=[away_team_id])


class FixtureStatusHistory(TimestampMixin, Base):
    __tablename__ = "v10_fixture_status_history"
    __table_args__ = (
        UniqueConstraint("fixture_id", "canonical_status", "provider_status", "observed_at", name="uq_v10_fixture_status_observation"),
        Index("ix_v10_fixture_status_as_of", "fixture_id", "observed_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    fixture_id: Mapped[str] = mapped_column(ForeignKey("v10_fixtures.id"), nullable=False)
    canonical_status: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_status: Mapped[str | None] = mapped_column(String(80))
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    raw_payload_id: Mapped[str | None] = mapped_column(ForeignKey("v10_raw_api_payloads.id"))


class Bookmaker(TimestampMixin, Base):
    __tablename__ = "v10_bookmakers"
    __table_args__ = (
        UniqueConstraint("provider_id", "external_id", name="uq_v10_bookmaker_provider_external"),
        UniqueConstraint("provider_id", "canonical_key", name="uq_v10_bookmaker_provider_canonical"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    provider_id: Mapped[str] = mapped_column(ForeignKey("v10_providers.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    canonical_key: Mapped[str] = mapped_column(String(160), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Market(TimestampMixin, Base):
    __tablename__ = "v10_markets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    selection_count: Mapped[int | None] = mapped_column(Integer)
    settlement_handler: Mapped[str] = mapped_column(String(120), nullable=False)
    parameters_json: Mapped[dict[str, Any]] = mapped_column("parameters", JSONB_TYPE, default=dict, nullable=False)


class MarketSelection(TimestampMixin, Base):
    __tablename__ = "v10_market_selections"
    __table_args__ = (Index("ix_v10_market_selection_lookup", "market_id", "selection_key", "line_value", "handicap_value"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    market_id: Mapped[str] = mapped_column(ForeignKey("v10_markets.id"), nullable=False)
    selection_key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    line_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    handicap_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))


class IngestionRun(TimestampMixin, Base):
    __tablename__ = "v10_ingestion_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    run_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str] = mapped_column(String(300), nullable=False)
    parameters_json: Mapped[dict[str, Any]] = mapped_column("parameters", JSONB_TYPE, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    records_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ignored: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    code_version: Mapped[str | None] = mapped_column(String(80))
    error_summary: Mapped[str | None] = mapped_column(Text)


class RawApiPayload(TimestampMixin, Base):
    __tablename__ = "v10_raw_api_payloads"
    __table_args__ = (
        UniqueConstraint("provider_id", "endpoint", "request_fingerprint", "content_hash", name="uq_v10_raw_payload_context_hash"),
        Index("ix_v10_raw_payload_fetched", "provider_id", "fetched_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    provider_id: Mapped[str] = mapped_column(ForeignKey("v10_providers.id"), nullable=False)
    ingestion_run_id: Mapped[str | None] = mapped_column(ForeignKey("v10_ingestion_runs.id"))
    endpoint: Mapped[str] = mapped_column(String(160), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    request_parameters_json: Mapped[dict[str, Any]] = mapped_column("request_parameters", JSONB_TYPE, default=dict, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    provider_request_id: Mapped[str | None] = mapped_column(String(160))
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict[str, Any] | list[Any]] = mapped_column("payload", JSONB_TYPE, nullable=False)
    payload_size: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(40), default="1.0", nullable=False)
    processing_status: Mapped[str] = mapped_column(String(40), default="stored", nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(500))


class OddsSnapshot(TimestampMixin, Base):
    __tablename__ = "v10_odds_snapshots"
    __table_args__ = (
        UniqueConstraint("content_fingerprint", name="uq_v10_odds_snapshot_fingerprint"),
        CheckConstraint("decimal_odds > 1", name="ck_v10_odds_decimal_gt_1"),
        Index("ix_v10_odds_fixture_market_observed", "fixture_id", "market_id", "observed_at"),
        Index("ix_v10_odds_lookup", "fixture_id", "bookmaker_id", "market_id", "selection_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    fixture_id: Mapped[str] = mapped_column(ForeignKey("v10_fixtures.id"), nullable=False)
    bookmaker_id: Mapped[str] = mapped_column(ForeignKey("v10_bookmakers.id"), nullable=False)
    market_id: Mapped[str] = mapped_column(ForeignKey("v10_markets.id"), nullable=False)
    selection_key: Mapped[str] = mapped_column(String(80), nullable=False)
    line_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    decimal_odds: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    original_odds: Mapped[str] = mapped_column(String(80), nullable=False)
    original_format: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    provider_event_timestamp: Mapped[datetime | None] = mapped_column(UTCDateTime())
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    raw_payload_id: Mapped[str | None] = mapped_column(ForeignKey("v10_raw_api_payloads.id"))
    ingestion_run_id: Mapped[str | None] = mapped_column(ForeignKey("v10_ingestion_runs.id"))
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)


class NormalizedMarketSnapshot(TimestampMixin, Base):
    __tablename__ = "v10_normalized_market_snapshots"
    __table_args__ = (
        UniqueConstraint("fixture_id", "market_id", "line_value", "snapshot_time", "margin_method", name="uq_v10_market_snapshot_time"),
        Index("ix_v10_market_snapshot_as_of", "fixture_id", "market_id", "snapshot_time"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    fixture_id: Mapped[str] = mapped_column(ForeignKey("v10_fixtures.id"), nullable=False)
    market_id: Mapped[str] = mapped_column(ForeignKey("v10_markets.id"), nullable=False)
    line_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    snapshot_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    bookmaker_count: Mapped[int] = mapped_column(Integer, nullable=False)
    best_odds_json: Mapped[dict[str, Any]] = mapped_column("best_odds", JSONB_TYPE, default=dict, nullable=False)
    median_odds_json: Mapped[dict[str, Any]] = mapped_column("median_odds", JSONB_TYPE, default=dict, nullable=False)
    mean_odds_json: Mapped[dict[str, Any]] = mapped_column("mean_odds", JSONB_TYPE, default=dict, nullable=False)
    overround: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    fair_probabilities_json: Mapped[dict[str, Any]] = mapped_column("fair_probabilities", JSONB_TYPE, default=dict, nullable=False)
    margin_method: Mapped[str] = mapped_column(String(80), default="proportional", nullable=False)
    source_odds_snapshot_ids_json: Mapped[list[str]] = mapped_column("source_odds_snapshot_ids", JSONB_TYPE, default=list, nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)


class AdvisoryLock(Base):
    __tablename__ = "v10_advisory_locks"

    lock_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    owner: Mapped[str] = mapped_column(String(160), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)


class ModelDefinition(TimestampMixin, Base):
    __tablename__ = "v10_model_definitions"
    __table_args__ = (UniqueConstraint("model_key", name="uq_v10_model_definition_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    model_key: Mapped[str] = mapped_column(String(120), nullable=False)
    model_family: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    code_version: Mapped[str] = mapped_column(String(80), nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    hyperparameter_schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ModelVersion(TimestampMixin, Base):
    __tablename__ = "v10_model_versions"
    __table_args__ = (
        UniqueConstraint("model_definition_id", "version", name="uq_v10_model_version_definition_version"),
        Index("ix_v10_model_version_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    model_definition_id: Mapped[str] = mapped_column(ForeignKey("v10_model_definitions.id"), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    training_start: Mapped[datetime | None] = mapped_column(UTCDateTime())
    training_end: Mapped[datetime | None] = mapped_column(UTCDateTime())
    competitions_json: Mapped[list[str]] = mapped_column("competitions", JSONB_TYPE, default=list, nullable=False)
    markets_json: Mapped[list[str]] = mapped_column("markets", JSONB_TYPE, default=list, nullable=False)
    hyperparameters_json: Mapped[dict[str, Any]] = mapped_column("hyperparameters", JSONB_TYPE, default=dict, nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    dataset_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    match_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    training_metrics_json: Mapped[dict[str, Any]] = mapped_column("training_metrics", JSONB_TYPE, default=dict, nullable=False)
    validation_metrics_json: Mapped[dict[str, Any]] = mapped_column("validation_metrics", JSONB_TYPE, default=dict, nullable=False)
    artifact_json: Mapped[dict[str, Any]] = mapped_column("artifact", JSONB_TYPE, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="DRAFT", nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    definition = relationship("ModelDefinition")


class FeatureSnapshot(TimestampMixin, Base):
    __tablename__ = "v10_feature_snapshots"
    __table_args__ = (
        UniqueConstraint("fixture_external_id", "as_of", "feature_schema_version", "source_fingerprint", name="uq_v10_feature_snapshot_external_as_of"),
        Index("ix_v10_feature_snapshot_as_of", "fixture_id", "as_of"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    fixture_id: Mapped[str | None] = mapped_column(ForeignKey("v10_fixtures.id"))
    fixture_external_id: Mapped[str] = mapped_column(String(160), nullable=False)
    as_of: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    data_cutoff: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    data_completeness: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    feature_values_json: Mapped[dict[str, Any]] = mapped_column("feature_values", JSONB_TYPE, default=dict, nullable=False)
    missing_indicators_json: Mapped[dict[str, Any]] = mapped_column("missing_indicators", JSONB_TYPE, default=dict, nullable=False)
    warnings_json: Mapped[list[str]] = mapped_column("warnings", JSONB_TYPE, default=list, nullable=False)


class ScoreDistribution(Base):
    __tablename__ = "v10_score_distributions"
    __table_args__ = (
        UniqueConstraint("fixture_external_id", "model_version_id", "feature_snapshot_id", name="uq_v10_score_distribution_prediction"),
        Index("ix_v10_score_distribution_fixture", "fixture_id", "generated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    fixture_id: Mapped[str | None] = mapped_column(ForeignKey("v10_fixtures.id"))
    fixture_external_id: Mapped[str] = mapped_column(String(160), nullable=False)
    model_version_id: Mapped[str] = mapped_column(ForeignKey("v10_model_versions.id"), nullable=False)
    feature_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("v10_feature_snapshots.id"))
    max_goals_home: Mapped[int] = mapped_column(Integer, nullable=False)
    max_goals_away: Mapped[int] = mapped_column(Integer, nullable=False)
    matrix_json: Mapped[list[list[float]]] = mapped_column("matrix", JSONB_TYPE, default=list, nullable=False)
    tail_mass: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    expected_home_goals: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    expected_away_goals: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class StatisticalPrediction(Base):
    __tablename__ = "v10_statistical_predictions"
    __table_args__ = (
        UniqueConstraint("prediction_fingerprint", name="uq_v10_statistical_prediction_fingerprint"),
        Index("ix_v10_stat_prediction_fixture_market", "fixture_id", "market_key", "selection_key", "prediction_time"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    fixture_id: Mapped[str | None] = mapped_column(ForeignKey("v10_fixtures.id"))
    fixture_external_id: Mapped[str] = mapped_column(String(160), nullable=False)
    model_version_id: Mapped[str] = mapped_column(ForeignKey("v10_model_versions.id"), nullable=False)
    feature_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("v10_feature_snapshots.id"))
    prediction_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    market_key: Mapped[str] = mapped_column(String(80), nullable=False)
    selection_key: Mapped[str] = mapped_column(String(80), nullable=False)
    raw_probability: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    calibrated_probability: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    lower_bound: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    upper_bound: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    uncertainty_method: Mapped[str] = mapped_column(String(120), default="heuristic", nullable=False)
    model_diagnostics_json: Mapped[dict[str, Any]] = mapped_column("model_diagnostics", JSONB_TYPE, default=dict, nullable=False)
    prediction_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class CalibrationModel(TimestampMixin, Base):
    __tablename__ = "v10_calibration_models"
    __table_args__ = (Index("ix_v10_calibration_lookup", "source_model_version_id", "market_key", "selection_key", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source_model_version_id: Mapped[str] = mapped_column(ForeignKey("v10_model_versions.id"), nullable=False)
    market_key: Mapped[str] = mapped_column(String(80), nullable=False)
    selection_key: Mapped[str | None] = mapped_column(String(80))
    method: Mapped[str] = mapped_column(String(80), nullable=False)
    training_start: Mapped[datetime | None] = mapped_column(UTCDateTime())
    training_end: Mapped[datetime | None] = mapped_column(UTCDateTime())
    sample_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parameters_json: Mapped[dict[str, Any]] = mapped_column("parameters", JSONB_TYPE, default=dict, nullable=False)
    metrics_before_json: Mapped[dict[str, Any]] = mapped_column("metrics_before", JSONB_TYPE, default=dict, nullable=False)
    metrics_after_json: Mapped[dict[str, Any]] = mapped_column("metrics_after", JSONB_TYPE, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="DRAFT", nullable=False)


class EvaluationRun(TimestampMixin, Base):
    __tablename__ = "v10_evaluation_runs"
    __table_args__ = (Index("ix_v10_evaluation_run_type_status", "evaluation_type", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    evaluation_type: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version_ids_json: Mapped[list[str]] = mapped_column("model_version_ids", JSONB_TYPE, default=list, nullable=False)
    period_start: Mapped[datetime | None] = mapped_column(UTCDateTime())
    period_end: Mapped[datetime | None] = mapped_column(UTCDateTime())
    competitions_json: Mapped[list[str]] = mapped_column("competitions", JSONB_TYPE, default=list, nullable=False)
    markets_json: Mapped[list[str]] = mapped_column("markets", JSONB_TYPE, default=list, nullable=False)
    configuration_json: Mapped[dict[str, Any]] = mapped_column("configuration", JSONB_TYPE, default=dict, nullable=False)
    dataset_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(40), default="DRAFT", nullable=False)
    metrics_json: Mapped[dict[str, Any]] = mapped_column("metrics", JSONB_TYPE, default=dict, nullable=False)
    artifact_paths_json: Mapped[list[str]] = mapped_column("artifact_paths", JSONB_TYPE, default=list, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)


class LLMProviderModel(TimestampMixin, Base):
    __tablename__ = "v10_llm_providers"
    __table_args__ = (UniqueConstraint("provider_key", name="uq_v10_llm_provider_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    provider_key: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB_TYPE, default=dict, nullable=False)


class LLMModelConfig(TimestampMixin, Base):
    __tablename__ = "v10_llm_model_configs"
    __table_args__ = (UniqueConstraint("logical_tier", "model_name", "reasoning_effort", name="uq_v10_llm_model_config"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    provider_id: Mapped[str | None] = mapped_column(ForeignKey("v10_llm_providers.id"))
    logical_tier: Mapped[str] = mapped_column(String(40), nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False)
    reasoning_effort: Mapped[str] = mapped_column(String(40), nullable=False)
    mode: Mapped[str] = mapped_column(String(40), default="standard", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB_TYPE, default=dict, nullable=False)


class PromptTemplate(TimestampMixin, Base):
    __tablename__ = "v10_prompt_templates"
    __table_args__ = (UniqueConstraint("prompt_key", name="uq_v10_prompt_template_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    prompt_key: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PromptVersion(TimestampMixin, Base):
    __tablename__ = "v10_prompt_versions"
    __table_args__ = (UniqueConstraint("prompt_template_id", "version", name="uq_v10_prompt_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    prompt_template_id: Mapped[str] = mapped_column(ForeignKey("v10_prompt_templates.id"), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    template_text: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(40), default="1.0", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="DRAFT", nullable=False)


class LLMRun(Base):
    __tablename__ = "v10_llm_runs"
    __table_args__ = (
        Index("ix_v10_llm_run_candidate", "candidate_id", "started_at"),
        Index("ix_v10_llm_run_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    candidate_id: Mapped[str] = mapped_column(String(120), nullable=False)
    fixture_id: Mapped[str] = mapped_column(String(120), nullable=False)
    panel_or_agent: Mapped[str] = mapped_column(String(120), nullable=False)
    requested_model: Mapped[str] = mapped_column(String(160), nullable=False)
    used_model: Mapped[str | None] = mapped_column(String(160))
    reasoning_effort: Mapped[str] = mapped_column(String(40), nullable=False)
    prompt_version_id: Mapped[str | None] = mapped_column(ForeignKey("v10_prompt_versions.id"))
    packet_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cache_status: Mapped[str] = mapped_column(String(40), default="miss", nullable=False)
    error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    request_json: Mapped[dict[str, Any]] = mapped_column("request", JSONB_TYPE, default=dict, nullable=False)
    response_json: Mapped[dict[str, Any]] = mapped_column("response", JSONB_TYPE, default=dict, nullable=False)


class LLMToolCall(Base):
    __tablename__ = "v10_llm_tool_calls"
    __table_args__ = (Index("ix_v10_llm_tool_call_run", "llm_run_id", "tool_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    llm_run_id: Mapped[str] = mapped_column(ForeignKey("v10_llm_runs.id"), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    arguments_json: Mapped[dict[str, Any]] = mapped_column("arguments", JSONB_TYPE, default=dict, nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class LLMUsageRecord(Base):
    __tablename__ = "v10_llm_usage_records"
    __table_args__ = (Index("ix_v10_llm_usage_scan", "scan_id", "model_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    llm_run_id: Mapped[str | None] = mapped_column(ForeignKey("v10_llm_runs.id"))
    scan_id: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class AgentFindingRecord(Base):
    __tablename__ = "v10_agent_findings"
    __table_args__ = (Index("ix_v10_agent_finding_candidate", "candidate_id", "agent_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    llm_run_id: Mapped[str | None] = mapped_column(ForeignKey("v10_llm_runs.id"))
    candidate_id: Mapped[str] = mapped_column(String(120), nullable=False)
    fixture_id: Mapped[str] = mapped_column(String(120), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(120), nullable=False)
    verdict: Mapped[str] = mapped_column(String(60), nullable=False)
    veto: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    veto_code: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    evidence_ids_json: Mapped[list[str]] = mapped_column("evidence_ids", JSONB_TYPE, default=list, nullable=False)
    finding_json: Mapped[dict[str, Any]] = mapped_column("finding", JSONB_TYPE, default=dict, nullable=False)
    semantic_status: Mapped[str] = mapped_column(String(40), default="PENDING", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class ContradictionReportRecord(Base):
    __tablename__ = "v10_contradiction_reports"
    __table_args__ = (Index("ix_v10_contradiction_candidate", "candidate_id", "severity"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    candidate_id: Mapped[str] = mapped_column(String(120), nullable=False)
    fixture_id: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), nullable=False)
    hard_veto: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    contradictions_json: Mapped[list[dict[str, Any]]] = mapped_column("contradictions", JSONB_TYPE, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class FinalJudgeReviewRecord(Base):
    __tablename__ = "v10_final_judge_reviews"
    __table_args__ = (Index("ix_v10_final_judge_candidate", "candidate_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    llm_run_id: Mapped[str | None] = mapped_column(ForeignKey("v10_llm_runs.id"))
    candidate_id: Mapped[str] = mapped_column(String(120), nullable=False)
    fixture_id: Mapped[str] = mapped_column(String(120), nullable=False)
    recommendation: Mapped[str] = mapped_column(String(60), nullable=False)
    review_json: Mapped[dict[str, Any]] = mapped_column("review", JSONB_TYPE, default=dict, nullable=False)
    semantic_status: Mapped[str] = mapped_column(String(40), default="PENDING", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class ShadowDecisionRecord(Base):
    __tablename__ = "v10_shadow_decisions"
    __table_args__ = (UniqueConstraint("candidate_id", "decision_as_of", "packet_hash", name="uq_v10_shadow_decision_candidate_as_of"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    candidate_id: Mapped[str] = mapped_column(String(120), nullable=False)
    fixture_id: Mapped[str] = mapped_column(String(120), nullable=False)
    decision_as_of: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    packet_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    final_status: Mapped[str] = mapped_column(String(60), nullable=False)
    gate_reasons_json: Mapped[list[str]] = mapped_column("gate_reasons", JSONB_TYPE, default=list, nullable=False)
    llm_review_id: Mapped[str | None] = mapped_column(ForeignKey("v10_final_judge_reviews.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class BudgetReservation(Base):
    __tablename__ = "v10_budget_reservations"
    __table_args__ = (Index("ix_v10_budget_scope", "scope_key", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    scope_key: Mapped[str] = mapped_column(String(160), nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False)
    reserved_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    actual_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="RESERVED", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    reconciled_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class LLMCacheEntry(Base):
    __tablename__ = "v10_llm_cache_entries"
    __table_args__ = (UniqueConstraint("cache_key", name="uq_v10_llm_cache_key"), Index("ix_v10_llm_cache_expires", "expires_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False)
    packet_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    response_json: Mapped[dict[str, Any]] = mapped_column("response", JSONB_TYPE, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class ModelPricingVersion(TimestampMixin, Base):
    __tablename__ = "v10_model_pricing_versions"
    __table_args__ = (UniqueConstraint("provider_key", "model_name", "pricing_version", name="uq_v10_model_pricing_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    provider_key: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False)
    pricing_version: Mapped[str] = mapped_column(String(80), nullable=False)
    input_per_million_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    output_per_million_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    cached_input_per_million_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ScheduledJob(TimestampMixin, Base):
    __tablename__ = "v10_scheduled_jobs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_v10_scheduled_job_idempotency"),
        Index("ix_v10_scheduled_job_due", "status", "due_at", "priority"),
        Index("ix_v10_scheduled_job_fixture", "fixture_id", "job_type"),
        Index("ix_v10_scheduled_job_lease", "lease_expires_at", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_type: Mapped[str] = mapped_column(String(80), nullable=False)
    fixture_id: Mapped[str | None] = mapped_column(ForeignKey("v10_fixtures.id"))
    candidate_id: Mapped[str | None] = mapped_column(String(120))
    provider_key: Mapped[str | None] = mapped_column(String(80))
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    due_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    not_before: Mapped[datetime | None] = mapped_column(UTCDateTime())
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(40), default="PENDING", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column("payload", JSONB_TYPE, default=dict, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(160))
    lease_acquired_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_error_code: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    last_error_summary: Mapped[str] = mapped_column(String(500), default="", nullable=False)


class JobAttempt(Base):
    __tablename__ = "v10_job_attempts"
    __table_args__ = (
        UniqueConstraint("job_id", "attempt_number", name="uq_v10_job_attempt_number"),
        Index("ix_v10_job_attempt_job", "job_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(ForeignKey("v10_scheduled_jobs.id"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    worker_id: Mapped[str] = mapped_column(String(160), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result_summary_json: Mapped[dict[str, Any]] = mapped_column("result_summary", JSONB_TYPE, default=dict, nullable=False)
    exception_class: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    retry_reason: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    metrics_json: Mapped[dict[str, Any]] = mapped_column("metrics", JSONB_TYPE, default=dict, nullable=False)


class SchedulerRun(Base):
    __tablename__ = "v10_scheduler_runs"
    __table_args__ = (Index("ix_v10_scheduler_run_started", "started_at", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(40), default="RUNNING", nullable=False)
    jobs_claimed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_retried: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exit_reason: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    code_version: Mapped[str] = mapped_column(String(80), default="", nullable=False)


class ScanRun(Base):
    __tablename__ = "v10_scan_runs"
    __table_args__ = (Index("ix_v10_scan_run_decision", "decision_time", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    scope: Mapped[str] = mapped_column(String(120), nullable=False)
    decision_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    fixtures_considered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fixtures_filtered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidates_generated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidates_reviewed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    shadow_accepted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    watches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_provider_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_llm_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    summary_json: Mapped[dict[str, Any]] = mapped_column("summary", JSONB_TYPE, default=dict, nullable=False)


class ScanTarget(TimestampMixin, Base):
    __tablename__ = "v10_scan_targets"
    __table_args__ = (
        UniqueConstraint("fixture_id", name="uq_v10_scan_target_fixture"),
        Index("ix_v10_scan_target_next_due", "next_due_time", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    fixture_id: Mapped[str] = mapped_column(ForeignKey("v10_fixtures.id"), nullable=False)
    next_action: Mapped[str] = mapped_column(String(80), nullable=False)
    next_due_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    phase: Mapped[str] = mapped_column(String(40), nullable=False)
    last_fixture_refresh: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_odds_refresh: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_context_refresh: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_prediction: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_candidate_generation: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_llm_review: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_near_close_capture: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_result_refresh: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(40), default="ACTIVE", nullable=False)


class ProviderQuotaUsage(Base):
    __tablename__ = "v10_provider_quota_usage"
    __table_args__ = (Index("ix_v10_provider_quota_observed", "provider_key", "observed_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    provider_key: Mapped[str] = mapped_column(String(80), nullable=False)
    request_type: Mapped[str] = mapped_column(String(120), nullable=False)
    quota_headers_json: Mapped[dict[str, Any]] = mapped_column("quota_headers", JSONB_TYPE, default=dict, nullable=False)
    calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reset_time: Mapped[datetime | None] = mapped_column(UTCDateTime())
    estimated_remaining_quota: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(120), default="provider_headers", nullable=False)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class ProviderHealth(Base):
    __tablename__ = "v10_provider_health"
    __table_args__ = (Index("ix_v10_provider_health_lookup", "provider_key", "endpoint_class", "observed_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    provider_key: Mapped[str] = mapped_column(String(80), nullable=False)
    endpoint_class: Mapped[str] = mapped_column(String(120), nullable=False)
    health_status: Mapped[str] = mapped_column(String(40), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_error_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    circuit_status: Mapped[str] = mapped_column(String(40), default="CLOSED", nullable=False)
    degraded_reason: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class ProviderCacheEntry(Base):
    __tablename__ = "v10_provider_cache_entries"
    __table_args__ = (
        UniqueConstraint("cache_key", name="uq_v10_provider_cache_key"),
        Index("ix_v10_provider_cache_expiry", "provider_key", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(80), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(160), nullable=False)
    fixture_id: Mapped[str | None] = mapped_column(String(120))
    parameters_json: Mapped[dict[str, Any]] = mapped_column("parameters", JSONB_TYPE, default=dict, nullable=False)
    response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_json: Mapped[dict[str, Any]] = mapped_column("response", JSONB_TYPE, default=dict, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    stale_while_revalidate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class MaterialChangeEvent(Base):
    __tablename__ = "v10_material_change_events"
    __table_args__ = (Index("ix_v10_material_change_fixture", "fixture_id", "detected_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    fixture_id: Mapped[str] = mapped_column(String(120), nullable=False)
    candidate_id: Mapped[str | None] = mapped_column(String(120))
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    old_fingerprint: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    new_fingerprint: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    severity: Mapped[str] = mapped_column(String(40), default="INFO", nullable=False)
    material: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    evidence_ids_json: Mapped[list[str]] = mapped_column("evidence_ids", JSONB_TYPE, default=list, nullable=False)
    caused_rescan: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    caused_llm_rerun: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rules_json: Mapped[list[str]] = mapped_column("rules", JSONB_TYPE, default=list, nullable=False)


class ShadowExperiment(TimestampMixin, Base):
    __tablename__ = "v10_shadow_experiments"
    __table_args__ = (UniqueConstraint("experiment_key", "version", name="uq_v10_shadow_experiment_key_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    experiment_key: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    cohort_rules_json: Mapped[dict[str, Any]] = mapped_column("cohort_rules", JSONB_TYPE, default=dict, nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    ends_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(40), default="DRAFT", nullable=False)
    statistical_model_versions_json: Mapped[list[str]] = mapped_column("statistical_model_versions", JSONB_TYPE, default=list, nullable=False)
    prompt_versions_json: Mapped[list[str]] = mapped_column("prompt_versions", JSONB_TYPE, default=list, nullable=False)
    gate_version: Mapped[str] = mapped_column(String(80), default="deterministic_gate_v1", nullable=False)
    preregistered_metrics_json: Mapped[list[str]] = mapped_column("preregistered_metrics", JSONB_TYPE, default=list, nullable=False)


class ShadowExperimentDecision(Base):
    __tablename__ = "v10_shadow_experiment_decisions"
    __table_args__ = (
        UniqueConstraint("experiment_id", "candidate_id", "arm", "decision_hash", name="uq_v10_shadow_experiment_decision_immutable"),
        Index("ix_v10_shadow_experiment_decision_candidate", "candidate_id", "decision_time"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("v10_shadow_experiments.id"), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(120), nullable=False)
    fixture_id: Mapped[str] = mapped_column(String(120), nullable=False)
    arm: Mapped[str] = mapped_column(String(40), nullable=False)
    decision: Mapped[str] = mapped_column(String(80), nullable=False)
    decision_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    model_versions_json: Mapped[list[str]] = mapped_column("model_versions", JSONB_TYPE, default=list, nullable=False)
    prompt_versions_json: Mapped[list[str]] = mapped_column("prompt_versions", JSONB_TYPE, default=list, nullable=False)
    evidence_packet_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome_hidden: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    decision_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    decision_json: Mapped[dict[str, Any]] = mapped_column("decision_payload", JSONB_TYPE, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class ShadowExperimentOutcome(Base):
    __tablename__ = "v10_shadow_experiment_outcomes"
    __table_args__ = (UniqueConstraint("experiment_decision_id", "revealed_at", name="uq_v10_shadow_outcome_decision_reveal"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    experiment_decision_id: Mapped[str] = mapped_column(ForeignKey("v10_shadow_experiment_decisions.id"), nullable=False)
    fixture_result_json: Mapped[dict[str, Any]] = mapped_column("fixture_result", JSONB_TYPE, default=dict, nullable=False)
    settlement_json: Mapped[dict[str, Any]] = mapped_column("settlement", JSONB_TYPE, default=dict, nullable=False)
    closing_line_json: Mapped[dict[str, Any]] = mapped_column("closing_line", JSONB_TYPE, default=dict, nullable=False)
    clv_json: Mapped[dict[str, Any]] = mapped_column("clv", JSONB_TYPE, default=dict, nullable=False)
    paper_return_units: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"), nullable=False)
    brier_contribution: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    log_loss_contribution: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    revealed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class OperationalAlert(Base):
    __tablename__ = "v10_operational_alerts"
    __table_args__ = (Index("ix_v10_operational_alerts_status", "severity", "acknowledged", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    severity: Mapped[str] = mapped_column(String(40), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    scan_id: Mapped[str | None] = mapped_column(String(120))
    job_id: Mapped[str | None] = mapped_column(String(120))
    provider_key: Mapped[str | None] = mapped_column(String(80))
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class ServiceHeartbeat(Base):
    __tablename__ = "v10_service_heartbeats"
    __table_args__ = (UniqueConstraint("service_key", "instance_id", name="uq_v10_service_heartbeat_instance"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    service_key: Mapped[str] = mapped_column(String(120), nullable=False)
    instance_id: Mapped[str] = mapped_column(String(160), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="OK", nullable=False)
    details_json: Mapped[dict[str, Any]] = mapped_column("details", JSONB_TYPE, default=dict, nullable=False)
