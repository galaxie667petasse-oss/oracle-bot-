"""v10 llm shadow orchestration schema

Revision ID: 20260719_0003
Revises: 20260718_0002
Create Date: 2026-07-19
"""

from alembic import op

from v10.db.models import Base

revision = "20260719_0003"
down_revision = "20260718_0002"
branch_labels = None
depends_on = None

TABLES = [
    "v10_llm_providers",
    "v10_llm_model_configs",
    "v10_prompt_templates",
    "v10_prompt_versions",
    "v10_llm_runs",
    "v10_llm_tool_calls",
    "v10_llm_usage_records",
    "v10_agent_findings",
    "v10_contradiction_reports",
    "v10_final_judge_reviews",
    "v10_shadow_decisions",
    "v10_budget_reservations",
    "v10_llm_cache_entries",
    "v10_model_pricing_versions",
]


def upgrade() -> None:
    existing = set(op.get_bind().dialect.get_table_names(op.get_bind()))
    for table in Base.metadata.sorted_tables:
        if table.name in TABLES and table.name not in existing:
            table.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    for name in reversed(TABLES):
        table = Base.metadata.tables[name]
        table.drop(op.get_bind(), checkfirst=True)
