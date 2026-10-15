"""CI-only integration: fail if real PostgreSQL is not configured; no SQLite fallback."""
import os
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text

from v10.config import V10Settings
from v10.db.locks import AdvisoryLockManager
from v10.db.migrations import migration_status, upgrade_head
from v10.db.session import create_engine_from_settings, create_session_factory
from v10.operations.provider_cache import ProviderCache, provider_cache_key
from v10.operations.quota import ProviderQuotaManager


def test_real_postgres_migrations_provider_cache_and_exclusive_lock():
    url = os.getenv("DATABASE_URL", "")
    assert url.startswith("postgresql"), "A real PostgreSQL DATABASE_URL is required for this test"
    settings = V10Settings(DATABASE_URL=url)
    assert upgrade_head(settings)["up_to_date"]
    assert migration_status(settings)["current_revision"] == "20260719_0004"
    engine = create_engine_from_settings(settings)
    factory = create_session_factory(engine)
    now = datetime.now(UTC)
    provider = "v11_ci_" + uuid4().hex
    try:
        with factory() as first, factory() as second:
            assert "PostgreSQL" in first.scalar(text("SELECT version()"))
            ProviderCache(first).put(provider, "odds", {"sport": "synthetic"}, {"test": True}, now=now, phase="T10")
            ProviderQuotaManager().record_headers(first, provider, "odds", {"x-requests-remaining": "7"}, observed_at=now)
            first.commit()
            cached = ProviderCache(second).get(provider_cache_key(provider, "odds", {"sport": "synthetic"}), now)
            assert cached["response"] == {"test": True} and not cached["stale"]
            lock = AdvisoryLockManager(first, provider)
            competing = AdvisoryLockManager(second, provider)
            assert lock.acquire()
            try:
                assert not competing.acquire()
            finally:
                lock.release()
            assert competing.acquire()
            competing.release()
    finally:
        engine.dispose()
