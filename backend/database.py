"""Database configuration for legacy APIs and optional platform workflows."""

import logging
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
DATABASE_URL = os.getenv("LEGACY_DATABASE_URL", f"sqlite:///{os.path.join(DATA_DIR, 'partitioning.db')}")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Assistant persistence is release-managed. Keep these tables out of the
# compatibility ``init_db`` path so a production process cannot silently alter
# its schema before the backup-first migration is authorized.
ASSISTANT_TABLE_NAMES = frozenset({
    "assistant_sessions",
    "assistant_messages",
    "assistant_tool_executions",
})

_platform_engine = None
_platform_session_local = None


def get_db():
    """Yield a legacy SQLite session for existing FastAPI routers."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(bind=None):
    """Create only legacy/product tables which do not require a release migration."""
    tables = [table for table in Base.metadata.sorted_tables if table.name not in ASSISTANT_TABLE_NAMES]
    Base.metadata.create_all(bind=bind or engine, tables=tables)


def assistant_schema_ready(bind=None) -> bool:
    """Return whether every explicitly migrated Assistant table is present."""
    from sqlalchemy import inspect

    inspector = inspect(bind or engine)
    return all(inspector.has_table(table_name) for table_name in ASSISTANT_TABLE_NAMES)


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
