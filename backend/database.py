"""Database configuration for legacy APIs and optional platform workflows."""

import logging
import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get(
    "PLATFORM_DATA_ROOT",
    os.path.join(ROOT_DIR, "data"),
)
os.makedirs(DATA_DIR, exist_ok=True)
DATABASE_PATH = Path(
    os.environ.get(
        "LEGACY_DATABASE_PATH",
        os.path.join(DATA_DIR, "partitioning.db"),
    )
).resolve()
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, echo=False)


@event.listens_for(engine, "connect")
def _enable_legacy_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """Enable FK enforcement only after the audited legacy migration exists."""
    migration_table = dbapi_connection.execute(
        "SELECT 1 FROM sqlite_master "
        "WHERE type='table' AND name='legacy_schema_migrations'"
    ).fetchone()
    if migration_table is None:
        return
    migration = dbapi_connection.execute(
        "SELECT 1 FROM legacy_schema_migrations "
        "WHERE migration_id='20260728_01_distributed_validation_v1'"
    ).fetchone()
    if migration is not None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

_platform_engine = None
_platform_session_local = None


def get_db():
    """Yield a legacy SQLite session for existing FastAPI routers."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize only explicitly isolated test databases.

    Runtime repositories must never perform implicit schema changes. Production
    and staging schemas are advanced only by the reviewed migration command.
    """
    initialization_mode = os.environ.get(
        "LEGACY_SCHEMA_INITIALIZATION_MODE",
        "validate_only",
    ).strip()
    if initialization_mode == "create_for_tests":
        Base.metadata.create_all(bind=engine)
        return
    if initialization_mode != "validate_only":
        raise RuntimeError(
            "LEGACY_SCHEMA_INITIALIZATION_MODE must be validate_only or "
            "create_for_tests."
        )


def get_session_local():
    """Return the platform workflow session factory when DATABASE_URL is configured."""
    global _platform_engine, _platform_session_local

    if _platform_session_local is not None:
        return _platform_session_local

    from backend.core.config import settings
    from backend.db.session import build_session_factory

    if not settings.DATABASE_URL.strip():
        raise RuntimeError("DATABASE_URL is not configured for platform workflow persistence.")

    _platform_engine, _platform_session_local = build_session_factory(settings.DATABASE_URL)
    return _platform_session_local


def init_platform_db() -> bool:
    """Initialize platform workflow tables when the platform database is configured."""
    from backend.core.config import has_platform_database

    if not has_platform_database():
        return False

    from backend.db import models as _platform_models  # noqa: F401
    from backend.db.base import Base as PlatformBase

    session_factory = get_session_local()
    bind = session_factory.kw["bind"]
    PlatformBase.metadata.create_all(bind=bind)
    logger.info("Platform workflow database initialized.")
    return True
