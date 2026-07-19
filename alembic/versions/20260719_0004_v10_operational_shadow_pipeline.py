"""v10 operational shadow pipeline schema

Revision ID: 20260719_0004
Revises: 20260719_0003
Create Date: 2026-07-19
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from alembic import op

from v10.db.models import Base

revision = "20260719_0004"
down_revision = "20260719_0003"
branch_labels = None
depends_on = None

TABLES = [
    "v10_scheduled_jobs",
    "v10_job_attempts",
    "v10_scheduler_runs",
    "v10_scan_runs",
    "v10_scan_targets",
    "v10_provider_quota_usage",
    "v10_provider_health",
    "v10_provider_cache_entries",
    "v10_material_change_events",
    "v10_shadow_experiments",
    "v10_shadow_experiment_decisions",
    "v10_shadow_experiment_outcomes",
    "v10_operational_alerts",
    "v10_service_heartbeats",
]


def upgrade() -> None:
    existing = set(op.get_bind().dialect.get_table_names(op.get_bind()))
    for table in Base.metadata.sorted_tables:
        if table.name in TABLES and table.name not in existing:
            table.create(op.get_bind(), checkfirst=True)
    now = datetime.now(timezone.utc)
    pricing = Base.metadata.tables["v10_model_pricing_versions"]
    op.bulk_insert(
        pricing,
        [
            {
                "id": str(uuid4()),
                "provider_key": "openai",
                "model_name": "gpt-5.6-luna",
                "pricing_version": "openai_short_context_2026_07_19",
                "input_per_million_usd": Decimal("1.00"),
                "output_per_million_usd": Decimal("6.00"),
                "cached_input_per_million_usd": Decimal("0.10"),
                "source_url": "https://developers.openai.com/api/docs/pricing",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": str(uuid4()),
                "provider_key": "openai",
                "model_name": "gpt-5.6-terra",
                "pricing_version": "openai_short_context_2026_07_19",
                "input_per_million_usd": Decimal("2.50"),
                "output_per_million_usd": Decimal("15.00"),
                "cached_input_per_million_usd": Decimal("0.25"),
                "source_url": "https://developers.openai.com/api/docs/pricing",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": str(uuid4()),
                "provider_key": "openai",
                "model_name": "gpt-5.6-sol",
                "pricing_version": "openai_short_context_2026_07_19",
                "input_per_million_usd": Decimal("5.00"),
                "output_per_million_usd": Decimal("30.00"),
                "cached_input_per_million_usd": Decimal("0.50"),
                "source_url": "https://developers.openai.com/api/docs/pricing",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM v10_model_pricing_versions WHERE pricing_version = 'openai_short_context_2026_07_19'")
    for name in reversed(TABLES):
        table = Base.metadata.tables[name]
        table.drop(op.get_bind(), checkfirst=True)
