"""v10 initial relational schema

Revision ID: 20260718_0001
Revises:
Create Date: 2026-07-18
"""
from typing import Sequence, Union

from alembic import op

from v10.db.base import Base
from v10.db import models  # noqa: F401


revision: str = "20260718_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[table for table in Base.metadata.sorted_tables if table.name.startswith("v10_")])


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=[table for table in reversed(Base.metadata.sorted_tables) if table.name.startswith("v10_")])

