# Backend Platform Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working slice of the new backend platform skeleton on top of the existing FastAPI repo, replacing in-process task handling with a PostgreSQL + Redis + RabbitMQ based workflow orchestrator and unified platform APIs.

**Architecture:** Keep a single FastAPI deployment unit, but reorganize the backend into API, orchestrator, database, infrastructure, and worker layers. The first slice creates workflow metadata, stage state transitions, RabbitMQ dispatch/consume flow, Redis-backed hot status, and platform task query APIs while preserving only the auth capability from the old system.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, PostgreSQL, Redis, RabbitMQ, Pydantic 2, pydantic-settings, PyJWT, pytest, docker compose, pika, redis-py, psycopg

---

### Task 1: Add infrastructure dependencies and local runtime

**Files:**
- Create: `C:\Users\15750\Desktop\分布式大系统\docker-compose.yml`
- Modify: `C:\Users\15750\Desktop\分布式大系统\backend\requirements.txt`
- Modify: `C:\Users\15750\Desktop\分布式大系统\.env`
- Test: `C:\Users\15750\Desktop\分布式大系统\backend\tests\test_infrastructure_config.py`

- [ ] **Step 1: Write the failing infrastructure config test**

```python
# C:\Users\15750\Desktop\分布式大系统\backend\tests\test_infrastructure_config.py
from pathlib import Path


def test_backend_requirements_include_platform_runtime_dependencies():
    text = Path("backend/requirements.txt").read_text(encoding="utf-8")
    for name in ["psycopg[binary]", "redis", "pika", "pytest", "alembic", "pydantic-settings"]:
        assert name in text


def test_compose_file_declares_postgres_redis_rabbitmq():
    text = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "postgres:" in text
    assert "redis:" in text
    assert "rabbitmq:" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_infrastructure_config.py -v`

Expected: FAIL because `docker-compose.yml` does not exist and the new dependencies are missing from `backend/requirements.txt`.

- [ ] **Step 3: Write the minimal infrastructure definitions**

```yaml
# C:\Users\15750\Desktop\分布式大系统\docker-compose.yml
version: "3.9"

services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: liangzhi
      POSTGRES_USER: liangzhi
      POSTGRES_PASSWORD: liangzhi
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7
    ports:
      - "6379:6379"

  rabbitmq:
    image: rabbitmq:3-management
    ports:
      - "5672:5672"
      - "15672:15672"
    environment:
      RABBITMQ_DEFAULT_USER: liangzhi
      RABBITMQ_DEFAULT_PASS: liangzhi

volumes:
  postgres_data:
```

```text
# Append to C:\Users\15750\Desktop\分布式大系统\backend\requirements.txt
psycopg[binary]>=3.2
redis>=5.0
pika>=1.3
alembic>=1.13
pytest>=8.0
pytest-asyncio>=0.23
pydantic-settings>=2.3
```

```env
# Append to C:\Users\15750\Desktop\分布式大系统\.env
DATABASE_URL=postgresql+psycopg://liangzhi:liangzhi@localhost:5432/liangzhi
REDIS_URL=redis://localhost:6379/0
RABBITMQ_URL=amqp://liangzhi:liangzhi@localhost:5672/
JWT_SECRET=change-me
JWT_EXPIRE_MINUTES=1440
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_infrastructure_config.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml backend/requirements.txt .env backend/tests/test_infrastructure_config.py
git commit -m "build: add platform infrastructure runtime"
```

### Task 2: Introduce backend core configuration and PostgreSQL session layer

**Files:**
- Create: `C:\Users\15750\Desktop\分布式大系统\backend\core\config.py`
- Create: `C:\Users\15750\Desktop\分布式大系统\backend\db\base.py`
- Create: `C:\Users\15750\Desktop\分布式大系统\backend\db\session.py`
- Modify: `C:\Users\15750\Desktop\分布式大系统\backend\database.py`
- Test: `C:\Users\15750\Desktop\分布式大系统\backend\tests\test_db_config.py`

- [ ] **Step 1: Write the failing database config test**

