from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from v10.db.models import ProviderCacheEntry
from v10.llm.evidence.models import stable_hash
from v10.time import ensure_utc, utc_now


def provider_cache_key(provider_key: str, endpoint: str, parameters: dict[str, Any], fixture_id: str | None = None) -> str:
    return stable_hash({"provider": provider_key, "endpoint": endpoint, "parameters": parameters, "fixture_id": fixture_id})


def ttl_for_phase(phase: str) -> timedelta:
    return {
        "FAR": timedelta(hours=12),
        "T72": timedelta(hours=6),
        "T24": timedelta(hours=3),
        "T6": timedelta(minutes=45),
        "T90": timedelta(minutes=15),
        "T30": timedelta(minutes=5),
        "T10": timedelta(minutes=2),
        "RESULT_CHECK": timedelta(hours=6),
    }.get(phase, timedelta(minutes=30))


class ProviderCache:
    def __init__(self, session: Session):
        self.session = session

    def get(self, key: str, now: datetime | None = None) -> dict[str, Any] | None:
        now = ensure_utc(now or utc_now(), "now")
        row = self.session.scalar(select(ProviderCacheEntry).where(ProviderCacheEntry.cache_key == key))
        if not row:
            return None
        return {
            "cache_key": row.cache_key,
            "response": row.response_json,
            "fetched_at": row.fetched_at.isoformat(),
            "expires_at": row.expires_at.isoformat(),
            "stale": row.expires_at < now,
            "stale_while_revalidate": row.stale_while_revalidate,
        }

    def put(self, provider_key: str, endpoint: str, parameters: dict[str, Any], response: dict[str, Any], fixture_id: str | None = None, phase: str = "T24", now: datetime | None = None) -> ProviderCacheEntry:
        now = ensure_utc(now or utc_now(), "now")
        key = provider_cache_key(provider_key, endpoint, parameters, fixture_id)
        row = self.session.scalar(select(ProviderCacheEntry).where(ProviderCacheEntry.cache_key == key))
        if row is None:
            row = ProviderCacheEntry(
                cache_key=key,
                provider_key=provider_key,
                endpoint=endpoint,
                fixture_id=fixture_id,
                parameters_json=parameters,
                response_hash=stable_hash(response),
                response_json=response,
                fetched_at=now,
                expires_at=now + ttl_for_phase(phase),
                stale_while_revalidate=phase in {"FAR", "T72", "RESULT_CHECK"},
            )
            self.session.add(row)
        else:
            row.response_hash = stable_hash(response)
            row.response_json = response
            row.fetched_at = now
            row.expires_at = now + ttl_for_phase(phase)
            row.stale_while_revalidate = phase in {"FAR", "T72", "RESULT_CHECK"}
        self.session.flush()
        return row

