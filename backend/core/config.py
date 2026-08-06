from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = ""
    REDIS_URL: str = ""
    RABBITMQ_URL: str = ""
    JWT_SECRET: str = ""
    JWT_EXPIRE_MINUTES: int = 1440
    APP_NAME: str = "Liangzhi Liuguang Platform Backend"
    WORKFLOW_EXECUTION_MODE: str = "sync"
    WORKFLOW_STAGE_QUEUE: str = "platform.workflow.stages"
    QE_EXECUTABLE: str = "pw.x"
    QE_PSEUDO_DIR: str = ""
    CP2K_EXECUTABLE: str = "cp2k"
    DFT_MAX_TIMEOUT_SECONDS: int = 3600
    RESEARCH_BENCHMARK_ADMIN_USERNAMES: str = ""
    LEGACY_PLATFORM_ROUTERS_ENABLED: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()


def has_platform_database() -> bool:
    """Return whether the platform workflow database mirror is configured."""
    return bool(settings.DATABASE_URL.strip())


def has_workflow_queue() -> bool:
    """Return whether RabbitMQ queue dispatch is configured."""
    return bool(settings.RABBITMQ_URL.strip())


def legacy_platform_routers_enabled() -> bool:
    """Whether legacy materials/DFT platform endpoints are publicly mounted."""
    return settings.LEGACY_PLATFORM_ROUTERS_ENABLED