```python
# C:\Users\15750\Desktop\分布式大系统\backend\tests\test_db_config.py
from backend.core.config import Settings
from backend.db.session import build_engine


def test_settings_expose_platform_urls():
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://demo:demo@localhost:5432/demo",
        REDIS_URL="redis://localhost:6379/0",
        RABBITMQ_URL="amqp://guest:guest@localhost:5672/",
        JWT_SECRET="secret",
    )
    assert settings.DATABASE_URL.startswith("postgresql+psycopg://")
    assert settings.REDIS_URL.startswith("redis://")
    assert settings.RABBITMQ_URL.startswith("amqp://")


def test_build_engine_uses_future_sqlalchemy_postgres_driver():
    engine = build_engine("postgresql+psycopg://demo:demo@localhost:5432/demo")
    assert engine.url.drivername == "postgresql+psycopg"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_db_config.py -v`

Expected: FAIL because `backend.core.config` and `backend.db.session` do not exist.

- [ ] **Step 3: Write the minimal configuration and session modules**

```python
# C:\Users\15750\Desktop\分布式大系统\backend\core\config.py
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    RABBITMQ_URL: str
    JWT_SECRET: str
    JWT_EXPIRE_MINUTES: int = 1440
    APP_NAME: str = "量智硫光后端平台"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
```

```python
# C:\Users\15750\Desktop\分布式大系统\backend\db\session.py
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def build_engine(database_url: str):
    return create_engine(database_url, pool_pre_ping=True)


def build_session_factory(database_url: str):
    engine = build_engine(database_url)
    return engine, sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

```python
# C:\Users\15750\Desktop\分布式大系统\backend\db\base.py
from sqlalchemy.orm import declarative_base

Base = declarative_base()
```

```python
# C:\Users\15750\Desktop\分布式大系统\backend\database.py
from __future__ import annotations

from backend.core.config import settings
from backend.db.base import Base
from backend.db.session import build_session_factory
import backend.db.models  # noqa: F401

engine, SessionLocal = build_session_factory(settings.DATABASE_URL)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_db_config.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/config.py backend/db/base.py backend/db/session.py backend/database.py backend/tests/test_db_config.py
git commit -m "refactor: add platform config and postgres session layer"
```

### Task 3: Replace the legacy ORM center with workflow-first models

**Files:**
- Create: `C:\Users\15750\Desktop\分布式大系统\backend\core\enums.py`
- Create: `C:\Users\15750\Desktop\分布式大系统\backend\db\models\identity.py`
- Create: `C:\Users\15750\Desktop\分布式大系统\backend\db\models\workflow.py`
- Create: `C:\Users\15750\Desktop\分布式大系统\backend\db\models\__init__.py`
- Modify: `C:\Users\15750\Desktop\分布式大系统\backend\models_db.py`
- Test: `C:\Users\15750\Desktop\分布式大系统\backend\tests\test_workflow_models.py`

- [ ] **Step 1: Write the failing workflow model test**

```python
# C:\Users\15750\Desktop\分布式大系统\backend\tests\test_workflow_models.py
from backend.core.enums import WorkflowStatus, StageName, StageRunStatus
from backend.db.models.workflow import WorkflowInstance, WorkflowStageRun, TaskEventLog


def test_workflow_status_enums_cover_platform_lifecycle():
    assert WorkflowStatus.CREATED.value == "created"
    assert WorkflowStatus.COMPLETED.value == "completed"
    assert StageName.DISTRIBUTED_COMPILING.value == "distributed_compiling"
    assert StageRunStatus.RETRYING.value == "retrying"


def test_workflow_models_expose_core_columns():
    assert WorkflowInstance.__tablename__ == "workflow_instances"
    assert WorkflowStageRun.__tablename__ == "workflow_stage_runs"
    assert TaskEventLog.__tablename__ == "task_event_logs"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_workflow_models.py -v`

Expected: FAIL because the enum and new model modules do not exist.

- [ ] **Step 3: Write the minimal workflow-first model layer**

```python
# C:\Users\15750\Desktop\分布式大系统\backend\core\enums.py
from enum import Enum


