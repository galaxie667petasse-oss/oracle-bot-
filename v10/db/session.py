from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from v10.config import V10Settings, load_settings, mask_database_url


def create_engine_from_settings(settings: V10Settings | None = None, database_url: str | None = None) -> Engine:
    settings = settings or load_settings()
    url = database_url or settings.require_database_url(allow_sqlite=True)
    kwargs = {"echo": settings.database_echo, "future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs.update(
            {
                "pool_size": settings.database_pool_size,
                "max_overflow": settings.database_max_overflow,
                "pool_timeout": settings.database_pool_timeout_seconds,
                "connect_args": {"options": f"-c statement_timeout={settings.database_statement_timeout_ms}"},
            }
        )
    return create_engine(url, **kwargs)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def database_health(engine: Engine) -> dict[str, object]:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        status = "ok"
        error = ""
    except Exception as exc:
        status = "error"
        error = str(exc)
    return {
        "status": status,
        "database_url": mask_database_url(str(engine.url)),
        "dialect": engine.dialect.name,
        "error": error,
    }

