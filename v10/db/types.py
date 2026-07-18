from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, JSON
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import TypeDecorator


JSONB_TYPE = postgresql.JSONB().with_variant(JSON(), "sqlite")


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC datetimes, including SQLite round-trips."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("database datetime values must be timezone-aware")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