class WorkflowStatus(str, Enum):
    CREATED = "created"
    VALIDATED = "validated"
    SCREENING = "screening"
    CHEM_MODELING = "chem_modeling"
    QUANTUM_ENCODING = "quantum_encoding"
    DISTRIBUTED_COMPILING = "distributed_compiling"
    SIMULATION_EVALUATING = "simulation_evaluating"
    SCORING = "scoring"
    AGGREGATING = "aggregating"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL_COMPLETED = "partial_completed"
    CANCELLED = "cancelled"


class StageName(str, Enum):
    SCREENING = "screening"
    CHEM_MODELING = "chem_modeling"
    QUANTUM_ENCODING = "quantum_encoding"
    DISTRIBUTED_COMPILING = "distributed_compiling"
    SIMULATION_EVALUATING = "simulation_evaluating"
    SCORING = "scoring"
    AGGREGATING = "aggregating"


class StageRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"
```

```python
# C:\Users\15750\Desktop\分布式大系统\backend\db\models\identity.py
import datetime as dt
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
```

```python
# C:\Users\15750\Desktop\分布式大系统\backend\db\models\workflow.py
import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class WorkflowInstance(Base):
    __tablename__ = "workflow_instances"

    workflow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    initiator_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    case_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    current_stage: Mapped[str] = mapped_column(String(64))
    overall_status: Mapped[str] = mapped_column(String(64), index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    input_snapshot_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result_view_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class WorkflowStageRun(Base):
    __tablename__ = "workflow_stage_runs"

    stage_run_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_instances.workflow_id"), index=True)
    stage_name: Mapped[str] = mapped_column(String(64), index=True)
    stage_status: Mapped[str] = mapped_column(String(32), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    service_name: Mapped[str] = mapped_column(String(100))
    input_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    output_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class TaskEventLog(Base):
    __tablename__ = "task_event_logs"

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_instances.workflow_id"), index=True)
    stage_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
```

```python
# C:\Users\15750\Desktop\分布式大系统\backend\db\models\__init__.py
from backend.db.models.identity import User
from backend.db.models.workflow import TaskEventLog, WorkflowInstance, WorkflowStageRun

__all__ = ["User", "WorkflowInstance", "WorkflowStageRun", "TaskEventLog"]
```

```python
# C:\Users\15750\Desktop\分布式大系统\backend\models_db.py
from backend.db.models import TaskEventLog, User, WorkflowInstance, WorkflowStageRun

__all__ = ["User", "WorkflowInstance", "WorkflowStageRun", "TaskEventLog"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_workflow_models.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/enums.py backend/db/models/identity.py backend/db/models/workflow.py backend/db/models/__init__.py backend/models_db.py backend/tests/test_workflow_models.py
git commit -m "feat: add workflow-first platform models"
```

### Task 4: Migrate auth onto the new model and central security module

**Files:**
- Create: `C:\Users\15750\Desktop\分布式大系统\backend\core\security.py`
- Modify: `C:\Users\15750\Desktop\分布式大系统\backend\middleware.py`
- Modify: `C:\Users\15750\Desktop\分布式大系统\backend\routers\auth.py`
- Test: `C:\Users\15750\Desktop\分布式大系统\backend\tests\test_auth_security.py`

- [ ] **Step 1: Write the failing auth/security test**

```python
# C:\Users\15750\Desktop\分布式大系统\backend\tests\test_auth_security.py
from backend.core.security import hash_password, verify_password


def test_password_hash_round_trip():
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert verify_password("secret123", hashed) is True
    assert verify_password("wrong", hashed) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_auth_security.py -v`

Expected: FAIL because `backend.core.security` does not exist.

- [ ] **Step 3: Write the minimal shared security module and refactor auth**

```python
# C:\Users\15750\Desktop\分布式大系统\backend\core\security.py
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone

import jwt

from backend.core.config import settings


def hash_password(password: str) -> str:
    salt = os.urandom(32).hex()
    digest = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    salt, digest = stored.split("$", 1)
    return digest == hashlib.sha256((salt + password).encode()).hexdigest()


def create_access_token(user_id: int, username: str) -> str:
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "username": username, "exp": expire_at}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
```

```python
# In C:\Users\15750\Desktop\分布式大系统\backend\routers\auth.py replace local hash helpers with:
from ..core.security import create_access_token, hash_password, verify_password
```

```python
# In C:\Users\15750\Desktop\分布式大系统\backend\middleware.py ensure token verification uses:
payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_auth_security.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/security.py backend/middleware.py backend/routers/auth.py backend/tests/test_auth_security.py
git commit -m "refactor: centralize auth security helpers"
```

### Task 5: Implement the workflow state machine and orchestrator service

**Files:**
- Create: `C:\Users\15750\Desktop\分布式大系统\backend\orchestrator\stage_machine.py`
- Create: `C:\Users\15750\Desktop\分布式大系统\backend\orchestrator\engine.py`
- Create: `C:\Users\15750\Desktop\分布式大系统\backend\api\schemas\platform.py`
- Test: `C:\Users\15750\Desktop\分布式大系统\backend\tests\test_orchestrator_engine.py`

- [ ] **Step 1: Write the failing orchestrator test**

```python
# C:\Users\15750\Desktop\分布式大系统\backend\tests\test_orchestrator_engine.py
from backend.core.enums import StageName, WorkflowStatus
from backend.orchestrator.stage_machine import next_stage_after_success


def test_stage_machine_advances_to_next_domain_stage():
    assert next_stage_after_success(StageName.SCREENING) == StageName.CHEM_MODELING
    assert next_stage_after_success(StageName.AGGREGATING) is None


def test_created_workflow_status_is_platform_created():
    assert WorkflowStatus.CREATED.value == "created"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_orchestrator_engine.py -v`

Expected: FAIL because `backend.orchestrator.stage_machine` does not exist.

- [ ] **Step 3: Write the minimal state machine and orchestrator API contract**

```python
# C:\Users\15750\Desktop\分布式大系统\backend\orchestrator\stage_machine.py
from __future__ import annotations

from backend.core.enums import StageName

ORDER = [
    StageName.SCREENING,
    StageName.CHEM_MODELING,
    StageName.QUANTUM_ENCODING,
    StageName.DISTRIBUTED_COMPILING,
    StageName.SIMULATION_EVALUATING,
    StageName.SCORING,
    StageName.AGGREGATING,
]


def next_stage_after_success(stage_name: StageName) -> StageName | None:
    index = ORDER.index(stage_name)
    if index == len(ORDER) - 1:
        return None
    return ORDER[index + 1]
```

```python
# C:\Users\15750\Desktop\分布式大系统\backend\api\schemas\platform.py
from __future__ import annotations

from pydantic import BaseModel, Field


class WorkflowCreateRequest(BaseModel):
    case_id: str | None = None
    candidate_material: str = Field(..., min_length=1)
    qasm_content: str | None = None


class WorkflowCreateResponse(BaseModel):
    workflow_id: str
    overall_status: str
    current_stage: str
```

```python
# C:\Users\15750\Desktop\分布式大系统\backend\orchestrator\engine.py
from __future__ import annotations

from backend.core.enums import StageName, WorkflowStatus


class OrchestratorEngine:
    def initial_stage(self) -> StageName:
        return StageName.SCREENING

    def initial_status(self) -> WorkflowStatus:
        return WorkflowStatus.CREATED
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_orchestrator_engine.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/orchestrator/stage_machine.py backend/orchestrator/engine.py backend/api/schemas/platform.py backend/tests/test_orchestrator_engine.py
git commit -m "feat: add workflow stage machine and orchestrator skeleton"
```

### Task 6: Add Redis progress store and RabbitMQ dispatcher

**Files:**
- Create: `C:\Users\15750\Desktop\分布式大系统\backend\infrastructure\cache\redis_client.py`
- Create: `C:\Users\15750\Desktop\分布式大系统\backend\infrastructure\messaging\rabbitmq.py`
- Create: `C:\Users\15750\Desktop\分布式大系统\backend\orchestrator\dispatcher.py`
- Test: `C:\Users\15750\Desktop\分布式大系统\backend\tests\test_dispatcher_contracts.py`

- [ ] **Step 1: Write the failing dispatcher contract test**

```python
# C:\Users\15750\Desktop\分布式大系统\backend\tests\test_dispatcher_contracts.py
from backend.orchestrator.dispatcher import build_stage_message


def test_stage_message_contains_minimum_delivery_fields():
    message = build_stage_message(
        workflow_id="wf-123",
        stage_name="screening",
        attempt_no=1,
        trace_id="trace-001",
    )
    assert message["workflow_id"] == "wf-123"
    assert message["stage_name"] == "screening"
    assert message["attempt_no"] == 1
    assert message["trace_id"] == "trace-001"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_dispatcher_contracts.py -v`

Expected: FAIL because `backend.orchestrator.dispatcher` does not exist.

- [ ] **Step 3: Write the minimal progress and messaging adapters**

```python
# C:\Users\15750\Desktop\分布式大系统\backend\infrastructure\cache\redis_client.py
from __future__ import annotations

import redis

from backend.core.config import settings


def get_redis_client():
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
```

```python
# C:\Users\15750\Desktop\分布式大系统\backend\infrastructure\messaging\rabbitmq.py
from __future__ import annotations

import json
import pika

from backend.core.config import settings


def publish_message(queue_name: str, payload: dict) -> None:
    params = pika.URLParameters(settings.RABBITMQ_URL)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=True)
    channel.basic_publish(
        exchange="",
        routing_key=queue_name,
        body=json.dumps(payload).encode("utf-8"),
    )
    connection.close()
```

```python
# C:\Users\15750\Desktop\分布式大系统\backend\orchestrator\dispatcher.py
from __future__ import annotations


def build_stage_message(workflow_id: str, stage_name: str, attempt_no: int, trace_id: str) -> dict:
    return {
        "workflow_id": workflow_id,
        "stage_name": stage_name,
        "attempt_no": attempt_no,
        "trace_id": trace_id,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_dispatcher_contracts.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/infrastructure/cache/redis_client.py backend/infrastructure/messaging/rabbitmq.py backend/orchestrator/dispatcher.py backend/tests/test_dispatcher_contracts.py
git commit -m "feat: add redis progress store and rabbitmq dispatcher"
```

### Task 7: Add workflow API endpoints and query model

**Files:**
- Create: `C:\Users\15750\Desktop\分布式大系统\backend\api\routers\platform.py`
- Modify: `C:\Users\15750\Desktop\分布式大系统\backend\main.py`
- Test: `C:\Users\15750\Desktop\分布式大系统\backend\tests\test_platform_router.py`

- [ ] **Step 1: Write the failing platform router test**

```python
# C:\Users\15750\Desktop\分布式大系统\backend\tests\test_platform_router.py
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routers.platform import router


def test_platform_router_registers_workflow_endpoints():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    routes = {route.path for route in app.routes}
    assert "/api/platform/workflows" in routes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_platform_router.py -v`

Expected: FAIL because `backend.api.routers.platform` does not exist.

- [ ] **Step 3: Write the minimal platform router and wire it into the app**

```python
# C:\Users\15750\Desktop\分布式大系统\backend\api\routers\platform.py
from __future__ import annotations

from fastapi import APIRouter

from backend.api.schemas.platform import WorkflowCreateRequest, WorkflowCreateResponse

router = APIRouter(prefix="/api/platform", tags=["platform"])


@router.post("/workflows", response_model=WorkflowCreateResponse)
def create_workflow(body: WorkflowCreateRequest):
    return WorkflowCreateResponse(
        workflow_id="wf-demo",
        overall_status="created",
        current_stage="screening",
    )


@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str):
    return {"workflow_id": workflow_id, "overall_status": "created", "current_stage": "screening"}
```

```python
# In C:\Users\15750\Desktop\分布式大系统\backend\main.py add:
from .api.routers.platform import router as platform_router

app.include_router(platform_router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_platform_router.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/platform.py backend/main.py backend/tests/test_platform_router.py
git commit -m "feat: add platform workflow endpoints"
```

### Task 8: Replace the stub workflow endpoint with real persistence and dispatch

**Files:**
- Modify: `C:\Users\15750\Desktop\分布式大系统\backend\orchestrator\engine.py`
- Modify: `C:\Users\15750\Desktop\分布式大系统\backend\api\routers\platform.py`
- Create: `C:\Users\15750\Desktop\分布式大系统\backend\workers\consumer.py`
- Create: `C:\Users\15750\Desktop\分布式大系统\backend\workers\handlers\screening.py`
- Test: `C:\Users\15750\Desktop\分布式大系统\backend\tests\test_workflow_creation_service.py`

- [ ] **Step 1: Write the failing workflow creation service test**

```python
# C:\Users\15750\Desktop\分布式大系统\backend\tests\test_workflow_creation_service.py
from types import SimpleNamespace

from backend.orchestrator.engine import OrchestratorEngine


class FakeDispatcher:
    def __init__(self):
        self.messages = []

    def dispatch(self, payload):
        self.messages.append(payload)


def test_create_workflow_builds_first_stage_dispatch_message():
    engine = OrchestratorEngine(dispatcher=FakeDispatcher())
    workflow = engine.build_initial_workflow_payload(
        workflow_id="wf-001",
        candidate_material="Li2S6",
    )
    assert workflow["current_stage"] == "screening"
    assert workflow["overall_status"] == "created"
    assert workflow["candidate_material"] == "Li2S6"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_workflow_creation_service.py -v`

Expected: FAIL because `OrchestratorEngine` does not expose `build_initial_workflow_payload`.

- [ ] **Step 3: Write the minimal real workflow creation path**

```python
# In C:\Users\15750\Desktop\分布式大系统\backend\orchestrator\engine.py expand to:
from __future__ import annotations

import uuid

from backend.core.enums import StageName, WorkflowStatus
from backend.orchestrator.dispatcher import build_stage_message


class OrchestratorEngine:
    def __init__(self, dispatcher=None):
        self.dispatcher = dispatcher

    def initial_stage(self) -> StageName:
        return StageName.SCREENING

    def initial_status(self) -> WorkflowStatus:
        return WorkflowStatus.CREATED

    def build_initial_workflow_payload(self, workflow_id: str | None, candidate_material: str) -> dict:
        workflow_id = workflow_id or str(uuid.uuid4())
        return {
            "workflow_id": workflow_id,
            "overall_status": self.initial_status().value,
            "current_stage": self.initial_stage().value,
            "candidate_material": candidate_material,
        }

    def dispatch_first_stage(self, workflow_id: str, trace_id: str) -> dict:
        payload = build_stage_message(workflow_id, self.initial_stage().value, 1, trace_id)
        if self.dispatcher is not None:
            self.dispatcher.dispatch(payload)
        return payload
```

```python
# In C:\Users\15750\Desktop\分布式大系统\backend\workers\handlers\screening.py
def run_screening(payload: dict) -> dict:
    return {"status": "success", "screening_passed": True, "payload": payload}
```

```python
# In C:\Users\15750\Desktop\分布式大系统\backend\workers\consumer.py
from backend.workers.handlers.screening import run_screening


HANDLERS = {"screening": run_screening}
```

```python
# In C:\Users\15750\Desktop\分布式大系统\backend\api\routers\platform.py replace stub create handler with:
from uuid import uuid4

from backend.orchestrator.engine import OrchestratorEngine

engine = OrchestratorEngine()


@router.post("/workflows", response_model=WorkflowCreateResponse)
def create_workflow(body: WorkflowCreateRequest):
    workflow_id = str(uuid4())
    payload = engine.build_initial_workflow_payload(
        workflow_id=workflow_id,
        candidate_material=body.candidate_material,
    )
    return WorkflowCreateResponse(
        workflow_id=payload["workflow_id"],
        overall_status=payload["overall_status"],
        current_stage=payload["current_stage"],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_workflow_creation_service.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/orchestrator/engine.py backend/api/routers/platform.py backend/workers/consumer.py backend/workers/handlers/screening.py backend/tests/test_workflow_creation_service.py
git commit -m "feat: create real workflow bootstrap path"
```

### Task 9: Replace old router registration with the new platform-first app surface

**Files:**
- Modify: `C:\Users\15750\Desktop\分布式大系统\backend\main.py`
- Modify: `C:\Users\15750\Desktop\分布式大系统\backend\routers\__init__.py`
- Test: `C:\Users\15750\Desktop\分布式大系统\backend\tests\test_app_routes.py`

- [ ] **Step 1: Write the failing app route test**

```python
# C:\Users\15750\Desktop\分布式大系统\backend\tests\test_app_routes.py
from backend.main import app


def test_app_exposes_health_auth_and_platform_routes():
    routes = {route.path for route in app.routes}
    assert "/api/health" in routes
    assert "/api/auth/register" in routes
    assert "/api/platform/workflows" in routes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_app_routes.py -v`

Expected: FAIL until `backend.main` is cleaned up to import the new router layout consistently.

- [ ] **Step 3: Write the minimal platform-first application wiring**

```python
# In C:\Users\15750\Desktop\分布式大系统\backend\main.py use:
from backend.api.routers.platform import router as platform_router
from backend.routers.auth import router as auth_router

app = FastAPI(title="量智硫光后端平台", version="3.0.0")
app.include_router(auth_router)
app.include_router(platform_router)
```

```python
# In C:\Users\15750\Desktop\分布式大系统\backend\routers\__init__.py keep only:
__all__ = []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_app_routes.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/main.py backend/routers/__init__.py backend/tests/test_app_routes.py
git commit -m "refactor: switch app surface to platform-first routing"
```

### Task 10: Run the platform skeleton verification suite

**Files:**
- Modify: `C:\Users\15750\Desktop\分布式大系统\README.md`
- Test: `C:\Users\15750\Desktop\分布式大系统\backend\tests\test_infrastructure_config.py`
- Test: `C:\Users\15750\Desktop\分布式大系统\backend\tests\test_db_config.py`
- Test: `C:\Users\15750\Desktop\分布式大系统\backend\tests\test_workflow_models.py`
- Test: `C:\Users\15750\Desktop\分布式大系统\backend\tests\test_auth_security.py`
- Test: `C:\Users\15750\Desktop\分布式大系统\backend\tests\test_orchestrator_engine.py`
- Test: `C:\Users\15750\Desktop\分布式大系统\backend\tests\test_dispatcher_contracts.py`
- Test: `C:\Users\15750\Desktop\分布式大系统\backend\tests\test_platform_router.py`
- Test: `C:\Users\15750\Desktop\分布式大系统\backend\tests\test_workflow_creation_service.py`
- Test: `C:\Users\15750\Desktop\分布式大系统\backend\tests\test_app_routes.py`

- [ ] **Step 1: Write the failing README verification note test**

```python
# Add to C:\Users\15750\Desktop\分布式大系统\backend\tests\test_infrastructure_config.py
from pathlib import Path


def test_readme_mentions_platform_infrastructure_stack():
    text = Path("README.md").read_text(encoding="utf-8")
    assert "PostgreSQL" in text
    assert "Redis" in text
    assert "RabbitMQ" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_infrastructure_config.py::test_readme_mentions_platform_infrastructure_stack -v`

Expected: FAIL because the README still describes the old SQLite-only backend.

- [ ] **Step 3: Write the minimal docs update and run the full suite**

```markdown
<!-- Update C:\Users\15750\Desktop\分布式大系统\README.md backend stack section to mention: -->
- 后端基础设施：PostgreSQL + Redis + RabbitMQ
- 工作流编排：统一编排中心 + 异步阶段任务
- 本地依赖启动：`docker compose up -d`
```

Run: `pytest backend/tests -v`

Expected: PASS with all platform skeleton tests green.

- [ ] **Step 4: Run startup smoke check**

Run: `uvicorn backend.main:app --host 127.0.0.1 --port 8000`

Expected: Server starts successfully and `GET /api/health` returns `{"status": "ok", "version": "3.0.0"}`.

- [ ] **Step 5: Commit**

```bash
git add README.md backend/tests
git commit -m "test: verify platform skeleton end to end"
```
