from datetime import datetime, timezone
from typing import Any


def ensure_utc(value: datetime, field_name: str = "datetime") -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def parse_utc(value: Any, field_name: str = "datetime") -> datetime:
    if isinstance(value, datetime):
        return ensure_utc(value, field_name)
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except Exception as exc:
        raise ValueError(f"{field_name} must be ISO-8601") from exc
    return ensure_utc(parsed, field_name)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(value: datetime) -> str:
    return ensure_utc(value).isoformat().replace("+00:00", "Z")

