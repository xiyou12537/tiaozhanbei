from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

try:
    from dotenv import load_dotenv

    _env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(_env_path)
except ImportError:
    pass

from .api.routers.platform import router as platform_router
from .api.routers.molecule_workflow import router as molecule_workflow_router
from .core.config import has_platform_database, has_workflow_queue
from .database import SessionLocal, init_db, init_platform_db
from .routers import auth, chat, circuit, export, history, knowledge, mapping, partitioning
from .services.runtime_status import get_quantum_runtime_status

logger = logging.getLogger(__name__)
APP_VERSION = "3.0.0"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    try:
        init_platform_db()
    except Exception as exc:
        logger.warning("Platform database initialization skipped: %s", exc)
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Liangzhi Liuguang Distributed Quantum Platform",
    description="""
## Liangzhi Liuguang Backend Service

This backend currently exposes two groups of APIs:

1. Legacy compatibility APIs: `/api/auth`, `/api/knowledge`, `/api/chat`, `/api/circuit`, `/api/partition`, `/api/mapping`
2. Platform workflow APIs: `/api/platform/**`
    """,
    version=APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(circuit.router)
app.include_router(partitioning.router)
app.include_router(mapping.router)
app.include_router(export.router)
app.include_router(history.router)
app.include_router(chat.router)
app.include_router(knowledge.router)
app.include_router(platform_router)
app.include_router(molecule_workflow_router)


@app.get("/api/health")
def health_check():
    """Return runtime readiness for local frontend integration."""
    services: dict[str, dict[str, str]] = {
        "api": {"status": "ok", "detail": "FastAPI service is running."},
        "legacy_database": {"status": "ok", "detail": "SQLite compatibility database is reachable."},
        "authentication": {"status": "ok", "detail": "Authentication router is loaded."},
        "platform_database": {
            "status": "ok",
            "detail": "Platform database is configured."
            if has_platform_database()
            else "Not configured; sync workflows use in-memory state.",
        },
        "workflow_queue": {
            "status": "ok",
            "detail": "RabbitMQ queue is configured."
            if has_workflow_queue()
            else "Not configured; queued requests fall back to sync execution.",
        },
    }

    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        services["legacy_database"] = {"status": "degraded", "detail": f"SQLite database error: {exc}"}
        services["authentication"] = {
            "status": "degraded",
            "detail": "Authentication depends on the SQLite compatibility database.",
        }
    finally:
        db.close()

    services.update(get_quantum_runtime_status())

    critical_services = ["api", "legacy_database", "authentication"]
    overall_status = "ok" if all(services[name]["status"] == "ok" for name in critical_services) else "degraded"
    return {
        "status": overall_status,
        "version": APP_VERSION,
        "docs_url": "/docs",
        "services": services,
    }
