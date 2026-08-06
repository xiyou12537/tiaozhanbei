from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def build_engine(database_url: str):
    return create_engine(database_url, pool_pre_ping=True)


def build_session_factory(database_url: str):
    engine = build_engine(database_url)
    return engine, sessionmaker(autocommit=False, autoflush=False, bind=engine)
