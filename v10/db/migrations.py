from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory

from v10.config import V10Settings, load_settings, mask_database_url
from v10.db.session import create_engine_from_settings, database_health


def alembic_config(settings: V10Settings | None = None) -> Config:
    settings = settings or load_settings()
    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.require_database_url(allow_sqlite=True))
    return cfg


def upgrade_head(settings: V10Settings | None = None) -> dict[str, Any]:
    settings = settings or load_settings()
    cfg = alembic_config(settings)
    command.upgrade(cfg, "head")
    return migration_status(settings)


def downgrade_base(settings: V10Settings | None = None) -> dict[str, Any]:
    settings = settings or load_settings()
    cfg = alembic_config(settings)
    command.downgrade(cfg, "base")
    return migration_status(settings)


def migration_status(settings: V10Settings | None = None) -> dict[str, Any]:
    settings = settings or load_settings()
    cfg = alembic_config(settings)
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    engine = create_engine_from_settings(settings)
    try:
        with engine.connect() as conn:
            current = MigrationContext.configure(conn).get_current_revision()
        return {
            "database_url": mask_database_url(settings.database_url),
            "dialect": engine.dialect.name,
            "current_revision": current,
            "heads": heads,
            "up_to_date": current in heads if current else False,
        }
    finally:
        engine.dispose()


def db_doctor(settings: V10Settings | None = None) -> dict[str, Any]:
    settings = settings or load_settings()
    report = settings.safe_report()
    try:
        engine = create_engine_from_settings(settings)
        report["database_health"] = database_health(engine)
        engine.dispose()
        report["migration_status"] = migration_status(settings)
    except Exception as exc:
        report["database_health"] = {"status": "error", "error": str(exc)}
    return report
