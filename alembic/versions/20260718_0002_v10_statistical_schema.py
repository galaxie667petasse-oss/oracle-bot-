"""v10 statistical model schema

Revision ID: 20260718_0002
Revises: 20260718_0001
Create Date: 2026-07-18
"""

from alembic import op

from v10.db.base import Base
from v10.db import models  # noqa: F401


revision = "20260718_0002"
down_revision = "20260718_0001"
branch_labels = None
depends_on = None


STAT_TABLES = [
    "v10_model_definitions",
    "v10_model_versions",
    "v10_feature_snapshots",
    "v10_score_distributions",
    "v10_statistical_predictions",
    "v10_calibration_models",
    "v10_evaluation_runs",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in STAT_TABLES]
    Base.metadata.create_all(bind=bind, tables=tables)


def downgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in reversed(STAT_TABLES)]
    Base.metadata.drop_all(bind=bind, tables=tables)
