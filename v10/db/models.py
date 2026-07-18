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
